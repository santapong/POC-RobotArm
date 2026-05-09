"""Headless scene-graph demo: build, save, load, compare a station.

Run from the repo root::

    python examples/demo_station_save_load.py

This script intentionally does not import any Qt module: it exercises
only :mod:`src.station.scene` so it runs cleanly on headless boxes
(CI, ssh sessions, sandboxed agents). It writes ``tmp_station.json``
into a temporary directory, loads it back, asserts equality with the
in-memory station, and prints a one-line summary per stage.
"""

from __future__ import annotations

import os
import tempfile

from src.station.scene import (
    FixtureEntry,
    Frame,
    IOSignal,
    RobotEntry,
    Station,
    ToolEntry,
    WorkpieceEntry,
    dump,
    load,
)


def build_demo_station() -> Station:
    """Construct a small but representative pick-and-place station."""
    frames = (
        Frame("world", (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0), parent=None),
        Frame("robot_base", (0.0, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0), parent="world"),
        Frame("table", (0.5, 0.0, 0.0), (1.0, 0.0, 0.0, 0.0), parent="world"),
        Frame("flange", (0.0, 0.0, 0.9), (1.0, 0.0, 0.0, 0.0), parent="robot_base"),
    )
    robots = (RobotEntry("arm0", "abb_irb1200", "robot_base"),)
    tools = (
        ToolEntry(
            name="gripper",
            parent_frame="flange",
            mesh_path=None,
            tcp_xyz_m=(0.0, 0.0, 0.12),
            tcp_quat_wxyz=(1.0, 0.0, 0.0, 0.0),
        ),
    )
    fixtures = (FixtureEntry("jig", "table", mesh_path=None),)
    workpieces = (WorkpieceEntry("part0", "table", mesh_path=None),)
    io_signals = (
        IOSignal("do_grip", "DO", default_value=0),
        IOSignal("di_part_present", "DI", default_value=False),
    )
    return Station(
        name="demo_station",
        frames=frames,
        robots=robots,
        tools=tools,
        workpieces=workpieces,
        fixtures=fixtures,
        io_signals=io_signals,
    )


def main() -> None:
    station = build_demo_station()
    print(
        f"Built station {station.name!r}: "
        f"{len(station.frames)} frames, "
        f"{len(station.robots)} robots, "
        f"{len(station.tools)} tools, "
        f"{len(station.workpieces)} workpieces, "
        f"{len(station.fixtures)} fixtures, "
        f"{len(station.io_signals)} IO signals."
    )

    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "tmp_station.json")
        dump(station, path)
        size = os.path.getsize(path)
        print(f"Wrote {path} ({size} bytes).")

        reloaded = load(path)
        print(f"Reloaded station {reloaded.name!r} from disk.")

        assert reloaded == station, "Round-trip changed the station object"
        print("Round-trip OK: reloaded == original.")


if __name__ == "__main__":
    main()
