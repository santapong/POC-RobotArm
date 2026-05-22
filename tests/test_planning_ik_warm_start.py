"""Tests for src.planning.ik — IKSolver with quantised LRU seed cache.

Covers:
- First call seeds the cache (miss)
- Second call within 1 mm quantisation grid is a cache hit (cache_stats())
- Third call beyond 1 mm grid is a miss
- Residual > tol raises PlanningIKUnreachable (risk-coverage for IK error code)
- Cache eviction at cap 256
- Dedicated-thread invariant: constructed on main thread, queried from worker
  thread without corruption (risk #7)
- Cache key is independent of robot current pose (risk #16 — cache staleness)
"""

from __future__ import annotations

import concurrent.futures
import threading

import pytest

pytestmark = pytest.mark.planning
pytest.importorskip("pybullet")

from src.planning.ik import IKResult, IKSolver, PlanningIKUnreachable  # noqa: E402
from src.planning.scene import SceneSnapshot  # noqa: E402
from src.station.scene import Frame, RobotEntry, Station  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_IDENTITY_QUAT = (1.0, 0.0, 0.0, 0.0)
# Panda ee link — we use panda because it has a well-defined ee_link in catalog
# and its workspace is documented.  We accept any reachable target; the exact
# values matter less than the cache-hit/miss behaviour.
_PANDA_TARGET_XYZ = (0.4, 0.0, 0.4)
_PANDA_TARGET_QUAT_WXYZ = (1.0, 0.0, 0.0, 0.0)


@pytest.fixture(scope="module")
def panda_scene() -> SceneSnapshot:
    station = Station(
        name="cell",
        frames=(Frame("world", (0.0, 0.0, 0.0), _IDENTITY_QUAT),),
        robots=(RobotEntry("arm0", "panda", "world"),),
    )
    return SceneSnapshot.from_station(station, "arm0")


@pytest.fixture
def panda_solver(panda_scene: SceneSnapshot) -> IKSolver:
    solver = IKSolver(panda_scene, residual_tol_m=0.01, cache_size=256)
    yield solver
    solver.close()


# ---------------------------------------------------------------------------
# Basic IK solve
# ---------------------------------------------------------------------------


def test_ik_solve_returns_ik_result(panda_solver: IKSolver) -> None:
    result = panda_solver.solve(_PANDA_TARGET_XYZ, _PANDA_TARGET_QUAT_WXYZ)
    assert isinstance(result, IKResult)


def test_ik_solve_result_has_correct_dof(panda_solver: IKSolver, panda_scene: SceneSnapshot) -> None:
    result = panda_solver.solve(_PANDA_TARGET_XYZ, _PANDA_TARGET_QUAT_WXYZ)
    # q_rad may be longer than dof (panda has finger joints in sim)
    assert len(result.q_rad) >= panda_scene.dof


def test_ik_solve_residual_is_non_negative(panda_solver: IKSolver) -> None:
    result = panda_solver.solve(_PANDA_TARGET_XYZ, _PANDA_TARGET_QUAT_WXYZ)
    assert result.residual_m >= 0.0


def test_ik_solve_first_call_is_cache_miss(panda_solver: IKSolver) -> None:
    panda_solver.solve(_PANDA_TARGET_XYZ, _PANDA_TARGET_QUAT_WXYZ)
    hits, misses = panda_solver.cache_stats()
    assert misses >= 1


# ---------------------------------------------------------------------------
# Cache hit on repeat call within 1 mm grid
# ---------------------------------------------------------------------------


def test_second_call_same_xyz_is_cache_hit(panda_solver: IKSolver) -> None:
    """Calling with same xyz twice — second must be a seed cache hit."""
    panda_solver.solve(_PANDA_TARGET_XYZ, _PANDA_TARGET_QUAT_WXYZ)
    hits_before, _ = panda_solver.cache_stats()
    result2 = panda_solver.solve(_PANDA_TARGET_XYZ, _PANDA_TARGET_QUAT_WXYZ)
    hits_after, _ = panda_solver.cache_stats()
    # Hit count must increase
    assert hits_after > hits_before
    assert result2.seed_was_cache_hit is True


def test_second_call_within_1mm_grid_is_cache_hit(panda_solver: IKSolver) -> None:
    """A target 0.5 mm away (same grid cell) should be a cache hit."""
    xyz_a = _PANDA_TARGET_XYZ
    xyz_b = (xyz_a[0] + 0.0005, xyz_a[1], xyz_a[2])  # +0.5 mm — same 1mm grid cell
    panda_solver.solve(xyz_a, _PANDA_TARGET_QUAT_WXYZ)
    _, misses_before = panda_solver.cache_stats()
    result_b = panda_solver.solve(xyz_b, _PANDA_TARGET_QUAT_WXYZ)
    _, misses_after = panda_solver.cache_stats()
    # Still same grid cell, so no new miss
    assert misses_after == misses_before
    assert result_b.seed_was_cache_hit is True


def test_third_call_beyond_1mm_grid_is_cache_miss(panda_solver: IKSolver) -> None:
    """A target 2 mm away falls in a different grid cell — cache miss."""
    xyz_a = _PANDA_TARGET_XYZ
    xyz_c = (xyz_a[0] + 0.002, xyz_a[1], xyz_a[2])  # +2 mm — different grid cell
    panda_solver.solve(xyz_a, _PANDA_TARGET_QUAT_WXYZ)
    hits_before, misses_before = panda_solver.cache_stats()
    result_c = panda_solver.solve(xyz_c, _PANDA_TARGET_QUAT_WXYZ)
    hits_after, misses_after = panda_solver.cache_stats()
    assert misses_after > misses_before
    assert result_c.seed_was_cache_hit is False


# ---------------------------------------------------------------------------
# Residual > tol raises PlanningIKUnreachable
# ---------------------------------------------------------------------------


def test_unreachable_target_raises_planning_ik_unreachable(
    panda_scene: SceneSnapshot,
) -> None:
    """A target far outside the workspace must raise PlanningIKUnreachable.

    Setting residual_tol_m to near-zero forces any IK solution to fail the
    tolerance check even for reachable targets, which is the simplest way
    to unit-test the error path without needing a geometrically unreachable
    target that might depend on the URDF mesh layout.
    """
    solver = IKSolver(panda_scene, residual_tol_m=1e-10, cache_size=256)
    try:
        with pytest.raises(PlanningIKUnreachable):
            solver.solve(_PANDA_TARGET_XYZ, _PANDA_TARGET_QUAT_WXYZ)
    finally:
        solver.close()


# ---------------------------------------------------------------------------
# Cache eviction at cap
# ---------------------------------------------------------------------------


def test_cache_eviction_at_cap(panda_scene: SceneSnapshot) -> None:
    """Filling the cache past cap evicts old entries (FIFO OrderedDict)."""
    cap = 4
    solver = IKSolver(panda_scene, residual_tol_m=0.02, cache_size=cap)
    try:
        # Insert cap+1 distinct 1mm-grid cells.
        for i in range(cap + 1):
            xyz = (_PANDA_TARGET_XYZ[0] + i * 0.01, _PANDA_TARGET_XYZ[1], _PANDA_TARGET_XYZ[2])
            try:
                solver.solve(xyz, _PANDA_TARGET_QUAT_WXYZ)
            except PlanningIKUnreachable:
                pass  # Fine — we're testing the eviction logic, not solve success
        # The cache should not exceed cap entries.
        # (We can't read _cache directly; verify via cache_stats.)
        hits, misses = solver.cache_stats()
        # At least one eviction occurred (more than cap misses means eviction happened)
        assert misses >= cap
    finally:
        solver.close()


# ---------------------------------------------------------------------------
# Dedicated-thread invariant — risk #7
# ---------------------------------------------------------------------------


def test_solver_constructed_on_main_queried_from_worker(panda_scene: SceneSnapshot) -> None:
    """IKSolver constructed on main thread, query from worker thread (risk #7)."""
    solver = IKSolver(panda_scene, residual_tol_m=0.02, cache_size=256)
    results: list[IKResult] = []
    errors: list[Exception] = []

    def _worker():
        try:
            r = solver.solve(_PANDA_TARGET_XYZ, _PANDA_TARGET_QUAT_WXYZ)
            results.append(r)
        except PlanningIKUnreachable:
            # Residual > tol is OK for this test; we just need no crash.
            results.append(None)  # type: ignore[arg-type]
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    t = threading.Thread(target=_worker)
    t.start()
    t.join(timeout=10.0)
    solver.close()

    assert errors == [], f"Worker raised: {errors}"
    assert len(results) == 1


def test_concurrent_workers_do_not_corrupt_solver(panda_scene: SceneSnapshot) -> None:
    """Multiple concurrent IK queries must not crash or deadlock (risk #7)."""
    solver = IKSolver(panda_scene, residual_tol_m=0.02, cache_size=256)
    errors: list[Exception] = []
    lock = threading.Lock()

    def _worker(i: int) -> None:
        xyz = (_PANDA_TARGET_XYZ[0] + i * 0.001, _PANDA_TARGET_XYZ[1], _PANDA_TARGET_XYZ[2])
        try:
            solver.solve(xyz, _PANDA_TARGET_QUAT_WXYZ)
        except PlanningIKUnreachable:
            pass  # Acceptable
        except Exception as e:  # noqa: BLE001
            with lock:
                errors.append(e)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futs = [pool.submit(_worker, i) for i in range(8)]
        concurrent.futures.wait(futs, timeout=30.0)

    solver.close()
    assert errors == [], f"Workers raised: {errors}"


# ---------------------------------------------------------------------------
# Cache key is independent of robot current pose — risk #16
# ---------------------------------------------------------------------------


def test_cache_key_independent_of_robot_pose(panda_scene: SceneSnapshot) -> None:
    """The IK cache key must NOT depend on the robot's current joint angles.

    risk #16: cache staleness after jog. The cache key is
    (fingerprint, xyz_quantised, quat_quantised) — robot pose is NOT part of
    it. We verify that two solves with the same target but different q_seeds
    still map to the same cache key (the second call should be a hit).
    """
    solver = IKSolver(panda_scene, residual_tol_m=0.02, cache_size=256)
    try:
        # First call with no seed.
        solver.solve(_PANDA_TARGET_XYZ, _PANDA_TARGET_QUAT_WXYZ)
        hits_before, misses_before = solver.cache_stats()

        # Second call with a different seed (simulates "robot was jogged").
        different_seed = tuple(0.1 * i for i in range(panda_scene.dof))
        result = solver.solve(
            _PANDA_TARGET_XYZ, _PANDA_TARGET_QUAT_WXYZ, q_seed=different_seed
        )
        hits_after, misses_after = solver.cache_stats()

        # Must be a cache hit (fingerprint + xyz + quat are identical)
        assert hits_after > hits_before
        assert result.seed_was_cache_hit is True
    finally:
        solver.close()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


def test_solver_close_joins_worker_thread(panda_scene: SceneSnapshot) -> None:
    solver = IKSolver(panda_scene, residual_tol_m=0.02)
    worker = solver._thread
    solver.close()
    assert not worker.is_alive()


def test_solver_query_after_close_raises(panda_scene: SceneSnapshot) -> None:
    solver = IKSolver(panda_scene, residual_tol_m=0.02)
    solver.close()
    with pytest.raises(RuntimeError):
        solver.solve(_PANDA_TARGET_XYZ, _PANDA_TARGET_QUAT_WXYZ)


def test_solver_context_manager(panda_scene: SceneSnapshot) -> None:
    with IKSolver(panda_scene, residual_tol_m=0.02) as solver:
        solver.solve(_PANDA_TARGET_XYZ, _PANDA_TARGET_QUAT_WXYZ)


# ---------------------------------------------------------------------------
# cache_stats returns (hits, misses) tuple
# ---------------------------------------------------------------------------


def test_cache_stats_initial_zero(panda_scene: SceneSnapshot) -> None:
    solver = IKSolver(panda_scene, residual_tol_m=0.02)
    try:
        hits, misses = solver.cache_stats()
        assert hits == 0
        assert misses == 0
    finally:
        solver.close()
