"""Demo: build a square TCP path, interpolate it, and optionally replay it.

This script exercises the PR-B :func:`~src.motion.path.interpolate_program`
API by constructing a 4-corner square MOVE_L program, sampling it at 20 ms,
and (when pybullet is available) replaying the trajectory through a
:class:`~src.drivers.sim.sim_sampled_path.SimSampledPathDriver`.

Run with::

    python examples/demo_path_calculation.py

Output includes sample count, total duration, and maximum observed joint
velocity across the path.
"""

from __future__ import annotations


def _identity_quat() -> tuple[float, float, float, float]:
    return (1.0, 0.0, 0.0, 0.0)


def main() -> None:
    # ---- Build robot -------------------------------------------------------
    from src.robots.predefined import get_robot

    robot = get_robot("panda")

    # ---- Build a square TCP path Program ------------------------------------
    from src.motion.ir import (
        Move,
        MoveKind,
        PoseTarget,
        Procedure,
        Program,
        SpeedData,
        ToolData,
        WObjData,
        ZoneData,
    )

    tool = ToolData("tool0", 0.001, (0.0, 0.0, 0.0), _identity_quat())
    wobj = WObjData("wobj0", (0.0, 0.0, 0.0), _identity_quat())
    speed = SpeedData(v_tcp_mm_s=50.0)
    zone = ZoneData.fine()

    # Square corners in the base frame (metres): 20 cm side, centred at (0.4, 0, 0.4)
    corners = [
        (0.4,  0.1, 0.4),
        (0.4, -0.1, 0.4),
        (0.4, -0.1, 0.2),
        (0.4,  0.1, 0.2),
    ]

    moves = [
        Move(
            kind=MoveKind.MOVE_L,
            target=PoseTarget(xyz_m=corner, quat_wxyz=_identity_quat()),
            speed=speed,
            zone=zone,
            tool=tool,
            wobj=wobj,
        )
        for corner in corners
    ]

    proc = Procedure(name="main", body=tuple(moves))
    prog = Program(name="square_tcp", procedures=(proc,))

    # ---- Interpolate -------------------------------------------------------
    from src.motion.path import interpolate_program

    print("Interpolating square TCP path ...")
    path = interpolate_program(prog, robot, dt_s=0.02, raise_on_violation=False)

    total_time = path.samples[-1].t_s if path.samples else 0.0
    print(f"  samples:    {len(path.samples)}")
    print(f"  total time: {total_time:.3f} s")
    print(f"  violations: {len(path.violations)}")

    # ---- Max joint velocity ------------------------------------------------
    if len(path.samples) >= 2:
        max_qd = 0.0
        for k in range(len(path.samples) - 1):
            s0 = path.samples[k]
            s1 = path.samples[k + 1]
            dt = s1.t_s - s0.t_s
            if dt <= 0.0:
                continue
            for q0, q1 in zip(s0.q_rad, s1.q_rad):
                qd = abs(q1 - q0) / dt
                if qd > max_qd:
                    max_qd = qd
        print(f"  max joint velocity: {max_qd:.4f} rad/s")

    # ---- Replay via simulator (optional) -----------------------------------
    try:
        import pybullet  # noqa: F401 — availability check only
    except ImportError:
        print("\npybullet not available — skipping simulator replay.")
        return

    from src.simulation.bridge import SimBridge

    if not SimBridge.is_initialized():
        print("\nSimBridge not initialised — skipping simulator replay.")
        return

    from src.drivers.sim.sim_driver import SimDriver
    from src.drivers.sim.sim_sampled_path import SimSampledPathDriver

    bridge = SimBridge.instance()
    inner = SimDriver(bridge, robot.name, robot.n)
    inner.connect()

    driver = SimSampledPathDriver(inner, robot, dt_s=0.02)
    print("\nReplaying path through SimSampledPathDriver ...")
    played_path = driver.play_program(prog)
    print(f"  replayed {len(played_path.samples)} samples")

    # Assertion: max joint velocity must be below the robot's configured limit.
    spec_limits = getattr(getattr(robot, "spec", None), "limits", None)
    if spec_limits is not None and len(path.samples) >= 2:
        qd_max = max(spec_limits.qd_max_rad_s)
        if max_qd < qd_max:
            print(f"  joint velocity assertion: PASS (max {max_qd:.4f} < limit {qd_max:.4f})")
        else:
            print(f"  joint velocity assertion: FAIL (max {max_qd:.4f} >= limit {qd_max:.4f})")


if __name__ == "__main__":
    main()
