# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project does not yet follow semantic versioning; tags will be added once
the public API stabilises.

## [Unreleased]

Changes since `c1ee054` (previous merge to main), covering the code landed on
branch `claude/path-calculator-trapz-FkX1U` via draft PRs #4 (limits / frames /
manipulability foundations) and #5 (path interpolator + post-processor accel
emission + audit fixes).

### Added

- `motion-planner` sub-agent role for kinematics work (`.claude/agents/motion-planner.md`)
- `src/robots/limits.py` — `JointLimits` frozen dataclass; per-robot velocity and
  acceleration limits for Panda, UR5, KUKA iiwa 14, and ABB IRB1200 sourced from
  vendor datasheets; all values in SI units (rad/s, rad/s²)
- `src/motion/frames.py` — TCP and RTCP pose composition helpers:
  `resolve_pose_to_base`, `forward_resolve`, `derive_frame_mode`,
  `resolve_frame_to_root`; `FrameMode` enum; math helpers `quat_wxyz_to_rotmat`,
  `_rotmat_to_quat_wxyz`, `SE3_from_pose`
- `src/motion/manipulability.py` — Yoshikawa manipulability index (`yoshikawa`)
  and singularity guard (`is_singular`), extracted from the optimizer to be
  reusable across the path-calculation pipeline
- `src/motion/limits.py` — structured limit-violation layer: `LimitViolation`
  (frozen dataclass), `LimitsExceeded` (exception with `.violations` list),
  `validate_move`, `assert_no_violations`; 9 reserved error codes
  (`JOINT_POSITION`, `JOINT_VELOCITY`, `JOINT_ACCEL`, `TCP_VELOCITY`,
  `TCP_ANGULAR_VELOCITY`, `TCP_ACCEL`, `SINGULARITY`, `RTCP_INVALID`,
  `TCP_INVALID`)
- `src/motion/path.py` — limits-aware time-parameterised path interpolator:
  `Sample`, `SampledPath`, `interpolate_program`, `interpolate_move`,
  `_trapezoidal_profile`, `_arc_fit_3pt`, `_slerp_quat`, `_slerp_via`
- `src/drivers/sim/sim_sampled_path.py` — `SimSampledPathDriver`, a Driver
  Protocol proxy that runs the interpolator and replays the resulting
  `SampledPath` through the PyBullet bridge
- KUKA LBR iiwa 14 R820 hand-built `DHRobot` factory added to
  `src/robots/predefined.py`; `get_robot("iiwa")` now works without a URDF
- `SpeedData.a_tcp_mm_s2` and `a_ori_deg_s2` optional fields with backwards-
  compatible JSON round-trip
- `ToolData.robhold` flag; drives TCP/RTCP frame mode selection in the
  interpolator and in `derive_frame_mode`
- `examples/demo_path_calculation.py` — end-to-end demo: builds a 4-corner
  MOVE_L square, interpolates at 20 ms, reports sample count and max joint
  velocity, and replays through `SimSampledPathDriver` when the bridge is
  available
- 51 new pytest functions for PR-A foundations, 25 for PR-B path primitives,
  and 12 for `SimSampledPathDriver`
- `LIMIT_VIOLATION` structured error code in `src/llm/tools.py` (dormant; will
  be activated when the LLM sim tools are re-wired through `interpolate_program`
  in a follow-on PR)

### Changed

- `src/toolpath/optimizer.py` no longer carries private `_quat_wxyz_to_rotmat`,
  `_SE3_from_pose`, or the Yoshikawa block — those symbols are now public in
  `src/motion/frames.py` and `src/motion/manipulability.py`
- `RobotURDFSpec` gained an optional `limits: JointLimits | None` keyword-only
  field; existing callers pass no argument (defaults to `None`)
- ABB RAPID emitter (`src/post/abb_rapid.py`) emits `AccSet acc%, 100;`
  immediately before each move when `SpeedData.a_tcp_mm_s2` is set; the
  percentage is clamped to [1, 100] of the 5000 mm/s² controller default and
  injected only when the value changes between moves
- KUKA KRL emitter (`src/post/kuka_krl.py`) emits `$ACC.CP = <m/s²>` and
  `$ACC.ORI1 = <deg/s²>` between the `$VEL` block and the `$APO` line when the
  corresponding `SpeedData` accel field is set
- URScript emitter (`src/post/ur_script.py`) passes `a=<m/s²>` on `movel` /
  `movec` from `a_tcp_mm_s2`, and `a=<rad/s²>` (converted from degrees) on
  `movej` from `a_ori_deg_s2`; falls back to `DEFAULT_ACCEL_LIN` /
  `DEFAULT_ACCEL_J` when the field is `None`
- `Sample.__post_init__` validates non-negative `t_s`, correct component counts
  for `flange_xyz_m` and `flange_quat_wxyz`, and unit-norm quaternion
- `SampledPath.__post_init__` validates positive `dt_s` and monotonic
  `move_boundaries`
- `_trapezoidal_profile` raises `ValueError` on negative distance (was a silent
  `(0.0,)` return)
- `_arc_fit_3pt` orientation now uses piecewise SLERP through `q_via`; previously
  it was a straight `q0 → q1` slerp that ignored `q_via`
- IR layer canonicalises every quaternion to the `w >= 0` hemisphere via the new
  `canonicalise_quat()` helper, applied in `PoseTarget`, `ToolData`, and
  `WObjData.__post_init__`
- `LimitViolation` field names align with the sibling `IK_UNREACHABLE` /
  `JOINT_LIMIT_CLAMPED` JSON shape: `error_code`, `requested`, `allowed`
- Sub-agent roster bumped from 8 to 9 (`motion-planner` added)

### Fixed

- `SimSampledPathDriver` now routes `bridge.start_trajectory` through
  `bridge.submit` so PyBullet calls happen on the GUI thread; previously this
  was a silent corruption and segfault risk
- `iiwa` is now registered in the rtb factory (`src/robots/predefined.py`);
  was the root cause of every kinematics LLM tool call crashing when the
  default sim robot was set to `iiwa`
- Quaternion `w < 0` no longer produces a 270° rotation vector in URScript
  emission; canonicalisation closes the same footgun in the RAPID and KRL
  emitters
- `interpolate_program` no longer crashes on `DHRobot` instances where
  `robot.q` is `None` (affects ABB IRB1200 and KUKA iiwa built via the DH
  factory)
- `SimBridge.tick` now self-shuts-down when the underlying `RobotArmSim` drops
  its PyBullet connection; previously this caused a permanent-singleton deadlock
  requiring a process kill

### Notes

- The following items are deferred to a follow-on PR (PR-C): S-curve / jerk
  profiles; collision-aware trajectory sampling; blend-zone honouring; RWS
  retry-on-transient-failure; reconciling two rtb IK APIs (`ikine_LM` vs
  `ik_LM`); `tools.py` JSON schema argument validation; and re-wiring the LLM
  `sim_*` tools through `interpolate_program` (was reverted in this branch;
  ready to re-enable now that `iiwa` is in the factory).
