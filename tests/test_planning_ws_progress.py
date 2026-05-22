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

``receive_json()`` on the TestClient WebSocket is synchronous and blocks
indefinitely if no frames arrive.  We therefore collect frames in a
background thread with a hard wall-time limit to keep tests bounded.

Skipped entirely if fastapi or httpx are not installed.
"""

from __future__ import annotations

import contextlib
import queue
import threading
import time
from typing import Iterator

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from server.main import create_app  # noqa: E402  # noqa: E402

pytestmark = pytest.mark.planning


# ---------------------------------------------------------------------------
# Stub planner / parameteriser helpers (same approach as endpoint tests)
# ---------------------------------------------------------------------------


def _make_medium_planner(step_sleep_s: float = 0.05, n_steps: int = 6):
    """A planner that sleeps cooperatively so the WS can receive frames."""
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


def _collect_ws_frames_threaded(
    ws,
    max_frames: int = 10,
    timeout_s: float = 5.0,
    stop_on_stages: tuple[str, ...] = ("completed", "failed", "cancelled"),
) -> list[dict]:
    """Collect frames from an open WebSocket using a background thread.

    ``ws.receive_json()`` blocks indefinitely when no more frames arrive.
    Running it in a daemon thread with a hard wall-time deadline prevents
    the test suite from hanging.
    """
    result_q: queue.Queue = queue.Queue()

    def _reader():
        try:
            while True:
                frame = ws.receive_json()
                result_q.put(frame)
                if frame.get("stage") in stop_on_stages:
                    break
        except Exception:  # noqa: BLE001
            pass  # WS closed / timed out

    t = threading.Thread(target=_reader, daemon=True)
    t.start()

    collected = []
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline and len(collected) < max_frames:
        try:
            frame = result_q.get(timeout=max(0.0, deadline - time.monotonic()))
            collected.append(frame)
            if frame.get("stage") in stop_on_stages:
                break
        except queue.Empty:
            break

    # Don't join the thread — if receive_json is blocking, the daemon thread
    # will be killed at process exit. The WebSocket context manager will close
    # the connection which unblocks receive_json.
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

    # Medium planner stays in flight while WS connects.
    planner = _make_medium_planner(step_sleep_s=0.06, n_steps=8)

    app = create_app()
    with _patch_planning_runtime(planner=planner):
        with TestClient(app) as c:
            _spawn_robot(c)

            # Submit the plan first (creates the runtime).
            r = c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
            assert r.status_code == 200

            # Connect to WS while plan is in-flight.
            with c.websocket_connect("/ws/planning/progress") as ws:
                frames = _collect_ws_frames_threaded(
                    ws,
                    max_frames=15,
                    timeout_s=8.0,
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
    Within a 4 s window we expect >= 2 frames (1 stage-transition + at
    least 1 heartbeat).

    Also asserts that ``percent`` is monotonically non-decreasing across
    consecutive frames for the same plan (the iteration-2 fix: heartbeats
    use ``record.last_percent`` not a hard-coded 0.5)."""
    pytest.importorskip("pybullet")

    # Slow enough that the heartbeat (500 ms) fires at least twice.
    # Plan runs ~3 s: 12 steps × 0.25 s each.
    planner = _make_medium_planner(step_sleep_s=0.25, n_steps=12)

    app = create_app()
    with _patch_planning_runtime(planner=planner):
        with TestClient(app) as c:
            _spawn_robot(c)

            r = c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
            assert r.status_code == 200

            with c.websocket_connect("/ws/planning/progress") as ws:
                frames = _collect_ws_frames_threaded(
                    ws,
                    max_frames=25,
                    timeout_s=8.0,
                    stop_on_stages=("completed", "failed", "cancelled"),
                )

    assert len(frames) >= 2, (
        f"Expected >= 2 frames (stage transitions + heartbeats), got {len(frames)}: {frames}"
    )

    # Verify percent never decreases for same plan_id within the same stage
    # (the iteration-2 fix: heartbeats use record.last_percent so they don't
    # flicker backwards within a stage).
    # Note: percent RESETS to 0.0 on each stage transition (e.g. sampling→
    # parameterising is expected behaviour, not a regression).
    if len(frames) >= 2:
        for i in range(len(frames) - 1):
            a, b = frames[i], frames[i + 1]
            if a.get("plan_id") != b.get("plan_id"):
                continue
            if a.get("stage") != b.get("stage"):
                # Stage transition: percent reset is expected.
                continue
            # Same plan_id, same stage: percent must not decrease.
            assert b["percent"] >= a["percent"] - 0.001, (
                f"percent regressed within stage '{a.get('stage')}' at frame "
                f"{i}->{i+1}: {a['percent']} -> {b['percent']} — "
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
    1. Submit plan A (fast planner, completes quickly) and wait for it.
    2. Submit plan B (medium planner, stays in-flight longer).
    3. Open WS, send subscribe message for plan B's id.
    4. Collect frames.
    5. Assert no collected frame has plan_id == plan_A_id.
    """
    pytest.importorskip("pybullet")

    fast_planner = _make_fast_planner()
    medium_planner = _make_medium_planner(step_sleep_s=0.1, n_steps=8)

    from server.services.planning import PlanningRuntime

    original = PlanningRuntime._ensure_stateless_components
    par = _make_stub_parameteriser()

    call_count = [0]

    def _multi_patched(self):
        # First invocation (plan A): fast planner.
        # Subsequent invocations (plan B and beyond): medium planner.
        if call_count[0] == 0:
            self.sampling_planner = fast_planner
        else:
            self.sampling_planner = medium_planner
        self.parameteriser = par
        self.optimiser = None
        call_count[0] += 1

    PlanningRuntime._ensure_stateless_components = _multi_patched
    try:
        app = create_app()
        with TestClient(app) as c:
            _spawn_robot(c)

            # Plan A — fast, creates the runtime.
            rA = c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
            plan_id_A = rA.json()["plan_id"]

            # Wait for plan A to complete so its frames drain from the queue.
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                status = c.get(f"/api/planning/plans/{plan_id_A}").json()["status"]
                if status in ("completed", "failed"):
                    break
                time.sleep(0.1)
            time.sleep(0.3)  # let any in-flight queue entries drain

            # Plan B — medium, still running when WS opens.
            plan_B_body = {**_VALID_PLAN_BODY, "goal_q": [0.2] * 6}
            rB = c.post("/api/planning/plans", json=plan_B_body)
            plan_id_B = rB.json()["plan_id"]

            # Open WS and immediately subscribe to plan B.
            import json as _json

            with c.websocket_connect("/ws/planning/progress") as ws:
                ws.send_text(_json.dumps({"subscribe": f"plan/{plan_id_B}"}))
                frames = _collect_ws_frames_threaded(
                    ws,
                    max_frames=20,
                    timeout_s=6.0,
                    stop_on_stages=("completed", "failed", "cancelled"),
                )

    finally:
        PlanningRuntime._ensure_stateless_components = original

    b_frames = [f for f in frames if f.get("plan_id") == plan_id_B]
    a_frames = [f for f in frames if f.get("plan_id") == plan_id_A]

    assert len(b_frames) >= 1, (
        f"Expected frames for plan B ({plan_id_B}), got none. "
        f"Collected: {frames}"
    )
    assert len(a_frames) == 0, (
        f"Filter should have blocked plan A ({plan_id_A}) frames, "
        f"but received: {a_frames}"
    )


# ---------------------------------------------------------------------------
# Test: filter clears on reconnect — second WS receives all plans
# Covers: per-connection state isolation (no shared filter state between
#         two separate WebSocket connections).
# ---------------------------------------------------------------------------


def test_ws_filter_clears_on_reconnect():
    """Each new WebSocket connection starts with no filter (receives all
    plans by default).  Two connections are opened sequentially; the first
    uses a wrong filter (blocks plan C), the second uses no filter and
    confirms it receives frames for plan C."""
    pytest.importorskip("pybullet")

    import json as _json

    # Plan C must outlast both connections. Connection 1 runs for 1.5 s,
    # then connection 2 opens. Total exposure ~7.5 s. Planner runs
    # 0.2 s × 50 steps = 10 s, safely exceeding both windows.
    planner = _make_medium_planner(step_sleep_s=0.2, n_steps=50)

    app = create_app()
    with _patch_planning_runtime(planner=planner):
        with TestClient(app) as c:
            _spawn_robot(c)

            # Submit plan C — starts the runtime.
            rC = c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
            plan_id_C = rC.json()["plan_id"]

            # Connection 1: subscribe to a nonexistent plan so frames for C
            # are filtered out.  There is an inherent race between when the
            # subscribe message is processed by the _receiver task and when
            # any in-flight heartbeat frames reach the _sender queue.  We
            # accept that at most 1 frame may slip through during the race
            # window (the first heartbeat that arrives before the subscribe
            # is processed).  The assertion at the end uses <= 1.
            with c.websocket_connect("/ws/planning/progress") as ws1:
                ws1.send_text(_json.dumps({"subscribe": "plan/nonexistent-plan-abc"}))
                frames_ws1 = _collect_ws_frames_threaded(
                    ws1,
                    max_frames=10,
                    timeout_s=1.5,  # short: we expect very few frames through the filter
                    stop_on_stages=("completed", "failed", "cancelled"),
                )

            # Connection 2: NO subscribe message → default = all plans.
            # Plan C is still running (medium planner).
            with c.websocket_connect("/ws/planning/progress") as ws2:
                frames_ws2 = _collect_ws_frames_threaded(
                    ws2,
                    max_frames=15,
                    timeout_s=6.0,
                    stop_on_stages=("completed", "failed", "cancelled"),
                )

    # Second connection must receive frames for plan C.
    c_frames_ws2 = [f for f in frames_ws2 if f.get("plan_id") == plan_id_C]
    assert len(c_frames_ws2) >= 1, (
        f"Second WS (no filter) should receive frames for plan C ({plan_id_C}); "
        f"got frames: {frames_ws2}"
    )

    # First connection's wrong filter must have blocked plan C frames.
    # We accept at most 1 frame that slips through the subscribe-message
    # race window (first heartbeat arriving before _receiver processes the
    # subscribe).  The key property is that the filter is ACTIVE: subsequent
    # frames are dropped, and the second connection (with no filter) receives
    # many frames for plan C.
    c_frames_ws1 = [f for f in frames_ws1 if f.get("plan_id") == plan_id_C]
    assert len(c_frames_ws1) <= 1, (
        f"WS1 with wrong filter should have blocked plan C frames "
        f"(at most 1 race-window slip allowed); got {len(c_frames_ws1)}: {c_frames_ws1}"
    )
    # The second connection must see significantly more plan-C frames than
    # the first, proving the first's filter was effective.
    assert len(c_frames_ws2) > len(c_frames_ws1), (
        f"Second WS (no filter, {len(c_frames_ws2)} frames) should have "
        f"received more plan C frames than WS1 with filter ({len(c_frames_ws1)})"
    )


# ---------------------------------------------------------------------------
# Extra coverage: WS connects before any plan (no runtime) — stays open
# ---------------------------------------------------------------------------


def test_ws_connects_without_runtime():
    """Opening /ws/planning/progress when no PlanningRuntime exists must not
    crash the server.  The handler guards against runtime=None."""
    app = create_app()
    with TestClient(app) as c:
        try:
            with c.websocket_connect("/ws/planning/progress"):
                pass
        except Exception as exc:
            pytest.fail(f"WS connection without runtime raised: {exc}")


# ---------------------------------------------------------------------------
# Extra coverage: PlanProgressFrame schema validation
# ---------------------------------------------------------------------------


def test_ws_frames_have_correct_schema():
    """Every frame must contain plan_id, stage, percent, monotonic_s.
    eta_s is optional.  percent must be in [0, 1]."""
    pytest.importorskip("pybullet")

    planner = _make_medium_planner(step_sleep_s=0.05, n_steps=4)
    app = create_app()

    with _patch_planning_runtime(planner=planner):
        with TestClient(app) as c:
            _spawn_robot(c)

            r = c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
            assert r.status_code == 200

            with c.websocket_connect("/ws/planning/progress") as ws:
                frames = _collect_ws_frames_threaded(
                    ws,
                    max_frames=10,
                    timeout_s=5.0,
                    stop_on_stages=("completed", "failed", "cancelled"),
                )

    assert len(frames) >= 1, "Expected at least one frame"
    required_keys = {"plan_id", "stage", "percent", "monotonic_s"}
    for i, frame in enumerate(frames):
        missing = required_keys - frame.keys()
        assert not missing, f"Frame {i} missing keys {missing}: {frame}"
        assert isinstance(frame["percent"], (int, float)), (
            f"Frame {i} percent must be numeric: {frame['percent']!r}"
        )
        assert 0.0 <= frame["percent"] <= 1.0, (
            f"Frame {i} percent {frame['percent']} out of [0, 1]"
        )
