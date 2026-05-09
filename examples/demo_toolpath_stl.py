"""End-to-end CAM pipeline demo.

Builds a synthetic STL part, generates a surface-raster toolpath,
runs DP redundancy resolution against the IRB 1200, and emits ABB RAPID
for the resulting Cartesian moves.

Run from the repo root::

    python examples/demo_toolpath_stl.py
"""

from __future__ import annotations

import os
import tempfile

import numpy as np
import trimesh

from src.motion.ir import (
    Move,
    MoveKind,
    Procedure,
    Program,
    SpeedData,
    ToolData,
    WObjData,
    ZoneData,
)
from src.post import RAPIDPost
from src.robots.predefined import get_robot
from src.toolpath.operations import surface_raster
from src.toolpath.optimizer import optimize_joints


def _make_part_stl(out_dir: str) -> str:
    """Generate a small box STL on disk and return its path."""
    box = trimesh.creation.box(extents=(0.2, 0.1, 0.05))
    box.apply_translation([0.5, 0.0, 0.1])
    path = os.path.join(out_dir, "part.stl")
    box.export(path)
    return path


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        stl_path = _make_part_stl(tmp)
        print(f"Wrote synthetic part: {stl_path}")

        # Load the part and slice its top face.
        mesh = trimesh.load_mesh(stl_path)
        # Slice with planes parallel to YZ — gives a serpentine over the top face.
        # The top face sits at Z = 0.125; we slice along Y axis with step 20 mm.
        waypoints = surface_raster(
            mesh,
            plane_normal=(0.0, 1.0, 0.0),
            plane_origin=(0.0, -0.05, 0.125),
            step_m=0.02,
            normal_offset_m=0.005,  # 5 mm standoff
        )
        print(f"Generated {len(waypoints)} surface_raster waypoints")

        # Run the DP redundancy resolver against the IRB 1200.
        try:
            robot = get_robot("abb_irb1200")
        except Exception as exc:
            print(f"# Failed to load IRB 1200: {exc}")
            return

        try:
            joints = optimize_joints(
                robot,
                waypoints,
                phi_step_deg=15.0,
                manipulability_min=1e-4,
            )
        except ValueError as exc:
            # Some waypoints may be unreachable; that's expected for the
            # demo's tight workspace. Trim to what fits.
            print(f"# DP optimizer found infeasible waypoints: {exc}")
            print("# Re-running with the first reachable subset...")
            feasible: list = []
            from src.toolpath.optimizer import _ik_candidates
            phis = np.linspace(0.0, 2.0 * np.pi, 24, endpoint=False)
            seed = np.zeros(robot.n)
            for wp in waypoints:
                cands = _ik_candidates(robot, wp, phis, 1e-4, seed)
                if cands:
                    feasible.append(wp)
                    seed = max(cands, key=lambda c: c[1])[0]
            waypoints = feasible
            joints = optimize_joints(
                robot,
                waypoints,
                phi_step_deg=15.0,
                manipulability_min=1e-4,
            )
        print(f"DP joint trajectory length: {len(joints)}")

        # Build an IR Program — every waypoint becomes a MoveL.
        tool = ToolData(
            name="tMill",
            mass_kg=0.5,
            tcp_xyz_m=(0.0, 0.0, 0.05),
            tcp_quat_wxyz=(1.0, 0.0, 0.0, 0.0),
        )
        wobj = WObjData(
            name="wPart",
            base_xyz_m=(0.0, 0.0, 0.0),
            base_quat_wxyz=(1.0, 0.0, 0.0, 0.0),
        )
        speed = SpeedData(50.0)  # 50 mm/s — typical surface raster
        zone = ZoneData(ZoneData.RADIUS, 1.0)

        body = [
            Move(MoveKind.MOVE_L, wp, speed, zone, tool, wobj)
            for wp in waypoints
        ]
        program = Program(
            name="ToolpathDemo",
            modules_metadata={
                "target_robot": "ABB IRB 1200-5/0.9",
                "operation": "surface_raster",
                "waypoints": str(len(waypoints)),
            },
            tools=[tool],
            wobjs=[wobj],
            procedures=[Procedure("main", body=body)],
        )
        print(f"Program built with {len(body)} moves.")

        rapid = RAPIDPost().emit(program)
        print("# First 5 lines of RAPID:")
        for line in rapid.splitlines()[:5]:
            print(line)

        out = os.path.join(os.path.dirname(__file__), "toolpath_demo.mod")
        RAPIDPost().emit_to_file(program, out)
        print(f"# Wrote {out}")


if __name__ == "__main__":
    main()
