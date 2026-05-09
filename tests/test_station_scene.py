"""Tests for the station scene-graph (src.station.scene)."""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from src.station.scene import (
    FixtureEntry,
    Frame,
    IOSignal,
    RobotEntry,
    Station,
    ToolEntry,
    WorkpieceEntry,
    dump,
    from_dict,
    load,
    to_dict,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _identity_quat() -> tuple[float, float, float, float]:
    return (1.0, 0.0, 0.0, 0.0)


def _make_station() -> Station:
    frames = (
        Frame("world", (0.0, 0.0, 0.0), _identity_quat(), parent=None),
        Frame("robot_base", (0.0, 0.0, 0.0), _identity_quat(), parent="world"),
        Frame("table", (0.5, 0.0, 0.0), _identity_quat(), parent="world"),
        Frame("flange", (0.0, 0.0, 0.9), _identity_quat(), parent="robot_base"),
    )
    return Station(
        name="cell",
        frames=frames,
        robots=(RobotEntry("arm0", "abb_irb1200", "robot_base"),),
        tools=(
            ToolEntry(
                "gripper",
                "flange",
                mesh_path=None,
                tcp_xyz_m=(0.0, 0.0, 0.12),
                tcp_quat_wxyz=_identity_quat(),
            ),
        ),
        workpieces=(WorkpieceEntry("part", "table"),),
        fixtures=(FixtureEntry("jig", "table"),),
        io_signals=(
            IOSignal("do_grip", "DO", default_value=0),
            IOSignal("ai_load", "AI", default_value=0.0),
        ),
    )


# ---------------------------------------------------------------------------
# 1. Construction / hashability
# ---------------------------------------------------------------------------


def test_construct_each_dataclass_and_station():
    """Every leaf dataclass can be built; Station composes them cleanly."""
    fr = Frame("a", (0.0, 0.0, 0.0), _identity_quat())
    fr_child = Frame("b", (0.1, 0.0, 0.0), _identity_quat(), parent="a")
    robot = RobotEntry("r0", "panda", "a")
    tool = ToolEntry("t0", "a")
    wp = WorkpieceEntry("w0", "a")
    fx = FixtureEntry("f0", "a")
    sig_di = IOSignal("di0", "DI", default_value=True)
    sig_ao = IOSignal("ao0", "AO", default_value=0.5)

    station = Station(
        "x",
        frames=(fr, fr_child),
        robots=(robot,),
        tools=(tool,),
        workpieces=(wp,),
        fixtures=(fx,),
        io_signals=(sig_di, sig_ao),
    )

    # Frozen dataclass invariant: every entity must be hashable.
    for obj in (fr, fr_child, robot, tool, wp, fx, sig_di, sig_ao, station):
        hash(obj)
    assert station.frames[1].parent == "a"


# ---------------------------------------------------------------------------
# 2. Validation: empty names
# ---------------------------------------------------------------------------


def test_validation_rejects_empty_names():
    with pytest.raises(ValueError, match="Frame.name"):
        Frame("", (0.0, 0.0, 0.0), _identity_quat())
    with pytest.raises(ValueError, match="RobotEntry.name"):
        RobotEntry("", "panda", "world")
    with pytest.raises(ValueError, match="ToolEntry.name"):
        ToolEntry("", "world")
    with pytest.raises(ValueError, match="WorkpieceEntry.name"):
        WorkpieceEntry("", "world")
    with pytest.raises(ValueError, match="FixtureEntry.name"):
        FixtureEntry("", "world")
    with pytest.raises(ValueError, match="IOSignal.name"):
        IOSignal("", "DI")
    with pytest.raises(ValueError, match="Station.name"):
        Station("")


# ---------------------------------------------------------------------------
# 3. Validation: bad quaternion in Frame / Tool
# ---------------------------------------------------------------------------


def test_validation_rejects_non_unit_quaternions():
    with pytest.raises(ValueError, match="unit-norm"):
        Frame("a", (0.0, 0.0, 0.0), (1.0, 1.0, 0.0, 0.0))
    with pytest.raises(ValueError, match="unit-norm"):
        ToolEntry(
            "t", "world", tcp_quat_wxyz=(0.5, 0.0, 0.0, 0.0)
        )


def test_validation_rejects_wrong_length_quaternion():
    with pytest.raises(ValueError, match="length 4"):
        Frame("a", (0.0, 0.0, 0.0), (1.0, 0.0, 0.0))


# ---------------------------------------------------------------------------
# 4. Validation: I/O kind / value
# ---------------------------------------------------------------------------


def test_validation_io_signal_kind_and_value():
    # Bogus kind is rejected.
    with pytest.raises(ValueError, match="kind must be"):
        IOSignal("x", "GO")  # type: ignore[arg-type]
    # Non-numeric default_value is rejected.
    with pytest.raises(ValueError, match="default_value"):
        IOSignal("x", "DO", default_value="high")  # type: ignore[arg-type]
    # All four legal kinds work with the dataclass-default value (0).
    for kind in ("DI", "DO", "AI", "AO"):
        sig = IOSignal(f"s_{kind}", kind)  # type: ignore[arg-type]
        assert sig.kind == kind


# Audit must-fix #5: cross-check ``kind`` against ``default_value`` type.
# Earlier the validator only checked that the value was int/float/bool, which
# let bool slip through int (Python's `bool` is a subclass of `int`) and let
# float silently "default" a digital signal.


def test_iosignal_digital_rejects_float_default():
    """A DI/DO signal with a float default is meaningless."""
    for kind in ("DI", "DO"):
        with pytest.raises(ValueError, match="digital"):
            IOSignal("x", kind, default_value=0.5)  # type: ignore[arg-type]


def test_iosignal_digital_rejects_out_of_range_int():
    """A DI/DO signal must default to 0, 1, True, or False (not e.g. 2 or -1)."""
    for kind, bad in (("DO", 2), ("DI", -1)):
        with pytest.raises(ValueError, match="digital"):
            IOSignal("x", kind, default_value=bad)  # type: ignore[arg-type]


def test_iosignal_digital_accepts_bool_or_zero_one():
    """Legal digital defaults: True, False, 0, 1."""
    for value in (True, False, 0, 1):
        sig = IOSignal("x", "DO", default_value=value)
        assert sig.default_value == value


def test_iosignal_analog_rejects_bool_default():
    """An AI/AO signal with a bool default would be silently coerced to 0/1."""
    for kind in ("AI", "AO"):
        with pytest.raises(ValueError, match="bool"):
            IOSignal("x", kind, default_value=True)  # type: ignore[arg-type]


def test_iosignal_analog_accepts_int_or_float():
    """Legal analog defaults: any int or float."""
    for value in (0, 1, -3, 0.0, 3.14, -2.7):
        sig = IOSignal("x", "AI", default_value=value)
        assert sig.default_value == value


# ---------------------------------------------------------------------------
# 5. Referential integrity: dangling parents fail at Station build time
# ---------------------------------------------------------------------------


def test_station_rejects_dangling_frame_parent():
    """A Frame whose parent doesn't exist must raise."""
    fr0 = Frame("a", (0.0, 0.0, 0.0), _identity_quat())
    fr1 = Frame("b", (0.0, 0.0, 0.0), _identity_quat(), parent="ghost")
    with pytest.raises(ValueError, match="unknown parent"):
        Station("s", frames=(fr0, fr1))


def test_station_rejects_dangling_robot_base_frame():
    fr0 = Frame("a", (0.0, 0.0, 0.0), _identity_quat())
    bad = RobotEntry("r0", "panda", "ghost")
    with pytest.raises(ValueError, match="references unknown frame"):
        Station("s", frames=(fr0,), robots=(bad,))


def test_station_rejects_dangling_tool_workpiece_fixture():
    fr0 = Frame("a", (0.0, 0.0, 0.0), _identity_quat())
    with pytest.raises(ValueError, match="references unknown frame"):
        Station(
            "s", frames=(fr0,), tools=(ToolEntry("t0", "ghost"),)
        )
    with pytest.raises(ValueError, match="references unknown frame"):
        Station(
            "s", frames=(fr0,), workpieces=(WorkpieceEntry("w0", "ghost"),)
        )
    with pytest.raises(ValueError, match="references unknown frame"):
        Station(
            "s", frames=(fr0,), fixtures=(FixtureEntry("f0", "ghost"),)
        )


def test_station_rejects_duplicate_frame_names():
    fr0 = Frame("dup", (0.0, 0.0, 0.0), _identity_quat())
    fr1 = Frame("dup", (1.0, 0.0, 0.0), _identity_quat())
    with pytest.raises(ValueError, match="duplicate"):
        Station("s", frames=(fr0, fr1))


def test_station_rejects_duplicate_robot_names():
    fr0 = Frame("a", (0.0, 0.0, 0.0), _identity_quat())
    r0 = RobotEntry("r0", "panda", "a")
    r1 = RobotEntry("r0", "ur5", "a")
    with pytest.raises(ValueError, match="duplicate"):
        Station("s", frames=(fr0,), robots=(r0, r1))


# ---------------------------------------------------------------------------
# 6. JSON dict round-trip preserves equality
# ---------------------------------------------------------------------------


def test_to_dict_from_dict_round_trip():
    station = _make_station()
    encoded = to_dict(station)
    # Encoded is JSON-friendly primitives only.
    s = json.dumps(encoded)
    decoded = from_dict(json.loads(s), Station)
    assert isinstance(decoded, Station)
    assert decoded == station


def test_to_dict_includes_type_discriminators():
    station = _make_station()
    encoded = to_dict(station)
    assert encoded["__type__"] == "Station"
    assert encoded["frames"][0]["__type__"] == "Frame"
    assert encoded["robots"][0]["__type__"] == "RobotEntry"
    assert encoded["tools"][0]["__type__"] == "ToolEntry"
    assert encoded["io_signals"][0]["__type__"] == "IOSignal"


# ---------------------------------------------------------------------------
# 7. JSON file dump/load round-trip
# ---------------------------------------------------------------------------


def test_dump_load_file_round_trip():
    station = _make_station()
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "station.json")
        dump(station, path)
        assert os.path.isfile(path)
        loaded = load(path)
        assert isinstance(loaded, Station)
        assert loaded == station


def test_dump_rejects_non_station():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "x.json")
        with pytest.raises(TypeError, match="expects a Station"):
            dump(object(), path)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 8. Forward-compat: unknown JSON keys are ignored gracefully
# ---------------------------------------------------------------------------


def test_from_dict_ignores_unknown_keys():
    station = _make_station()
    encoded = to_dict(station)
    encoded["future_only_field"] = "ignored"
    encoded["frames"][0]["new_attr"] = 123
    decoded = from_dict(encoded, Station)
    assert decoded == station
