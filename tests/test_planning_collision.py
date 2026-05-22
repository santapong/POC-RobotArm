"""Tests for src.planning.collision — thread-affined CollisionChecker wrapper.

Covers:
- Known-colliding configuration is flagged as collision
- Checker uses a SEPARATE PyBullet client (independence from live SimRuntime)
- Thread affinity (calls from multiple worker threads return identical results)
  — risk #7
- close() joins worker thread
- Worker-crash drain: pending Futures raise RuntimeError after worker exit
- Determinism: same q returns same result across multiple calls (risk #11)
"""

from __future__ import annotations

import concurrent.futures
import threading

import pytest

pytestmark = pytest.mark.planning
pytest.importorskip("pybullet")

from src.planning.collision import CollisionChecker  # noqa: E402
from src.planning.scene import SceneSnapshot  # noqa: E402
from src.station.scene import Frame, RobotEntry, Station  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_IDENTITY_QUAT = (1.0, 0.0, 0.0, 0.0)


@pytest.fixture
def ur5_scene() -> SceneSnapshot:
    station = Station(
        name="cell",
        frames=(Frame("world", (0.0, 0.0, 0.0), _IDENTITY_QUAT),),
        robots=(RobotEntry("arm0", "ur5", "world"),),
    )
    return SceneSnapshot.from_station(station, "arm0")


@pytest.fixture
def ur5_checker(ur5_scene: SceneSnapshot):
    with CollisionChecker(ur5_scene) as checker:
        yield checker


# ---------------------------------------------------------------------------
# Collision detection
# ---------------------------------------------------------------------------


def test_no_collision_at_home_config(ur5_checker: CollisionChecker, ur5_scene: SceneSnapshot) -> None:
    """Robot at home should not self-collide with no obstacles."""
    q = list(ur5_scene.home_q)
    result = ur5_checker.is_collision(q)
    assert isinstance(result, bool)
    # Home config should not be in self-collision
    assert result is False


def test_known_self_collision_config(ur5_checker: CollisionChecker, ur5_scene: SceneSnapshot) -> None:
    """Extreme joint values that force self-intersection must return True.

    For ur5, setting joint[1]=π, joint[2]=π, joint[3]=-π/2 folds the elbow
    back into the upper arm. Verified against the UR5 URDF geometry: this
    configuration produces actual link-mesh overlap that PyBullet's narrow
    phase reports as a contact with distance ≤ 0 (self-collision).

    Fix A: was asserting isinstance(result, bool) which accepted any return
    value. Now asserts the geometrically guaranteed True.
    """
    import math
    q = [0.0, math.pi, math.pi, -math.pi / 2.0, 0.0, 0.0]
    result = ur5_checker.is_collision(q)
    assert result is True, (
        f"Expected self-collision for folded UR5 config {q!r}, got {result}. "
        "The test ensures the checker actually detects self-intersection, not "
        "just that it returns a bool."
    )


# Extra coverage: large clearance always triggers collision (risk #11 — determinism)
def test_collision_with_huge_clearance_is_deterministic(
    ur5_checker: CollisionChecker, ur5_scene: SceneSnapshot
) -> None:
    """Same q + large clearance must return True consistently (risk #11)."""
    q = list(ur5_scene.home_q)
    results = [ur5_checker.is_collision(q, clearance_m=100.0) for _ in range(5)]
    # A 100 m clearance means everything is "in collision"
    assert all(r is True for r in results)


def test_same_q_same_result_multiple_calls(
    ur5_checker: CollisionChecker, ur5_scene: SceneSnapshot
) -> None:
    """Same q without clearance must return the same bool value every call (risk #11)."""
    q = list(ur5_scene.home_q)
    first = ur5_checker.is_collision(q)
    for _ in range(4):
        assert ur5_checker.is_collision(q) is first


# ---------------------------------------------------------------------------
# Thread affinity — risk #7
# ---------------------------------------------------------------------------


def test_thread_affinity_multiple_workers_return_same_result(
    ur5_checker: CollisionChecker, ur5_scene: SceneSnapshot
) -> None:
    """Calls from multiple worker threads must return the same result (risk #7).

    The checker posts via queue.Queue to a single dedicated PyBullet thread;
    workers never directly touch PyBullet.
    """
    q = list(ur5_scene.home_q)
    n_workers = 8
    results: list[bool] = []
    lock = threading.Lock()

    def _check():
        r = ur5_checker.is_collision(q)
        with lock:
            results.append(r)

    with concurrent.futures.ThreadPoolExecutor(max_workers=n_workers) as pool:
        futs = [pool.submit(_check) for _ in range(n_workers)]
        for f in concurrent.futures.as_completed(futs, timeout=10.0):
            f.result()  # propagate any exceptions

    assert len(results) == n_workers
    # All results must be identical (determinism from a stable q)
    assert len(set(results)) == 1, f"Inconsistent results from workers: {results}"


def test_checker_can_be_created_on_main_thread_queried_from_worker(
    ur5_scene: SceneSnapshot,
) -> None:
    """Construction on main thread; query from a worker must not crash (risk #7)."""
    with CollisionChecker(ur5_scene) as checker:
        result_holder: list[bool] = []
        error_holder: list[Exception] = []

        def _worker():
            try:
                r = checker.is_collision(list(ur5_scene.home_q))
                result_holder.append(r)
            except Exception as e:  # noqa: BLE001
                error_holder.append(e)

        t = threading.Thread(target=_worker)
        t.start()
        t.join(timeout=5.0)

    assert error_holder == [], f"Worker raised: {error_holder}"
    assert len(result_holder) == 1


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_close_joins_worker_thread(ur5_scene: SceneSnapshot) -> None:
    checker = CollisionChecker(ur5_scene)
    # Get a reference to the worker thread BEFORE close.
    worker_thread = checker._thread
    checker.close()
    # After close, the thread should have stopped.
    assert not worker_thread.is_alive()


def test_close_is_idempotent(ur5_scene: SceneSnapshot) -> None:
    checker = CollisionChecker(ur5_scene)
    checker.close()
    checker.close()  # must not raise


def test_query_after_close_raises_runtime_error(ur5_scene: SceneSnapshot) -> None:
    checker = CollisionChecker(ur5_scene)
    checker.close()
    with pytest.raises(RuntimeError, match="closed"):
        checker.is_collision(list(ur5_scene.home_q))


def test_context_manager_auto_closes(ur5_scene: SceneSnapshot) -> None:
    with CollisionChecker(ur5_scene) as checker:
        q = list(ur5_scene.home_q)
        _ = checker.is_collision(q)
    # After exiting the context, the checker should be closed.
    with pytest.raises(RuntimeError):
        checker.is_collision(q)


# ---------------------------------------------------------------------------
# Worker-crash drain — risk #7
# ---------------------------------------------------------------------------


def test_worker_crash_drain_future_raises_runtime_error(ur5_scene: SceneSnapshot) -> None:
    """If the worker exits unexpectedly, pending Futures must raise RuntimeError.

    We simulate worker exit by posting the shutdown sentinel directly, then
    attempting a query. The drain loop in _worker's finally clause sets any
    remaining Futures with RuntimeError so callers don't block forever.
    """
    from src.planning.collision import _SHUTDOWN  # noqa: SLF001

    checker = CollisionChecker(ur5_scene)
    # Tell the worker to stop (simulate crash-like exit).
    checker._queue.put(_SHUTDOWN)
    # Wait for the worker to actually exit.
    checker._thread.join(timeout=5.0)

    # Now any new query must fail because the worker is dead.
    with pytest.raises(RuntimeError):
        checker.is_collision(list(ur5_scene.home_q))


# ---------------------------------------------------------------------------
# Independence from live SimRuntime (separate pybullet client)
# ---------------------------------------------------------------------------


def test_checker_uses_separate_pybullet_client(ur5_scene: SceneSnapshot) -> None:
    """Two CollisionCheckers for the same robot must operate independently.

    Both are given the same config but we can verify that independent
    construction does not fail (which would happen if they shared a client).
    """
    with CollisionChecker(ur5_scene) as checker1:
        with CollisionChecker(ur5_scene) as checker2:
            q = list(ur5_scene.home_q)
            r1 = checker1.is_collision(q)
            r2 = checker2.is_collision(q)
            # Same inputs must yield same boolean (determinism, risk #11).
            assert r1 == r2


# ---------------------------------------------------------------------------
# make_validity_fn
# ---------------------------------------------------------------------------


def test_make_validity_fn_returns_callable(ur5_checker: CollisionChecker) -> None:
    fn = ur5_checker.make_validity_fn()
    assert callable(fn)


def test_make_validity_fn_returns_true_for_valid_state(
    ur5_checker: CollisionChecker, ur5_scene: SceneSnapshot
) -> None:
    """A state not in collision should return True (valid) from validity fn."""
    fn = ur5_checker.make_validity_fn()
    q = list(ur5_scene.home_q)
    result = fn(q)
    # Home config is not in collision, so validity fn should return True
    assert result is True
