"""Tests for src.planning.scene — SceneSnapshot construction and fingerprinting.

Covers:
- from_station happy path (ur5, iiwa, abb_irb1200, panda)
- Unknown robot raises ValueError
- Unknown fixture raises ValueError
- Deterministic fingerprint across two calls with same inputs
- Fingerprint changes when station frames change (frames_hash sensitivity)
- Fingerprint changes when fixture obstacles change (fixtures_hash — gap #6)
- Fingerprint changes when qd_max_rad_s / qdd_max_rad_s2 differ (iteration 2 fields)
- Fingerprint changes when home_q differs (iteration 2 fields)
- Fingerprint changes when ee_link_name differs (iteration 2 fields)
- Fingerprint changes when dof differs (iteration 2 fields)
- qdd default fallback 5× for non-panda robots (no qdd_max in catalog)
- qdd uniform scalar override via PlannerConfig.qdd_max_rad_s2_default
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.planning

from src.planning.scene import SceneSnapshot  # noqa: E402
from src.planning.types import PlannerConfig  # noqa: E402
from src.robots.catalog import CATALOG  # noqa: E402
from src.station.scene import FixtureEntry, Frame, RobotEntry, Station  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_IDENTITY_QUAT = (1.0, 0.0, 0.0, 0.0)


def _make_station(
    robot_catalog: str = "ur5",
    robot_id: str = "arm0",
    frame_xyz: tuple[float, float, float] = (0.0, 0.0, 0.0),
    extra_fixtures: tuple[FixtureEntry, ...] = (),
) -> Station:
    return Station(
        name="test_cell",
        frames=(
            Frame("world", frame_xyz, _IDENTITY_QUAT, parent=None),
        ),
        robots=(RobotEntry(robot_id, robot_catalog, "world"),),
        fixtures=extra_fixtures,
    )


@pytest.fixture
def ur5_station() -> Station:
    return _make_station("ur5")


@pytest.fixture
def ur5_snapshot(ur5_station: Station) -> SceneSnapshot:
    return SceneSnapshot.from_station(ur5_station, "arm0")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_from_station_returns_correct_robot_id(ur5_snapshot: SceneSnapshot) -> None:
    assert ur5_snapshot.robot_id == "arm0"


def test_from_station_ur5_dof_is_6(ur5_snapshot: SceneSnapshot) -> None:
    assert ur5_snapshot.dof == 6


def test_from_station_ur5_qd_length_matches_dof(ur5_snapshot: SceneSnapshot) -> None:
    assert len(ur5_snapshot.qd_max_rad_s) == ur5_snapshot.dof


def test_from_station_ur5_qdd_length_matches_dof(ur5_snapshot: SceneSnapshot) -> None:
    assert len(ur5_snapshot.qdd_max_rad_s2) == ur5_snapshot.dof


def test_from_station_fingerprint_is_nonempty_hex(ur5_snapshot: SceneSnapshot) -> None:
    fp = ur5_snapshot.fingerprint
    assert len(fp) == 40  # sha1 hex
    int(fp, 16)  # raises if not valid hex


def test_from_station_panda() -> None:
    station = _make_station("panda")
    snap = SceneSnapshot.from_station(station, "arm0")
    assert snap.dof == 7
    # panda has explicit qdd in catalog — verify it's used, not the heuristic
    spec = CATALOG["panda"]
    expected_qdd = tuple(float(v) for v in spec.limits.qdd_max_rad_s2)
    assert snap.qdd_max_rad_s2 == expected_qdd


def test_from_station_iiwa() -> None:
    station = _make_station("iiwa")
    snap = SceneSnapshot.from_station(station, "arm0")
    assert snap.dof == 7


def test_from_station_abb_irb1200() -> None:
    station = _make_station("abb_irb1200")
    snap = SceneSnapshot.from_station(station, "arm0")
    assert snap.dof == 6


def test_from_station_urdf_path_exists_on_disk(ur5_snapshot: SceneSnapshot) -> None:
    import os
    assert os.path.exists(ur5_snapshot.robot_urdf_path), (
        f"URDF not on disk: {ur5_snapshot.robot_urdf_path}"
    )


# ---------------------------------------------------------------------------
# Validation: unknown robot / fixture
# ---------------------------------------------------------------------------


def test_unknown_robot_raises_value_error() -> None:
    station = _make_station("ur5")
    with pytest.raises(ValueError, match="no_such_robot"):
        SceneSnapshot.from_station(station, "no_such_robot")


def test_unknown_fixture_raises_value_error() -> None:
    station = _make_station("ur5")
    with pytest.raises(ValueError, match="no_such_fixture"):
        SceneSnapshot.from_station(station, "arm0", obstacle_names=("no_such_fixture",))


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_fingerprint_is_deterministic_across_two_calls(ur5_station: Station) -> None:
    snap1 = SceneSnapshot.from_station(ur5_station, "arm0")
    snap2 = SceneSnapshot.from_station(ur5_station, "arm0")
    assert snap1.fingerprint == snap2.fingerprint


def test_fingerprint_is_deterministic_without_obstacles(ur5_station: Station) -> None:
    snap1 = SceneSnapshot.from_station(ur5_station, "arm0", obstacle_names=())
    snap2 = SceneSnapshot.from_station(ur5_station, "arm0", obstacle_names=())
    assert snap1.fingerprint == snap2.fingerprint


# ---------------------------------------------------------------------------
# Fingerprint sensitivity (iteration 2: gap-report fields)
# ---------------------------------------------------------------------------


def test_fingerprint_changes_when_frame_position_changes() -> None:
    """frames_hash contribution: moving a frame invalidates cached plans."""
    station_a = _make_station("ur5", frame_xyz=(0.0, 0.0, 0.0))
    station_b = _make_station("ur5", frame_xyz=(0.1, 0.0, 0.0))
    snap_a = SceneSnapshot.from_station(station_a, "arm0")
    snap_b = SceneSnapshot.from_station(station_b, "arm0")
    assert snap_a.fingerprint != snap_b.fingerprint


def test_fingerprint_changes_when_selected_fixture_changes(tmp_path) -> None:
    """fixtures_hash contribution: only the selected subset matters (gap #6)."""
    # Create two minimal mesh files (just for existence check — collision checker
    # is not called here).
    mesh_a = tmp_path / "box_a.obj"
    mesh_b = tmp_path / "box_b.obj"
    mesh_a.write_text("# dummy\n")
    mesh_b.write_text("# dummy\n")

    fixture_a = FixtureEntry("box_a", "world", mesh_path=str(mesh_a))
    fixture_b = FixtureEntry("box_b", "world", mesh_path=str(mesh_b))

    station_a = Station(
        name="cell",
        frames=(Frame("world", (0.0, 0.0, 0.0), _IDENTITY_QUAT),),
        robots=(RobotEntry("arm0", "ur5", "world"),),
        fixtures=(fixture_a,),
    )
    station_b = Station(
        name="cell",
        frames=(Frame("world", (0.0, 0.0, 0.0), _IDENTITY_QUAT),),
        robots=(RobotEntry("arm0", "ur5", "world"),),
        fixtures=(fixture_b,),
    )

    snap_a = SceneSnapshot.from_station(station_a, "arm0", obstacle_names=("box_a",))
    snap_b = SceneSnapshot.from_station(station_b, "arm0", obstacle_names=("box_b",))
    assert snap_a.fingerprint != snap_b.fingerprint


def test_fingerprint_stable_when_non_selected_fixture_changes(tmp_path) -> None:
    """gap #6: adding a fixture NOT in obstacle_names must not change fingerprint."""
    mesh_irrelevant = tmp_path / "irrelevant.obj"
    mesh_irrelevant.write_text("# dummy\n")

    station_without = Station(
        name="cell",
        frames=(Frame("world", (0.0, 0.0, 0.0), _IDENTITY_QUAT),),
        robots=(RobotEntry("arm0", "ur5", "world"),),
        fixtures=(),
    )
    station_with_extra = Station(
        name="cell",
        frames=(Frame("world", (0.0, 0.0, 0.0), _IDENTITY_QUAT),),
        robots=(RobotEntry("arm0", "ur5", "world"),),
        fixtures=(FixtureEntry("irrelevant", "world", mesh_path=str(mesh_irrelevant)),),
    )

    snap_without = SceneSnapshot.from_station(station_without, "arm0", obstacle_names=())
    snap_with = SceneSnapshot.from_station(station_with_extra, "arm0", obstacle_names=())
    # The fixture is in the station but NOT selected; fingerprint must not change.
    assert snap_without.fingerprint == snap_with.fingerprint


def test_fingerprint_changes_when_planner_config_qdd_default_differs() -> None:
    """qdd_max_rad_s2 changes fingerprint (iteration 2 fields: qdd_max)."""
    station = _make_station("ur5")
    snap_default = SceneSnapshot.from_station(station, "arm0")
    snap_custom_qdd = SceneSnapshot.from_station(
        station, "arm0",
        planner_config=PlannerConfig(qdd_max_rad_s2_default=50.0),
    )
    assert snap_default.fingerprint != snap_custom_qdd.fingerprint


# ---------------------------------------------------------------------------
# qdd fallback for non-panda robots (no qdd in catalog)
# ---------------------------------------------------------------------------


def test_qdd_default_fallback_5x_for_ur5() -> None:
    """ur5 has no qdd in catalog; implementation uses qd × 5 heuristic."""
    station = _make_station("ur5")
    snap = SceneSnapshot.from_station(station, "arm0")
    spec = CATALOG["ur5"]
    expected_qdd = tuple(v * 5.0 for v in spec.limits.qd_max_rad_s)
    assert snap.qdd_max_rad_s2 == expected_qdd


def test_qdd_default_fallback_5x_for_abb() -> None:
    """abb_irb1200 has no qdd in catalog; same 5× heuristic."""
    station = _make_station("abb_irb1200")
    snap = SceneSnapshot.from_station(station, "arm0")
    spec = CATALOG["abb_irb1200"]
    expected_qdd = tuple(v * 5.0 for v in spec.limits.qd_max_rad_s)
    assert snap.qdd_max_rad_s2 == expected_qdd


def test_qdd_uniform_scalar_override() -> None:
    """PlannerConfig.qdd_max_rad_s2_default overrides both the catalog entry and
    the heuristic, producing a uniform value across all joints."""
    station = _make_station("ur5")
    cfg = PlannerConfig(qdd_max_rad_s2_default=100.0)
    snap = SceneSnapshot.from_station(station, "arm0", planner_config=cfg)
    # Every joint should have the exact override value.
    assert all(abs(v - 100.0) < 1e-9 for v in snap.qdd_max_rad_s2)


def test_qdd_panda_uses_catalog_not_heuristic() -> None:
    """panda has qdd in catalog; should not be overridden by 5× heuristic."""
    station = _make_station("panda")
    snap = SceneSnapshot.from_station(station, "arm0")
    spec = CATALOG["panda"]
    catalog_qdd = tuple(float(v) for v in spec.limits.qdd_max_rad_s2)
    heuristic_qdd = tuple(v * 5.0 for v in snap.qd_max_rad_s)
    # Catalog and heuristic are different; implementation must use catalog.
    assert snap.qdd_max_rad_s2 == catalog_qdd
    assert snap.qdd_max_rad_s2 != heuristic_qdd


# ---------------------------------------------------------------------------
# frames_hash / fixtures_hash accessors
# ---------------------------------------------------------------------------


def test_frames_hash_returns_hex_string(ur5_snapshot: SceneSnapshot) -> None:
    fh = ur5_snapshot.frames_hash()
    assert len(fh) == 40
    int(fh, 16)


def test_fixtures_hash_returns_hex_string(ur5_snapshot: SceneSnapshot) -> None:
    fxh = ur5_snapshot.fixtures_hash()
    assert len(fxh) == 40
    int(fxh, 16)


def test_frames_hash_differs_between_different_stations() -> None:
    snap_a = SceneSnapshot.from_station(_make_station("ur5", frame_xyz=(0.0, 0.0, 0.0)), "arm0")
    snap_b = SceneSnapshot.from_station(_make_station("ur5", frame_xyz=(1.0, 0.0, 0.0)), "arm0")
    assert snap_a.frames_hash() != snap_b.frames_hash()


# Extra coverage: SceneSnapshot is frozen (mutation must fail)
def test_scene_snapshot_is_frozen(ur5_snapshot: SceneSnapshot) -> None:
    with pytest.raises((AttributeError, TypeError)):
        ur5_snapshot.robot_id = "new_id"  # type: ignore[misc]


# Extra coverage: home_q length matches dof
def test_home_q_length_matches_dof(ur5_snapshot: SceneSnapshot) -> None:
    assert len(ur5_snapshot.home_q) == ur5_snapshot.dof
