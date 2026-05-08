"""Demo: record a small motion sequence, persist it, and replay it.

This script exercises the Phase 2 :class:`Recorder` / :class:`Player` pair
without spinning up PyBullet. The driver is a ``MagicMock(spec=Driver)``
so the demo is self-contained: it shows the *shape* of the API and the
round-trip through JSON, then prints the resulting call log to stdout so
a human reader can verify the dispatch order.

Run with::

    python examples/demo_record_playback.py

Output is the recorded program (as a Procedure summary), the JSON file
path, and the sequence of mock-driver calls that ``Player.play_program``
made when replaying the loaded program.
"""

from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock

from src.drivers.base import Driver
from src.motion import (
    IOKind,
    Player,
    Recorder,
    SpeedData,
    ToolData,
    WObjData,
    ZoneData,
    ZoneKind,
    dump,
    load,
)


def _identity_quat() -> tuple[float, float, float, float]:
    return (1.0, 0.0, 0.0, 0.0)


def main() -> None:
    # ---- Recording ------------------------------------------------------
    tool = ToolData("gripper0", 0.5, (0.0, 0.0, 0.12), _identity_quat())
    wobj = WObjData("table0", (0.4, 0.0, 0.0), _identity_quat())

    rec = Recorder(
        default_tool=tool,
        default_wobj=wobj,
        default_speed=SpeedData(100.0),
        default_zone=ZoneData.fine(),
    )

    home_q = (0.0, -0.5, 0.5, 0.0, 1.0, 0.0)
    pick_xyz = (0.5, 0.0, 0.30)
    pick_approach_xyz = (0.5, 0.0, 0.40)

    rec.record_comment("Pick demo: home -> approach -> pick -> home")
    rec.record_move_joint(home_q)
    # Use a blend zone for the in-air approach for smoother motion.
    rec.set_zone(ZoneData(ZoneKind.RADIUS, 25.0))
    rec.record_move_linear(pick_approach_xyz, _identity_quat())
    # Tighten back to FINE for the actual pick.
    rec.set_zone(ZoneData.fine())
    rec.record_move_linear(pick_xyz, _identity_quat())
    rec.record_io("do_grip", 1, IOKind.SET)
    rec.record_wait(0.25)
    rec.record_move_linear(pick_approach_xyz, _identity_quat())
    rec.record_move_joint(home_q)

    program = rec.as_program(name="pick_demo")

    print("=== Recorded program ===")
    print(f"name: {program.name}")
    print(f"tools: {[t.name for t in program.tools]}")
    print(f"wobjs: {[w.name for w in program.wobjs]}")
    print(f"procedures: {[p.name for p in program.procedures]}")
    print(f"main body length: {len(program.procedures[0].body)} steps")

    # ---- Persist + reload ----------------------------------------------
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "recording.json")
        dump(program, path)
        size = os.path.getsize(path)
        print("\n=== Persisted ===")
        print(f"path: {path}")
        print(f"size: {size} bytes")

        loaded = load(path)
        assert loaded == program, "JSON round-trip did not preserve the program"
        print("round-trip equality: OK")

        # ---- Playback through a mock driver ----------------------------
        driver = MagicMock(spec=Driver)
        driver.name = "mock:demo"
        driver.dof = len(home_q)

        player = Player(driver)
        player.play_program(loaded, procedure_name="main", wait_each=True)

        print("\n=== Mock driver call log ===")
        for i, call in enumerate(driver.mock_calls):
            # mock_calls includes nested attribute accesses; filter to top-level.
            name = call[0]
            args = call[1]
            kwargs = call[2]
            if not name or "." in name:
                continue
            print(f"{i:02d}: {name}(args={args}, kwargs={kwargs})")


if __name__ == "__main__":
    main()
