"""Tests for the /ws/planning/progress WebSocket endpoint.

Architecture notes
------------------
The planning progress WS handler (``server/ws/planning.py``) captures
``session.planning_runtime`` at *connection* time.  If the runtime does
not exist yet (no plan has been submitted), the WS stays open but
receives no frames.  Tests must therefore:

1. Spawn a robot (creates ``sim_runtime``).
2. POST a plan (lazily creates ``PlanningRuntime`` and dispatches the
   worker).
3. THEN open the WS connection — the handler now holds a live runtime
   reference and subscribes the queue.

The stub planner adds a brief ``time.sleep`` between cooperative-cancel
polls so the WS connection can be established while the plan is still in
flight.

Skipped entirely if fastapi or httpx are not installed.
"""

from __future__ import annotations

import contextlib
import time
from typing import Iterator

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from server.main import create_app  # noqa: E402

pytestmark = pytest.mark.planning


# ---------------------------------------------------------------------------
# Stub planner / parameteriser helpers (same approach as endpoint tests)
# ---------------------------------------------------------------------------


def _make_medium_planner(step_sleep_s: float = 0.05, n_steps: int = 6):
    """A planner that sleeps cooperatively — runs for step_sleep_s × n_steps
    so the WS has time to connect and receive intermediate frames."""
    from src.planning.samplers import Planner, PlannerKind

    class _MediumPlanner(Planner):
        kind = PlannerKind.RRT_STAR

        def solve(self, scene, checker, q_start, q_goal, config, cancel, on_progress=None):
            for i in range(n_steps):
                time.sleep(step_sleep_s)
                cancel.raise_if_cancelled()
                if on_progress is not None:
                    on_progress((i + 1) / n_steps)
            return (tuple(q_start), tuple(q_goal))

    return _MediumPlanner()


def _make_fast_planner():
    """Minimal planner for tests that need a quickly-completing plan."""
    from src.planning.samplers import Planner, PlannerKind

    class _FastPlanner(Planner):
        kind = PlannerKind.RRT_STAR

        def solve(self, scene, checker, q_start, q_goal, config, cancel, on_progress=None):
            cancel.raise_if_cancelled()
            if on_progress is not None:
                on_progress(1.0)
            return (tuple(q_start), tuple(q_goal))

    return _FastPlanner()


def _make_stub_parameteriser():
    from src.planning.parameteriser import TimeParameteriser
    from src.planning.types import TimedTrajectory, TrajectorySample

    class _StubParameteriser(TimeParameteriser):
        def parameterise(self, scene, waypoints, config, cancel, dt_s: float = 0.01):
            cancel.raise_if_cancelled()
            q_start = tuple(waypoints[0])
            q_end = tuple(waypoints[-1])
            dof = len(q_start)
            zeros = (0.0,) * dof
            s0 = TrajectorySample(t_s=0.0, q_rad=q_start, qd_rad_s=zeros, qdd_rad_s2=zeros)
            s1 = TrajectorySample(t_s=dt_s, q_rad=q_end, qd_rad_s=zeros, qdd_rad_s2=zeros)
            return TimedTrajectory(
                robot_id=scene.robot_id,
                dt_s=dt_s,
                samples=(s0, s1),
                duration_s=dt_s,
            )

    return _StubParameteriser()


@contextlib.contextmanager
def _patch_planning_runtime(planner=None, parameteriser=None) -> Iterator[None]:
    from server.services.planning import PlanningRuntime

    p = planner if planner is not None else _make_fast_planner()
    par = parameteriser if parameteriser is not None else _make_stub_parameteriser()

    original = PlanningRuntime._ensure_stateless_components

    def _patched(self):
        self.sampling_planner = p
        self.parameteriser = par
        self.optimiser = None

    PlanningRuntime._ensure_stateless_components = _patched
    try:
        yield
    finally:
        PlanningRuntime._ensure_stateless_components = original


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spawn_robot(client: TestClient, catalog_name: str = "abb_irb1200") -> str:
    client.post("/api/station/new")
    r = client.post("/api/station/robots", json={"catalog_name": catalog_name})
    assert r.status_code == 200
    time.sleep(0.3)
    return r.json()["id"]


_VALID_PLAN_BODY = {
    "robot_id": "abb_irb1200",
    "q_start": [0.0] * 6,
    "goal_q": [0.1, 0.1, 0.1, 0.1, 0.1, 0.1],
}


def _collect_ws_frames(
    client: TestClient,
    path: str,
    max_frames: int = 10,
    read_timeout_s: float = 5.0,
    stop_on_stages: tuple[str, ...] = ("completed", "failed", "cancelled"),
) -> list[dict]:
    """Collect up to ``max_frames`` frames from a WS endpoint.

    Uses a timeout to prevent tests from blocking indefinitely.  The
    ``receive_json()`` call on TestClient is synchronous; we wrap the
    collection in a thread-local deadline guard by limiting iterations.

    Note: ``TestClient.websocket_connect`` does NOT accept a ``timeout``
    parameter — we rely on the planner's step sleep to keep the total
    wall time bounded.
    """
    collected = []
    deadline = time.monotonic() + read_timeout_s
    with client.websocket_connect(path) as ws:
        for _ in range(max_frames):
            if time.monotonic() > deadline:
                break
            try:
                frame = ws.receive_json()
                collected.append(frame)
                if frame.get("stage") in stop_on_stages:
                    break
            except Exception:  # noqa: BLE001
                break
    return collected


# ---------------------------------------------------------------------------
# Test: WS receives stage transitions for a running plan
# Covers: WS fan-out from worker thread via call_soon_threadsafe;
#         Risk §J #8 (asyncio.get_running_loop) — exercised indirectly.
# ---------------------------------------------------------------------------


def test_ws_receives_stage_transitions_for_running_plan():
    """After submitting a plan, the progress WS must receive at least one
    frame with stage in {'sampling', 'parameterising', 'completed'}.

    The plan must be in flight BEFORE the WS connects (see module docstring
    for the ordering requirement)."""
    pytest.importorskip("pybullet")

    # Use a medium planner so the plan stays in flight during WS connection.
    planner = _make_medium_planner(step_sleep_s=0.06, n_steps=8)

    app = create_app()
    with _patch_planning_runtime(planner=planner):
        with TestClient(app) as c:
            _spawn_robot(c)

            # Submit the plan first (creates the runtime).
            r = c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
            assert r.status_code == 200
            # plan_id unused here — we just need the runtime to exist.

            # Now connect to WS; the handler finds a live runtime and
            # subscribes the queue.
            frames = _collect_ws_frames(
                c,
                "/ws/planning/progress",
                max_frames=15,
                read_timeout_s=8.0,
                stop_on_stages=("completed", "failed", "cancelled"),
            )

    observed_stages = {f.get("stage") for f in frames}
    expected_stages = {"sampling", "parameterising", "completed"}
    assert observed_stages & expected_stages, (
        f"Expected at least one frame from {expected_stages}, got stages: {observed_stages}\n"
        f"Frames: {frames}"
    )


# ---------------------------------------------------------------------------
# Test: WS receives heartbeat frames while plan is running
# Covers: heartbeat task at 500 ms; last_percent monotonicity (iteration-2 fix)
# ---------------------------------------------------------------------------


def test_ws_receives_heartbeat_for_running_plan():
    """While a plan is running the heartbeat loop fires every 500 ms.
    Within a 2 s window we expect >= 2 frames (1 stage-transition + at
    least 1 heartbeat).

    Also asserts that ``percent`` is monotonically non-decreasing across
    consecutive frames (the iteration-2 fix: heartbeats use
    ``record.last_percent`` instead of a hard-coded 0.5)."""
    pytest.importorskip("pybullet")

    # Slow enough to emit heartbeats (plan runs ~3 s).
    planner = _make_medium_planner(step_sleep_s=0.25, n_steps=12)

    app = create_app()
    with _patch_planning_runtime(planner=planner):
        with TestClient(app) as c:
            _spawn_robot(c)

            r = c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
            assert r.status_code == 200

            frames = _collect_ws_frames(
                c,
                "/ws/planning/progress",
                max_frames=20,
                read_timeout_s=6.0,
                stop_on_stages=("completed", "failed", "cancelled"),
            )

    assert len(frames) >= 2, (
        f"Expected >= 2 frames (transitions + heartbeats), got {len(frames)}: {frames}"
    )

    # Verify percent never decreases across consecutive frames for the same
    # plan_id (the iteration-2 last_percent fix).
    if len(frames) >= 2:
        for i in range(len(frames) - 1):
            a, b = frames[i], frames[i + 1]
            # Only compare same-plan frames; filter_tests share the queue.
            if a.get("plan_id") == b.get("plan_id"):
                assert b["percent"] >= a["percent"] - 0.001, (
                    f"percent regressed: frames[{i}]={a['percent']} > "
                    f"frames[{i+1}]={b['percent']} — "
                    "last_percent fix may not be applied in heartbeat loop"
                )


# ---------------------------------------------------------------------------
# Test: subscribe filter drops frames for other plans
# Covers: per-plan subscribe filter ('plan/<plan_id>'); WS receiver task.
# ---------------------------------------------------------------------------


def test_ws_subscribe_filter_drops_other_plans():
    """After sending {'subscribe': 'plan/<id_B>'} over the WS, frames for
    plan A must not pass through the filter.

    Approach:
    1. Submit plan A (fast planner, completes quickly).
    2. Submit plan B (medium planner, stays in-flight longer).
    3. Connect WS, send subscribe message for plan B's id.
    4. Collect frames.
    5. Assert no collected frame has plan_id == plan_A_id.
    """
    pytest.importorskip("pybullet")

    # Plan A: fast, completes before WS connects.
    fast_planner = _make_fast_planner()
    # Plan B: medium, stays running after WS connects.
    medium_planner = _make_medium_planner(step_sleep_s=0.1, n_steps=8)

    app = create_app()

    # We need two different planners but the patch only supports one.
    # Use the fast planner for setup (plan A), then swap to medium for plan B.
    from server.services.planning import PlanningRuntime

    original = PlanningRuntime._ensure_stateless_components
    par = _make_stub_parameteriser()

    call_count = [0]

    def _multi_patched(self):
        # First invocation (plan A): fast planner.
        # Subsequent invocations (plan B): medium planner.
        if call_count[0] == 0:
            self.sampling_planner = fast_planner
        else:
            self.sampling_planner = medium_planner
        self.parameteriser = par
        self.optimiser = None
        call_count[0] += 1

    PlanningRuntime._ensure_stateless_components = _multi_patched
    try:
        with TestClient(app) as c:
            _spawn_robot(c)

            # Plan A — triggers runtime creation, fast.
            rA = c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
            plan_id_A = rA.json()["plan_id"]

            # Wait briefly for plan A to complete so its frames are flushed.
            time.sleep(0.8)

            # Plan B — medium planner, still running when WS opens.
            plan_B_body = {**_VALID_PLAN_BODY, "goal_q": [0.2] * 6}
            rB = c.post("/api/planning/plans", json=plan_B_body)
            plan_id_B = rB.json()["plan_id"]

            # Connect WS and subscribe to plan B only.
            collected = []
            with c.websocket_connect("/ws/planning/progress") as ws:
                import json as _json

                ws.send_text(_json.dumps({"subscribe": f"plan/{plan_id_B}"}))
                deadline = time.monotonic() + 5.0
                for _ in range(20):
                    if time.monotonic() > deadline:
                        break
                    try:
                        frame = ws.receive_json()
                        collected.append(frame)
                        if frame.get("stage") in ("completed", "failed", "cancelled"):
                            break
                    except Exception:  # noqa: BLE001
                        break

    finally:
        PlanningRuntime._ensure_stateless_components = original

    # No frame must have plan_id == plan_id_A after the filter is set.
    # (Frames for plan A that arrived before the subscribe message was
    # processed are acceptable — we only care that filtered frames are
    # correct. In practice the filter is set before any B frames arrive.)
    b_frames = [f for f in collected if f.get("plan_id") == plan_id_B]
    a_frames = [f for f in collected if f.get("plan_id") == plan_id_A]

    # Must have received at least one frame for plan B.
    assert len(b_frames) >= 1, (
        f"Expected frames for plan B ({plan_id_B}), got none. "
        f"Collected: {collected}"
    )
    # Must NOT have received frames for plan A after filter was applied.
    assert len(a_frames) == 0, (
        f"Filter should have blocked plan A frames but got {a_frames}"
    )


# ---------------------------------------------------------------------------
# Test: filter clears on reconnect — second WS receives all plans
# Covers: per-connection state isolation (no shared filter state between
#         two separate WebSocket connections).
# ---------------------------------------------------------------------------


def test_ws_filter_clears_on_reconnect():
    """Each new WebSocket connection starts with no filter (receives all
    plans by default).  After closing and reopening the WS, the filter is
    not inherited from the previous session."""
    pytest.importorskip("pybullet")

    planner = _make_medium_planner(step_sleep_s=0.08, n_steps=10)
    app = create_app()

    with _patch_planning_runtime(planner=planner):
        with TestClient(app) as c:
            _spawn_robot(c)

            # Submit the plan.
            r = c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
            plan_id = r.json()["plan_id"]

            # Connection 1: subscribe to a nonexistent plan id so no frames pass.
            import json as _json

            with c.websocket_connect("/ws/planning/progress") as ws1:
                ws1.send_text(_json.dumps({"subscribe": "plan/nonexistent-plan-id"}))
                # The plan is running; with the wrong filter we get nothing.
                frames_ws1 = []
                deadline = time.monotonic() + 1.0
                while time.monotonic() < deadline:
                    try:
                        frame = ws1.receive_json()
                        frames_ws1.append(frame)
                    except Exception:  # noqa: BLE001
                        break

            # Connection 2: no subscribe message → receives all plans.
            frames_ws2 = _collect_ws_frames(
                c,
                "/ws/planning/progress",
                max_frames=15,
                read_timeout_s=6.0,
                stop_on_stages=("completed", "failed", "cancelled"),
            )

    # Second connection must receive frames for the running plan.
    plan_frames_ws2 = [f for f in frames_ws2 if f.get("plan_id") == plan_id]
    assert len(plan_frames_ws2) >= 1, (
        f"Second WS connection (no filter) should receive frames for {plan_id}; "
        f"got: {frames_ws2}"
    )

    # First connection's wrong filter means no frames for the real plan_id.
    plan_frames_ws1 = [f for f in frames_ws1 if f.get("plan_id") == plan_id]
    assert len(plan_frames_ws1) == 0, (
        f"WS1 with wrong filter should NOT see plan {plan_id} frames; "
        f"got {plan_frames_ws1}"
    )


# ---------------------------------------------------------------------------
# Extra coverage: WS connects before any plan (no runtime) — stays open
# ---------------------------------------------------------------------------

# Extra coverage: WS connection with no planning runtime stays open and
# does not crash the server.
def test_ws_connects_without_runtime():
    """Opening /ws/planning/progress when no PlanningRuntime exists must not
    cause a server error — the WS should accept the connection and stay open
    (the handler guards against runtime=None)."""
    app = create_app()
    with TestClient(app) as c:
        # Do NOT spawn a robot — runtime is None.
        try:
            with c.websocket_connect("/ws/planning/progress"):
                pass  # just open and close
        except Exception as exc:
            pytest.fail(
                f"WS connection without runtime raised an unexpected exception: {exc}"
            )


# ---------------------------------------------------------------------------
# Extra coverage: PlanProgressFrame shape validation
# ---------------------------------------------------------------------------

# Extra coverage: verify all required fields are present in each WS frame.
def test_ws_frames_have_correct_schema():
    """Every frame received over /ws/planning/progress must contain all
    fields required by PlanProgressFrame: plan_id, stage, percent,
    monotonic_s.  eta_s is optional."""
    pytest.importorskip("pybullet")

    planner = _make_medium_planner(step_sleep_s=0.05, n_steps=4)
    app = create_app()

    with _patch_planning_runtime(planner=planner):
        with TestClient(app) as c:
            _spawn_robot(c)

            r = c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
            assert r.status_code == 200

            frames = _collect_ws_frames(
                c,
                "/ws/planning/progress",
                max_frames=10,
                read_timeout_s=5.0,
                stop_on_stages=("completed", "failed", "cancelled"),
            )

    assert len(frames) >= 1, "Expected at least one frame"
    required_keys = {"plan_id", "stage", "percent", "monotonic_s"}
    for i, frame in enumerate(frames):
        missing = required_keys - frame.keys()
        assert not missing, (
            f"Frame {i} missing required keys {missing}: {frame}"
        )
        assert isinstance(frame["percent"], (int, float)), (
            f"Frame {i} percent must be numeric: {frame['percent']!r}"
        )
        assert 0.0 <= frame["percent"] <= 1.0, (
            f"Frame {i} percent {frame['percent']} out of [0, 1]"
        )
