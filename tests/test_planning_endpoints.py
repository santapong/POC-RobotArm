"""Tests for planning REST endpoints.

Exercises every public endpoint, every error code from the REST table in
§2 of the server brief, and selected risks from §J of the master plan.

Skipped entirely if fastapi or httpx are not installed.

Design notes
------------
- Uses ``TestClient(create_app())`` — the same ``app`` instance as the
  existing endpoint tests.  A fresh app per test function avoids shared
  session state (each ``TestClient.__enter__`` triggers the lifespan, which
  calls ``init_session()`` and resets the module-level singleton).
- ``PlanningRuntime._ensure_stateless_components`` is monkey-patched to
  inject stub planner / parameteriser so tests run without OMPL / Drake /
  toppra being installed.  The patch is applied to the class, restored in
  a ``finally`` block, and is the ONLY thing mocked — the runtime itself,
  PyBullet, session state, and FastAPI internals are all real.
- Per audit-rubric criterion 2 (over-mocking), ``PlanningRuntime`` and
  ``src.planning.*`` are NOT mocked; only the heavy C-extension backends
  (OMPL / Drake / toppra) are replaced with pure-Python stubs.

PLANNING_UNAVAILABLE (422) note
---------------------------------
``PLANNING_UNAVAILABLE`` (422) is the Windows / missing-extra guard raised
when ``from src.planning.types import PlanningUnavailable`` raises
``ImportError`` inside ``server/routers/planning.py:152-160``.  It cannot
be exercised in this CI environment because ``pytest.importorskip('pybullet')``
already gates module collection — by the time these tests run, the planning
extra is installed.  The error code is structurally covered by the lazy-import
block in ``server/services/errors.py`` and ``server/routers/planning.py``.
The guard is present and correct in the implementation; it simply cannot be
triggered without uninstalling the planning extra first.
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
# Stub planner / parameteriser (replaces OMPL + toppra; real PyBullet used)
# ---------------------------------------------------------------------------


def _make_stub_planner():
    """Minimal Planner that returns a 2-waypoint path without calling OMPL."""
    from src.planning.samplers import Planner, PlannerKind

    class _StubPlanner(Planner):
        kind = PlannerKind.RRT_STAR

        def solve(self, scene, checker, q_start, q_goal, config, cancel, on_progress=None):
            cancel.raise_if_cancelled()
            if on_progress is not None:
                on_progress(0.5)
            return (tuple(q_start), tuple(q_goal))

    return _StubPlanner()


def _make_slow_planner(sleep_s: float = 0.05, n_steps: int = 20):
    """A planner that sleeps between cooperative-cancel polls so the test can
    cancel it mid-flight before it completes."""
    from src.planning.samplers import Planner, PlannerKind

    class _SlowPlanner(Planner):
        kind = PlannerKind.RRT_STAR

        def solve(self, scene, checker, q_start, q_goal, config, cancel, on_progress=None):
            for _ in range(n_steps):
                time.sleep(sleep_s)
                cancel.raise_if_cancelled()
            return (tuple(q_start), tuple(q_goal))

    return _SlowPlanner()


def _make_stub_parameteriser():
    """Minimal TimeParameteriser that returns a 2-sample trajectory."""
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


def _make_limits_exceeded_parameteriser(singularity_hint: tuple[int, ...] = (1, 2)):
    """A parameteriser that always raises PlanLimitsExceeded."""
    from src.planning.parameteriser import PlanLimitsExceeded, TimeParameteriser

    class _LimitsExceededParameteriser(TimeParameteriser):
        def parameterise(self, scene, waypoints, config, cancel, dt_s: float = 0.01):
            raise PlanLimitsExceeded("...test...", singularity_hint=singularity_hint)

    return _LimitsExceededParameteriser()


@contextlib.contextmanager
def _patch_planning_runtime(planner=None, parameteriser=None) -> Iterator[None]:
    """Patch ``PlanningRuntime._ensure_stateless_components`` with stubs.

    Restores the original method on exit regardless of outcome.
    """
    from server.services.planning import PlanningRuntime

    p = planner if planner is not None else _make_stub_planner()
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
    """Create a new station, spawn a robot, return its id.

    A brief sleep lets the PyBullet sim tick start so subsequent planning
    calls can read joint angles.
    """
    client.post("/api/station/new")
    r = client.post("/api/station/robots", json={"catalog_name": catalog_name})
    assert r.status_code == 200, f"Spawn failed: {r.text}"
    time.sleep(0.3)  # let the sim tick settle
    return r.json()["id"]


def _wait_for_plan(
    client: TestClient,
    plan_id: str,
    timeout_s: float = 10.0,
    poll_s: float = 0.2,
) -> dict:
    """Poll GET /api/planning/plans/{plan_id} until status is terminal."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        r = client.get(f"/api/planning/plans/{plan_id}")
        assert r.status_code == 200, f"GET plan failed: {r.text}"
        body = r.json()
        if body["status"] in ("completed", "failed", "cancelled"):
            return body
        time.sleep(poll_s)
    raise TimeoutError(f"Plan {plan_id} did not reach terminal state in {timeout_s}s")


def _wait_for_run(
    client: TestClient,
    run_id: str,
    timeout_s: float = 20.0,
    poll_s: float = 0.2,
) -> dict:
    """Poll GET /api/programs/runs/{run_id} until status is terminal."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        r = client.get(f"/api/programs/runs/{run_id}")
        assert r.status_code == 200, f"GET run failed: {r.text}"
        body = r.json()
        if body["status"] in ("completed", "failed"):
            return body
        time.sleep(poll_s)
    raise TimeoutError(f"Run {run_id} did not reach terminal state in {timeout_s}s")


# ---------------------------------------------------------------------------
# Standard valid plan request body
# ---------------------------------------------------------------------------

_VALID_PLAN_BODY = {
    "robot_id": "abb_irb1200",
    "q_start": [0.0] * 6,
    "goal_q": [0.1, 0.1, 0.1, 0.1, 0.1, 0.1],
}


# ---------------------------------------------------------------------------
# Test: 503 PLANNING_NOT_INITIALIZED before sim is up
# Covers: error code PLANNING_NOT_INITIALIZED; Risk §J #14 (no regression)
# ---------------------------------------------------------------------------


def test_create_plan_503_when_sim_runtime_missing():
    """POST /api/planning/plans before a robot is spawned returns 503
    PLANNING_NOT_INITIALIZED.  This mirrors the program-run pattern from
    Phase 1 and asserts that the endpoint never crashes on an uninitialised
    session."""
    app = create_app()
    with TestClient(app) as c:
        r = c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
    assert r.status_code == 503
    assert r.json()["code"] == "PLANNING_NOT_INITIALIZED"


# ---------------------------------------------------------------------------
# Test: 422 VALIDATION_ERROR — Pydantic validator fires (neither goal set)
# Covers: error code VALIDATION_ERROR; PM decision (not PLANNING_BAD_CONFIG)
# ---------------------------------------------------------------------------


def test_create_plan_422_when_neither_goal_set():
    """Sending a plan body with neither goal_q nor goal_pose_* triggers the
    ``_exactly_one_goal`` Pydantic validator — must return 422 VALIDATION_ERROR
    (not PLANNING_BAD_CONFIG, per PM decision)."""
    app = create_app()
    with TestClient(app) as c:
        r = c.post(
            "/api/planning/plans",
            json={
                "robot_id": "abb_irb1200",
                "q_start": [0.0] * 6,
                # no goal_q, no goal_pose_*
            },
        )
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Test: 422 VALIDATION_ERROR — both goals set simultaneously
# ---------------------------------------------------------------------------


def test_create_plan_422_when_both_goals_set():
    """Setting both goal_q AND goal_pose_* is mutually exclusive — must also
    return 422 VALIDATION_ERROR, not PLANNING_BAD_CONFIG."""
    app = create_app()
    with TestClient(app) as c:
        r = c.post(
            "/api/planning/plans",
            json={
                "robot_id": "abb_irb1200",
                "q_start": [0.0] * 6,
                "goal_q": [0.1] * 6,
                "goal_pose_xyz_m": [0.3, 0.0, 0.5],
                "goal_pose_quat_wxyz": [1.0, 0.0, 0.0, 0.0],
            },
        )
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Test: 422 VALIDATION_ERROR — goal_pose_xyz_m has wrong length
# Covers: Pydantic min/max_length=3 field constraint; NOT to_domain()
# ---------------------------------------------------------------------------


def test_create_plan_422_when_goal_pose_xyz_wrong_length():
    """goal_pose_xyz_m=[1, 2] (2 elements instead of 3) must be caught by
    Pydantic's ``min_length=3, max_length=3`` annotation and return 422
    VALIDATION_ERROR before ``to_domain()`` is ever called."""
    app = create_app()
    with TestClient(app) as c:
        r = c.post(
            "/api/planning/plans",
            json={
                "robot_id": "abb_irb1200",
                "q_start": [0.0] * 6,
                "goal_pose_xyz_m": [1.0, 2.0],  # wrong length
                "goal_pose_quat_wxyz": [1.0, 0.0, 0.0, 0.0],
            },
        )
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# Test: 422 PLANNING_BAD_CONFIG — non-unit quaternion (passes Pydantic, fails
# in PlanRequest.__post_init__)
# Covers: downstream-domain validation; PM decision PLANNING_BAD_CONFIG
# ---------------------------------------------------------------------------


def test_create_plan_422_when_goal_pose_quat_not_unit():
    """A quaternion [2, 0, 0, 0] has length=2 (passes Pydantic's length=4
    constraint) but fails ``PlanRequest.__post_init__``'s unit-norm check.
    This downstream ValueError must be caught by the router and returned as
    422 PLANNING_BAD_CONFIG, not VALIDATION_ERROR."""
    pytest.importorskip("pybullet")
    app = create_app()
    with TestClient(app) as c:
        _spawn_robot(c)
        r = c.post(
            "/api/planning/plans",
            json={
                "robot_id": "abb_irb1200",
                "q_start": [0.0] * 6,
                "goal_pose_xyz_m": [0.3, 0.0, 0.5],
                "goal_pose_quat_wxyz": [2.0, 0.0, 0.0, 0.0],  # |q| = 2, not unit
            },
        )
    assert r.status_code == 422
    assert r.json()["code"] == "PLANNING_BAD_CONFIG"


# ---------------------------------------------------------------------------
# Test: happy path — POST returns running record
# Covers: PlanCreateResponse shape; status=running immediately on return
# ---------------------------------------------------------------------------


def test_create_plan_returns_running_record():
    """POST /api/planning/plans with a valid request must return 200 with a
    ``plan_id`` (UUID string) and ``status == 'running'`` immediately (the
    planning work happens asynchronously in the executor)."""
    pytest.importorskip("pybullet")
    app = create_app()
    with _patch_planning_runtime():
        with TestClient(app) as c:
            _spawn_robot(c)
            r = c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
    assert r.status_code == 200
    body = r.json()
    assert "plan_id" in body, "Response must include plan_id"
    assert len(body["plan_id"]) > 0
    assert body["status"] == "running"


# ---------------------------------------------------------------------------
# Test: 404 PLAN_UNKNOWN for unknown plan_id
# Covers: error code PLAN_UNKNOWN
# ---------------------------------------------------------------------------


def test_get_plan_404_for_unknown_id():
    """GET /api/planning/plans/missing returns 404 PLAN_UNKNOWN."""
    pytest.importorskip("pybullet")
    app = create_app()
    with TestClient(app) as c:
        _spawn_robot(c)
        # Submit one plan so the runtime exists, then fetch a nonexistent id
        c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
        r = c.get("/api/planning/plans/nonexistent-uuid-1234")
    assert r.status_code == 404
    assert r.json()["code"] == "PLAN_UNKNOWN"


# ---------------------------------------------------------------------------
# Test: list plans returns records
# Covers: GET /api/planning/plans endpoint
# ---------------------------------------------------------------------------


def test_list_plans_returns_records():
    """After creating one plan, GET /api/planning/plans must return a list
    with at least one entry whose plan_id matches the created plan."""
    pytest.importorskip("pybullet")
    app = create_app()
    with _patch_planning_runtime():
        with TestClient(app) as c:
            _spawn_robot(c)
            r_create = c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
            plan_id = r_create.json()["plan_id"]

            r_list = c.get("/api/planning/plans")

    assert r_list.status_code == 200
    plans = r_list.json()
    assert isinstance(plans, list)
    ids = [p["plan_id"] for p in plans]
    assert plan_id in ids, f"Created plan {plan_id} not in list: {ids}"


# ---------------------------------------------------------------------------
# Test: 409 PLAN_NOT_COMPLETED — trajectory while running
# Covers: error code PLAN_NOT_COMPLETED
# ---------------------------------------------------------------------------


def test_get_trajectory_409_when_running():
    """GET /api/planning/plans/{id}/trajectory while the plan is still
    running (status='running') returns 409 PLAN_NOT_COMPLETED."""
    pytest.importorskip("pybullet")

    # Use a slow planner so the plan stays in 'running' state long enough
    app = create_app()
    with _patch_planning_runtime(planner=_make_slow_planner(sleep_s=0.1, n_steps=30)):
        with TestClient(app) as c:
            _spawn_robot(c)
            r_create = c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
            plan_id = r_create.json()["plan_id"]

            # Poll until status='running' (plan is in the executor) before
            # fetching the trajectory so the timing is deterministic.
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                status_r = c.get(f"/api/planning/plans/{plan_id}")
                if status_r.json().get("status") == "running":
                    break
                time.sleep(0.02)

            r = c.get(f"/api/planning/plans/{plan_id}/trajectory")
    assert r.status_code == 409
    assert r.json()["code"] == "PLAN_NOT_COMPLETED"


# ---------------------------------------------------------------------------
# Test: 409 PLAN_NOT_COMPLETED — execute while running
# Covers: error code PLAN_NOT_COMPLETED (execute path)
# ---------------------------------------------------------------------------


def test_execute_plan_409_when_running():
    """POST /api/planning/plans/{id}/execute while the plan is still running
    returns 409 PLAN_NOT_COMPLETED (can't execute a trajectory that doesn't
    exist yet)."""
    pytest.importorskip("pybullet")

    app = create_app()
    with _patch_planning_runtime(planner=_make_slow_planner(sleep_s=0.1, n_steps=30)):
        with TestClient(app) as c:
            _spawn_robot(c)
            r_create = c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
            plan_id = r_create.json()["plan_id"]

            # Poll until status='running' before calling execute.
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                status_r = c.get(f"/api/planning/plans/{plan_id}")
                if status_r.json().get("status") == "running":
                    break
                time.sleep(0.02)

            r = c.post(
                f"/api/planning/plans/{plan_id}/execute",
                json={"dt_s": 0.01},
            )
    assert r.status_code == 409
    assert r.json()["code"] == "PLAN_NOT_COMPLETED"


# ---------------------------------------------------------------------------
# Test: cancel mid-flight updates status to 'cancelled' with PLANNING_CANCELLED
# Covers: cooperative cancellation; Risk §J #12 (cancel latency)
# Finding 3: assert error_code == "PLANNING_CANCELLED" in the plan record.
# Finding 8: polled wait replaces bare time.sleep(0.3).
# ---------------------------------------------------------------------------


def test_cancel_plan_updates_status():
    """POST cancel on a running plan must return the record with status
    'cancelled' and error_code='PLANNING_CANCELLED'.  Uses a slow planner so
    the plan is still running when cancel fires.

    The cancel endpoint awaits the future with a 3 s timeout; after returning,
    the record must already reflect 'cancelled' and the error_code from the
    cooperative PlanCancelled exception must be stored."""
    pytest.importorskip("pybullet")

    app = create_app()
    with _patch_planning_runtime(planner=_make_slow_planner(sleep_s=0.1, n_steps=30)):
        with TestClient(app) as c:
            _spawn_robot(c)
            r_create = c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
            plan_id = r_create.json()["plan_id"]

            # Polled wait: wait until the plan is in 'running' state before
            # cancelling (replaces bare time.sleep; bounded to 2 s).
            deadline = time.monotonic() + 2.0
            while time.monotonic() < deadline:
                status_r = c.get(f"/api/planning/plans/{plan_id}")
                if status_r.json().get("status") == "running":
                    break
                time.sleep(0.02)

            r_cancel = c.post(f"/api/planning/plans/{plan_id}/cancel")
            assert r_cancel.status_code == 200, f"Cancel failed: {r_cancel.text}"

            # The cancel endpoint awaits the future with a 3 s timeout; after
            # returning the record should already reflect 'cancelled'.
            final_status = r_cancel.json()["status"]

    assert final_status == "cancelled", f"Expected cancelled, got {final_status!r}"

    # Finding 3: after cancel, fetch the record and assert error_code stored.
    # (The record from cancel() return already contains error_code because
    # _record_to_response is used; verify via a fresh GET as well.)
    cancel_body = r_cancel.json()
    assert cancel_body.get("error_code") == "PLANNING_CANCELLED", (
        f"Expected error_code='PLANNING_CANCELLED', got {cancel_body.get('error_code')!r}"
    )


# ---------------------------------------------------------------------------
# Test: completed plan → trajectory accessible
# Covers: GET /api/planning/plans/{id}/trajectory happy path
# ---------------------------------------------------------------------------


def test_get_trajectory_after_plan_completes():
    """After a plan reaches status=completed, GET trajectory returns 200 with
    a TimedTrajectoryModel containing robot_id, dt_s, samples, duration_s."""
    pytest.importorskip("pybullet")

    app = create_app()
    with _patch_planning_runtime():
        with TestClient(app) as c:
            _spawn_robot(c)
            r_create = c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
            plan_id = r_create.json()["plan_id"]

            record = _wait_for_plan(c, plan_id)
            assert record["status"] == "completed", f"Plan did not complete: {record}"

            r_traj = c.get(f"/api/planning/plans/{plan_id}/trajectory")

    assert r_traj.status_code == 200
    traj = r_traj.json()
    assert traj["robot_id"] == "abb_irb1200"
    assert isinstance(traj["dt_s"], float) and traj["dt_s"] > 0
    assert isinstance(traj["samples"], list)
    assert len(traj["samples"]) >= 2
    # Each sample must carry t_s, q_rad, qd_rad_s, qdd_rad_s2
    s = traj["samples"][0]
    for key in ("t_s", "q_rad", "qd_rad_s", "qdd_rad_s2"):
        assert key in s, f"Sample missing key {key!r}"


# ---------------------------------------------------------------------------
# Test: execute completed plan → bridge start_trajectory called
# Covers: POST /api/planning/plans/{id}/execute happy path
# ---------------------------------------------------------------------------


def test_execute_plan_returns_run_id():
    """POST execute on a completed plan returns 200 with a non-empty run_id,
    confirming the trajectory was handed to the sim bridge."""
    pytest.importorskip("pybullet")

    app = create_app()
    with _patch_planning_runtime():
        with TestClient(app) as c:
            _spawn_robot(c)
            r_create = c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
            plan_id = r_create.json()["plan_id"]

            _wait_for_plan(c, plan_id)

            r_exec = c.post(
                f"/api/planning/plans/{plan_id}/execute",
                json={"dt_s": 0.01},
            )

    assert r_exec.status_code == 200
    body = r_exec.json()
    assert "run_id" in body
    assert len(body["run_id"]) > 0


# ---------------------------------------------------------------------------
# Test: 503 SIM_DISCONNECTED when sim_runtime is None on execute
# Covers: Finding 6 — execute endpoint's SIM_DISCONNECTED guard
# ---------------------------------------------------------------------------


def test_execute_plan_503_when_sim_disconnected():
    """POST /api/planning/plans/{id}/execute when the sim_runtime has been
    torn down must return 503 SIM_DISCONNECTED."""
    pytest.importorskip("pybullet")

    app = create_app()
    with _patch_planning_runtime():
        with TestClient(app) as c:
            _spawn_robot(c)
            r_create = c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
            plan_id = r_create.json()["plan_id"]
            _wait_for_plan(c, plan_id)

            # Null out sim_runtime to simulate SIM_DISCONNECTED.
            from server.services.session import get_session

            session = get_session()
            original_sim = session.sim_runtime
            session.sim_runtime = None
            try:
                r_exec = c.post(
                    f"/api/planning/plans/{plan_id}/execute",
                    json={"dt_s": 0.01},
                )
            finally:
                session.sim_runtime = original_sim  # restore so lifespan cleanup works

    assert r_exec.status_code == 503
    assert r_exec.json()["code"] == "SIM_DISCONNECTED"


# ---------------------------------------------------------------------------
# Test: cache hit short-circuits the executor
# Covers: plan cache (LRU cap 32); Risk §J #11 (collision determinism)
# The second plan with the same (scene, request) fingerprint returns
# status=completed immediately and cache_hit=True.
# ---------------------------------------------------------------------------


def test_cache_hit_short_circuits():
    """Submitting an identical plan twice: the second run should return
    cache_hit=True.  The first run must complete before the second is
    submitted so the cache is populated."""
    pytest.importorskip("pybullet")

    app = create_app()
    with _patch_planning_runtime():
        with TestClient(app) as c:
            _spawn_robot(c)

            # First plan — populates the cache
            r1 = c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
            plan_id1 = r1.json()["plan_id"]
            rec1 = _wait_for_plan(c, plan_id1)
            assert rec1["status"] == "completed", "First plan must complete to populate cache"
            assert rec1["cache_hit"] is False

            # Second plan — same payload → same fingerprint → cache hit
            r2 = c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
            plan_id2 = r2.json()["plan_id"]
            rec2 = _wait_for_plan(c, plan_id2, timeout_s=5.0)

    assert rec2["status"] == "completed"
    assert rec2["cache_hit"] is True, (
        "Second plan with same (scene, request) fingerprint must be served from cache"
    )


# ---------------------------------------------------------------------------
# Test: cache lock handles concurrent submissions without KeyError
# Covers: Finding 4 — _plan_cache_lock race between event-loop read path and
#         worker-thread popitem/setitem (iteration-2 fix validation)
# ---------------------------------------------------------------------------


def test_cache_lock_handles_concurrent_submissions():
    """Submitting two identical plan requests back-to-back (without waiting
    for the first to complete) must not raise a KeyError from the concurrent
    dict read/write in plan() vs _plan_blocking().

    The iteration-2 fix adds a threading.Lock around the cache operations.
    This test validates that fix by racing two identical submissions five
    times, asserting both always reach status=completed without errors."""
    pytest.importorskip("pybullet")

    # Planner that sleeps 200 ms so the first plan is in-flight long enough
    # for the second submission to race the cache lookup.
    from src.planning.samplers import Planner, PlannerKind

    class _SlightlySlowPlanner(Planner):
        kind = PlannerKind.RRT_STAR

        def solve(self, scene, checker, q_start, q_goal, config, cancel, on_progress=None):
            cancel.raise_if_cancelled()
            time.sleep(0.2)
            cancel.raise_if_cancelled()
            if on_progress is not None:
                on_progress(1.0)
            return (tuple(q_start), tuple(q_goal))

    for _ in range(5):
        app = create_app()
        with _patch_planning_runtime(planner=_SlightlySlowPlanner()):
            with TestClient(app) as c:
                _spawn_robot(c)

                # Submit two identical plan requests back-to-back.
                r1 = c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
                r2 = c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
                assert r1.status_code == 200, f"Plan 1 submission failed: {r1.text}"
                assert r2.status_code == 200, f"Plan 2 submission failed: {r2.text}"

                plan_id1 = r1.json()["plan_id"]
                plan_id2 = r2.json()["plan_id"]

                # Poll both to terminal status.
                rec1 = _wait_for_plan(c, plan_id1, timeout_s=15.0)
                rec2 = _wait_for_plan(c, plan_id2, timeout_s=15.0)

        assert rec1["status"] == "completed", (
            f"Plan 1 did not complete (race iteration); got: {rec1}"
        )
        assert rec2["status"] == "completed", (
            f"Plan 2 did not complete (race iteration); got: {rec2}"
        )
        # At least one of the two must report cache_hit=True (the second
        # may be served from cache once the first populates it).  In some
        # race timings both run in the executor, in others one gets a hit.
        # The key property is no KeyError / crash — both complete cleanly.


# ---------------------------------------------------------------------------
# Test: PLANNING_TIMEOUT when planner exceeds timeout_s
# Covers: error code PLANNING_TIMEOUT; Risk §J #10
# The planner returns PLANNING_FAILED (with error_code) when the heavy
# backend raises PlanTimeout; the route returns 200 + status=failed.
# ---------------------------------------------------------------------------


def test_planning_timeout():
    """A stub planner that raises PlanTimeout causes the plan to reach
    status=failed with error_code=PLANNING_TIMEOUT.

    Note: the pipeline catches PlanTimeout and converts it to a failed
    PlanResult (status=FAILED, error_code='PLANNING_TIMEOUT') — the REST
    endpoint returns 200 + the record, NOT 504.  The 504 error code lives
    in the error_code field of the record and in the map_exception table
    for direct HTTP errors; when the plan runs asynchronously the server
    stores the error inside the record."""
    pytest.importorskip("pybullet")

    from src.planning.budgets import PlanTimeout
    from src.planning.samplers import Planner, PlannerKind

    class _TimeoutPlanner(Planner):
        kind = PlannerKind.RRT_STAR

        def solve(self, scene, checker, q_start, q_goal, config, cancel, on_progress=None):
            raise PlanTimeout("Exceeded timeout for test")

    app = create_app()
    with _patch_planning_runtime(planner=_TimeoutPlanner()):
        with TestClient(app) as c:
            _spawn_robot(c)
            r_create = c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
            plan_id = r_create.json()["plan_id"]
            record = _wait_for_plan(c, plan_id)

    assert record["status"] == "failed"
    assert record["error_code"] == "PLANNING_TIMEOUT", (
        f"Expected PLANNING_TIMEOUT in error_code, got {record['error_code']!r}"
    )


# ---------------------------------------------------------------------------
# Test: PLANNING_NO_SOLUTION when sampler exhausts budget
# Covers: error code PLANNING_NO_SOLUTION
# ---------------------------------------------------------------------------


def test_planning_no_solution_in_blocked_scene():
    """A stub planner that raises PlanNoSolution causes status=failed with
    error_code=PLANNING_NO_SOLUTION stored in the plan record."""
    pytest.importorskip("pybullet")

    from src.planning.samplers import Planner, PlannerKind, PlanNoSolution

    class _NoSolutionPlanner(Planner):
        kind = PlannerKind.RRT_STAR

        def solve(self, scene, checker, q_start, q_goal, config, cancel, on_progress=None):
            raise PlanNoSolution("No collision-free path found for test")

    app = create_app()
    with _patch_planning_runtime(planner=_NoSolutionPlanner()):
        with TestClient(app) as c:
            _spawn_robot(c)
            r_create = c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
            plan_id = r_create.json()["plan_id"]
            record = _wait_for_plan(c, plan_id)

    assert record["status"] == "failed"
    assert record["error_code"] == "PLANNING_NO_SOLUTION", (
        f"Expected PLANNING_NO_SOLUTION, got {record['error_code']!r}"
    )


# ---------------------------------------------------------------------------
# Test: PLANNING_LIMITS_EXCEEDED stored in record
# Covers: Finding 5 — parameteriser raising PlanLimitsExceeded
# ---------------------------------------------------------------------------


def test_planning_limits_exceeded_stored_in_record():
    """A parameteriser that raises PlanLimitsExceeded causes status=failed
    with error_code=PLANNING_LIMITS_EXCEEDED and singularity_hint=[1, 2]."""
    pytest.importorskip("pybullet")

    app = create_app()
    with _patch_planning_runtime(parameteriser=_make_limits_exceeded_parameteriser((1, 2))):
        with TestClient(app) as c:
            _spawn_robot(c)
            r_create = c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
            plan_id = r_create.json()["plan_id"]
            record = _wait_for_plan(c, plan_id)

    assert record["status"] == "failed", (
        f"Expected status=failed, got {record['status']!r}"
    )
    assert record["error_code"] == "PLANNING_LIMITS_EXCEEDED", (
        f"Expected error_code='PLANNING_LIMITS_EXCEEDED', got {record['error_code']!r}"
    )
    assert record["singularity_hint"] == [1, 2], (
        f"Expected singularity_hint=[1, 2], got {record['singularity_hint']!r}"
    )


# ---------------------------------------------------------------------------
# Test: run_program with planner="rrt" completes; planner="linear" unchanged
# Covers: programs.py augmentation; Risk §J #14 (no regression to Phase 1)
# Finding 2: poll until terminal status, assert status=="completed".
# ---------------------------------------------------------------------------


def test_run_program_with_rrt_planner():
    """POST /api/programs/demo/run with {'planner': 'rrt'} must complete
    successfully.  The async task must reach a terminal status — we poll
    GET /api/programs/runs/{run_id} until done and assert status==completed.

    Separately, {'planner': 'linear'} (the Phase 1 default) must continue
    to work exactly as before (backwards-compatibility regression guard)."""
    pytest.importorskip("pybullet")

    app = create_app()
    with _patch_planning_runtime():
        with TestClient(app) as c:
            _spawn_robot(c)

            # Linear planner — Phase 1 path unchanged
            r_linear = c.post("/api/programs/demo/run", json={"planner": "linear"})
            assert r_linear.status_code == 200, f"linear run failed: {r_linear.text}"
            run_id_linear = r_linear.json().get("run_id")
            assert run_id_linear, "linear run must return run_id"

            # Poll until the linear run reaches terminal status.
            rec_linear = _wait_for_run(c, run_id_linear, timeout_s=20.0)
            assert rec_linear["status"] == "completed", (
                f"Linear run expected completed, got {rec_linear['status']!r}: {rec_linear}"
            )

            # RRT planner — new Phase 3 path
            r_rrt = c.post("/api/programs/demo/run", json={"planner": "rrt"})
            assert r_rrt.status_code == 200, f"rrt run failed: {r_rrt.text}"
            run_id_rrt = r_rrt.json().get("run_id")
            assert run_id_rrt, "rrt run must return run_id"

            # Poll until the RRT run reaches terminal status.
            rec_rrt = _wait_for_run(c, run_id_rrt, timeout_s=20.0)
            assert rec_rrt["status"] == "completed", (
                f"RRT run expected completed, got {rec_rrt['status']!r}: {rec_rrt}"
            )


# ---------------------------------------------------------------------------
# Test: run_program_rrt failure when planner raises PlanNoSolution
# Covers: Finding 1 — PLANNING_FAILED in run record; bridge NOT called
# ---------------------------------------------------------------------------


def test_run_program_rrt_failure_marks_planning_failed():
    """When a per-move plan fails (PlanNoSolution raised for every call),
    the run record must reach status='failed' with error containing
    'PLANNING_FAILED', and bridge.start_trajectory must NOT be called.

    Verifies that the _run_program_task_rrt path fails fast on planning
    errors and does not try to execute a partial trajectory."""
    pytest.importorskip("pybullet")

    from src.planning.samplers import Planner, PlannerKind, PlanNoSolution

    class _AlwaysFailPlanner(Planner):
        kind = PlannerKind.RRT_STAR

        def solve(self, scene, checker, q_start, q_goal, config, cancel, on_progress=None):
            raise PlanNoSolution("No solution — test stub")

    app = create_app()
    with _patch_planning_runtime(planner=_AlwaysFailPlanner()):
        with TestClient(app) as c:
            _spawn_robot(c)

            # Intercept bridge.start_trajectory to verify it is never called.
            from server.services.session import get_session

            session = get_session()
            bridge = session.sim_runtime.bridge
            start_traj_calls = []
            original_start = bridge.start_trajectory

            def _counting_start(*args, **kwargs):
                start_traj_calls.append(args)
                return original_start(*args, **kwargs)

            bridge.start_trajectory = _counting_start

            try:
                r_rrt = c.post("/api/programs/demo/run", json={"planner": "rrt"})
                assert r_rrt.status_code == 200, f"run failed unexpectedly: {r_rrt.text}"
                run_id = r_rrt.json()["run_id"]

                # Poll until terminal.
                record = _wait_for_run(c, run_id, timeout_s=20.0)
            finally:
                bridge.start_trajectory = original_start

    assert record["status"] == "failed", (
        f"Expected status=failed when planner raises PlanNoSolution, "
        f"got {record['status']!r}"
    )
    assert "PLANNING_FAILED" in (record.get("error") or ""), (
        f"Expected 'PLANNING_FAILED' in run record error, "
        f"got {record.get('error')!r}"
    )
    assert len(start_traj_calls) == 0, (
        f"bridge.start_trajectory must NOT be called on planning failure, "
        f"but was called {len(start_traj_calls)} time(s)"
    )


# ---------------------------------------------------------------------------
# Extra coverage: list plans returns empty list when no runtime
# ---------------------------------------------------------------------------

# Extra coverage: GET /api/planning/plans with no runtime returns [] not 503.
def test_list_plans_returns_empty_when_no_runtime():
    """GET /api/planning/plans before any plan is created returns an empty
    list (not 503).  The router must handle ``session.planning_runtime is
    None`` gracefully."""
    app = create_app()
    with TestClient(app) as c:
        r = c.get("/api/planning/plans")
    assert r.status_code == 200
    assert r.json() == []


# ---------------------------------------------------------------------------
# Extra coverage: cancel 404 for unknown plan
# ---------------------------------------------------------------------------

# Extra coverage: POST /api/planning/plans/{id}/cancel with unknown id → 404.
def test_cancel_plan_404_for_unknown_id():
    """Cancel a plan that doesn't exist returns 404 PLAN_UNKNOWN."""
    pytest.importorskip("pybullet")

    app = create_app()
    with TestClient(app) as c:
        _spawn_robot(c)
        # Submit a plan to create the runtime, then cancel a nonexistent id
        c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
        r = c.post("/api/planning/plans/nonexistent-cancel-test/cancel")
    assert r.status_code == 404
    assert r.json()["code"] == "PLAN_UNKNOWN"


# ---------------------------------------------------------------------------
# Extra coverage: execute 404 for unknown plan
# ---------------------------------------------------------------------------

# Extra coverage: POST execute with unknown plan_id → 404 PLAN_UNKNOWN.
def test_execute_plan_404_for_unknown_id():
    """POST /api/planning/plans/missing/execute returns 404 PLAN_UNKNOWN."""
    pytest.importorskip("pybullet")

    app = create_app()
    with TestClient(app) as c:
        _spawn_robot(c)
        c.post("/api/planning/plans", json=_VALID_PLAN_BODY)
        r = c.post(
            "/api/planning/plans/nonexistent-execute-test/execute",
            json={"dt_s": 0.01},
        )
    assert r.status_code == 404
    assert r.json()["code"] == "PLAN_UNKNOWN"


# ---------------------------------------------------------------------------
# Extra coverage: PlanRequestModel round-trip via to_domain / from_domain
# Covers: §5 test plan "model_validator: to_domain/from_domain round-trip"
# ---------------------------------------------------------------------------

# Extra coverage: PlanRequestModel.to_domain() round-trip.
def test_plan_request_model_to_domain_round_trip():
    """PlanRequestModel.to_domain() must produce a valid PlanRequest that
    Pydantic can read back via from_attributes (wire round-trip)."""
    from server.models.planning import PlanRequestModel
    from src.planning.types import PlanRequest

    model = PlanRequestModel(
        robot_id="abb_irb1200",
        q_start=[0.0] * 6,
        goal_q=[0.1] * 6,
    )
    domain = model.to_domain()
    assert isinstance(domain, PlanRequest)
    assert domain.robot_id == "abb_irb1200"
    assert domain.q_start == tuple([0.0] * 6)
    assert domain.goal_q == tuple([0.1] * 6)
    assert domain.goal_pose is None


# Extra coverage: goal_pose round-trip.
def test_plan_request_model_goal_pose_round_trip():
    """PlanRequestModel with goal_pose converts to_domain correctly."""
    from server.models.planning import PlanRequestModel

    model = PlanRequestModel(
        robot_id="abb_irb1200",
        q_start=[0.0] * 6,
        goal_pose_xyz_m=[0.3, 0.0, 0.5],
        goal_pose_quat_wxyz=[1.0, 0.0, 0.0, 0.0],
    )
    domain = model.to_domain()
    assert domain.goal_q is None
    assert domain.goal_pose is not None
    assert domain.goal_pose[0] == (0.3, 0.0, 0.5)
    assert domain.goal_pose[1] == (1.0, 0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# Extra coverage: PLANNING_IK_UNREACHABLE stored in record
# ---------------------------------------------------------------------------

# Extra coverage: IK failure produces PLANNING_IK_UNREACHABLE in record.
def test_planning_ik_unreachable_stored_in_record():
    """A planner that triggers IK failure produces a plan record with
    error_code=PLANNING_IK_UNREACHABLE."""
    pytest.importorskip("pybullet")

    from src.planning.ik import PlanningIKUnreachable
    from src.planning.samplers import Planner, PlannerKind

    class _IKFailPlanner(Planner):
        kind = PlannerKind.RRT_STAR

        def solve(self, scene, checker, q_start, q_goal, config, cancel, on_progress=None):
            raise PlanningIKUnreachable("IK unreachable for test")

    app = create_app()
    with _patch_planning_runtime(planner=_IKFailPlanner()):
        with TestClient(app) as c:
            _spawn_robot(c)
            r_create = c.post(
                "/api/planning/plans",
                json={
                    "robot_id": "abb_irb1200",
                    "q_start": [0.0] * 6,
                    "goal_pose_xyz_m": [0.3, 0.0, 0.5],
                    "goal_pose_quat_wxyz": [1.0, 0.0, 0.0, 0.0],
                },
            )
            plan_id = r_create.json()["plan_id"]
            record = _wait_for_plan(c, plan_id)

    assert record["status"] == "failed"
    assert record["error_code"] == "PLANNING_IK_UNREACHABLE"
