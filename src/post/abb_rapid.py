"""ABB RAPID post-processor.

Translates a vendor-neutral :class:`~src.motion.ir.Program` into a RAPID
``.mod`` module whose source is loadable into a RobotStudio Virtual
Controller (or any IRC5/OmniCore via RWS).

Conversions applied at the boundary:

* Distances: IR metres → RAPID millimetres (``* 1000``).
* Joint angles: IR radians → RAPID degrees.
* Quaternions: IR ``(w, x, y, z)`` → RAPID ``[q1, q2, q3, q4]`` (same order).

The emitter walks the program once to collect unique declarations
(tools, workobjects, speeds, zones, pose / joint targets) and emits
named ``CONST``/``PERS`` declarations at the top of the module so the
PROC body stays compact and human-readable. Predefined RAPID names
(``fine``, ``z10``, ``v100``, ...) are reused when the IR values match;
otherwise a custom declaration is generated.

Acceleration handling:
    RAPID ``speeddata`` has no acceleration slot. The canonical lever is the
    ``AccSet acc, ramp`` instruction, which sets TCP acceleration as a
    percentage of the controller default (5000 mm/s²). When
    :attr:`~src.motion.ir.SpeedData.a_tcp_mm_s2` is set on a Move, the emitter
    inserts an ``AccSet`` instruction immediately before the move line whenever
    the acceleration value changes from the last emitted one.

Reference: ABB RAPID Technical Reference Manual (3HAC16581-1).
"""

from __future__ import annotations

import math
from io import StringIO
from typing import Optional

from src.motion.ir import (
    Comment,
    ConfigData,
    IOKind,
    IOOp,
    JointTarget,
    Move,
    MoveKind,
    PoseTarget,
    Procedure,
    Program,
    SpeedData,
    ToolData,
    Wait,
    WObjData,
    ZoneData,
    ZoneKind,
)

# Predefined RAPID zone radii (mm). See RAPID reference, "zonedata".
_PREDEFINED_ZONES = (0, 1, 5, 10, 15, 20, 30, 40, 50, 60, 80, 100, 150, 200)

# Predefined RAPID v_tcp linear speeds (mm/s). See RAPID reference, "speeddata".
_PREDEFINED_SPEEDS = (
    5, 10, 20, 30, 40, 50, 60, 80, 100, 150, 200,
    300, 400, 500, 600, 800, 1000, 1500, 2000, 2500,
    3000, 4000, 5000, 6000, 7000,
)

# Default secondary speed components when the IR matches a predefined v<N>.
# These are the values RAPID uses for predefined v<N> entries.
_PREDEF_SPEED_DEFAULTS = (500.0, 5000.0, 1000.0)  # v_ori, v_lin_ext, v_rot_ext

# RAPID "no value" sentinel for unused external axes.
NO_VAL = "9E9"


# ---------------------------------------------------------------------------
# Number / vector formatting
# ---------------------------------------------------------------------------


def _fmt_num(x: float, precision: int = 6) -> str:
    """Format a scalar trimmed of trailing zeros; integers stay integer-shaped."""
    if math.isclose(x, round(x), abs_tol=1e-9):
        return str(int(round(x)))
    return f"{x:.{precision}f}".rstrip("0").rstrip(".")


def _fmt_xyz_mm(xyz_m: tuple[float, ...]) -> str:
    """``[x, y, z]`` in millimetres from an IR ``xyz_m`` tuple."""
    return "[" + ", ".join(_fmt_num(v * 1000.0) for v in xyz_m) + "]"


def _fmt_quat(q_wxyz: tuple[float, ...]) -> str:
    """``[q1, q2, q3, q4]`` — RAPID uses the same wxyz order as the IR."""
    return "[" + ", ".join(_fmt_num(v) for v in q_wxyz) + "]"


def _fmt_cfg(cfg: Optional[ConfigData]) -> str:
    if cfg is None:
        return "[0, 0, 0, 0]"
    return f"[{cfg.cf1}, {cfg.cf4}, {cfg.cf6}, {cfg.cfx}]"


def _fmt_eax_rad_to_deg(ext_axes_rad: tuple[float, ...]) -> str:
    """6-slot external axis array; degrees if specified, else 9E9."""
    out: list[str] = []
    for i in range(6):
        if i < len(ext_axes_rad):
            out.append(_fmt_num(math.degrees(ext_axes_rad[i])))
        else:
            out.append(NO_VAL)
    return "[" + ", ".join(out) + "]"


def _safe_id_token(x: float) -> str:
    """Turn a float into a RAPID-identifier-safe suffix (no '.' or '-')."""
    s = _fmt_num(x).replace("-", "n").replace(".", "p")
    return s


# ---------------------------------------------------------------------------
# Speed / zone resolver — predefined name when possible, else custom decl
# ---------------------------------------------------------------------------


def _speed_name(speed: SpeedData, custom_decls: dict[str, str]) -> str:
    v = round(speed.v_tcp_mm_s)
    matches_predef = (
        v in _PREDEFINED_SPEEDS
        and math.isclose(speed.v_tcp_mm_s, v, abs_tol=1e-6)
        and math.isclose(speed.v_ori_deg_s, _PREDEF_SPEED_DEFAULTS[0], abs_tol=1e-6)
        and math.isclose(speed.v_lin_ext_mm_s, _PREDEF_SPEED_DEFAULTS[1], abs_tol=1e-6)
        and math.isclose(speed.v_rot_ext_deg_s, _PREDEF_SPEED_DEFAULTS[2], abs_tol=1e-6)
    )
    if matches_predef:
        return f"v{v}"
    name = (
        f"v_{_safe_id_token(speed.v_tcp_mm_s)}_"
        f"{_safe_id_token(speed.v_ori_deg_s)}"
    )
    decl = (
        f"CONST speeddata {name} := ["
        f"{_fmt_num(speed.v_tcp_mm_s)}, {_fmt_num(speed.v_ori_deg_s)}, "
        f"{_fmt_num(speed.v_lin_ext_mm_s)}, {_fmt_num(speed.v_rot_ext_deg_s)}];"
    )
    custom_decls.setdefault(name, decl)
    return name


def _zone_name(zone: ZoneData, custom_decls: dict[str, str]) -> str:
    if zone.kind == ZoneKind.FINE:
        return "fine"
    r = round(zone.radius_mm)
    if r in _PREDEFINED_ZONES and math.isclose(zone.radius_mm, r, abs_tol=1e-6):
        return f"z{r}"
    # Custom zonedata. RAPID's zonedata layout:
    # [finep, pzone_tcp, pzone_ori, pzone_eax, zone_ori, zone_leax, zone_reax]
    pzone = zone.radius_mm
    name = f"z_{_safe_id_token(pzone)}"
    decl = (
        f"CONST zonedata {name} := [FALSE, {_fmt_num(pzone)}, "
        f"{_fmt_num(pzone * 1.5)}, {_fmt_num(pzone * 1.5)}, "
        f"{_fmt_num(pzone * 0.15)}, {_fmt_num(pzone * 1.5)}, "
        f"{_fmt_num(pzone * 0.15)}];"
    )
    custom_decls.setdefault(name, decl)
    return name


# ---------------------------------------------------------------------------
# Tool / WObj / target declaration formatters
# ---------------------------------------------------------------------------


def _decl_tooldata(tool: ToolData) -> str:
    # PERS tooldata name := [robhold, [tframe_xyz, tframe_quat], [mass, cog, [1,0,0,0], 0, 0, 0]];
    mass = max(tool.mass_kg, 1e-3)  # RAPID requires mass > 0
    return (
        f"PERS tooldata {tool.name} := [TRUE, "
        f"[{_fmt_xyz_mm(tool.tcp_xyz_m)}, {_fmt_quat(tool.tcp_quat_wxyz)}], "
        f"[{_fmt_num(mass)}, {_fmt_xyz_mm(tool.cog_xyz_m)}, "
        f"[1, 0, 0, 0], 0, 0, 0]];"
    )


def _decl_wobjdata(wobj: WObjData) -> str:
    # PERS wobjdata name := [robhold, ufprog, ufmec, uframe, oframe];
    robhold = "TRUE" if wobj.robhold else "FALSE"
    return (
        f"PERS wobjdata {wobj.name} := [{robhold}, TRUE, \"\", "
        f"[{_fmt_xyz_mm(wobj.user_xyz_m)}, {_fmt_quat(wobj.user_quat_wxyz)}], "
        f"[{_fmt_xyz_mm(wobj.base_xyz_m)}, {_fmt_quat(wobj.base_quat_wxyz)}]];"
    )


def _decl_robtarget(name: str, t: PoseTarget) -> str:
    return (
        f"CONST robtarget {name} := ["
        f"{_fmt_xyz_mm(t.xyz_m)}, {_fmt_quat(t.quat_wxyz)}, "
        f"{_fmt_cfg(t.config)}, {_fmt_eax_rad_to_deg(t.ext_axes_rad)}];"
    )


def _decl_jointtarget(name: str, t: JointTarget) -> str:
    deg = "[" + ", ".join(_fmt_num(math.degrees(q)) for q in t.q_rad) + "]"
    return (
        f"CONST jointtarget {name} := [{deg}, "
        f"{_fmt_eax_rad_to_deg(t.ext_axes_rad)}];"
    )


# ---------------------------------------------------------------------------
# Acceleration helper
# ---------------------------------------------------------------------------


def _accset_line(speed: SpeedData) -> str | None:
    """Return an ``AccSet acc%, 100;`` line or ``None`` if ``a_tcp_mm_s2`` is unset.

    The RAPID ``AccSet`` instruction sets TCP acceleration as a percentage of the
    controller default (5000 mm/s²). The ramp percentage is always 100 (full ramp).

    Args:
        speed: SpeedData from the Move.

    Returns:
        A RAPID ``AccSet acc, 100;`` string, or ``None``.
    """
    if speed.a_tcp_mm_s2 is None:
        return None
    acc_pct = max(1, min(100, round(speed.a_tcp_mm_s2 / 5000.0 * 100.0)))
    ramp_pct = 100
    return f"AccSet {acc_pct:.1f}, {ramp_pct};"


# ---------------------------------------------------------------------------
# Move / IO / Wait / Comment emitters
# ---------------------------------------------------------------------------


def _emit_move(
    move: Move,
    target_name: str,
    speed_name: str,
    zone_name: str,
) -> str:
    tool = move.tool.name
    # Always emit the \WObj clause. Earlier the suffix was elided when the
    # wobj name happened to be "wobj0", but the IR allows any name including
    # "wobj0" attached to a non-identity frame, in which case eliding the
    # clause would silently run motion in the wrong frame on the controller.
    suffix = f"\\WObj:={move.wobj.name}"
    if move.kind == MoveKind.MOVE_J:
        return f"MoveJ {target_name}, {speed_name}, {zone_name}, {tool}{suffix};"
    if move.kind == MoveKind.MOVE_L:
        return f"MoveL {target_name}, {speed_name}, {zone_name}, {tool}{suffix};"
    if move.kind == MoveKind.MOVE_ABS_J:
        return f"MoveAbsJ {target_name}, {speed_name}, {zone_name}, {tool}{suffix};"
    if move.kind == MoveKind.MOVE_C:
        # Caller must pass "<via_name>, <target_name>" already joined; we pass
        # the target_name through here and the via name is encoded by emit().
        return f"MoveC {target_name}, {speed_name}, {zone_name}, {tool}{suffix};"
    raise ValueError(f"Unsupported MoveKind: {move.kind}")


def _emit_io(op: IOOp) -> str:
    if op.kind == IOKind.SET:
        return f"SetDO {op.signal}, {_fmt_num(float(op.value))};"
    if op.kind == IOKind.PULSE:
        return f"PulseDO {op.signal};"
    if op.kind == IOKind.WAIT_HIGH:
        return f"WaitDI {op.signal}, 1;"
    if op.kind == IOKind.WAIT_LOW:
        return f"WaitDI {op.signal}, 0;"
    raise ValueError(f"Unsupported IOKind: {op.kind}")


def _emit_wait(w: Wait) -> str:
    if w.seconds is not None:
        return f"WaitTime {_fmt_num(w.seconds)};"
    return f"WaitDI {w.signal}, 1;"


# ---------------------------------------------------------------------------
# Walking the program — collect declarations, then emit
# ---------------------------------------------------------------------------


class _Decls:
    """Mutable collector for unique declarations encountered during the walk."""

    def __init__(self) -> None:
        self.pose_targets: dict[int, str] = {}     # id(PoseTarget) -> name
        self.joint_targets: dict[int, str] = {}    # id(JointTarget) -> name
        self.pose_decls: list[str] = []
        self.joint_decls: list[str] = []
        self.custom_speed_zone: dict[str, str] = {}
        self._pose_counter = 0
        self._joint_counter = 0

    def name_pose(self, t: PoseTarget) -> str:
        key = id(t)
        existing = self.pose_targets.get(key)
        if existing is not None:
            return existing
        self._pose_counter += 1
        name = f"p{self._pose_counter}"
        self.pose_targets[key] = name
        self.pose_decls.append(_decl_robtarget(name, t))
        return name

    def name_joint(self, t: JointTarget) -> str:
        key = id(t)
        existing = self.joint_targets.get(key)
        if existing is not None:
            return existing
        self._joint_counter += 1
        name = f"j{self._joint_counter}"
        self.joint_targets[key] = name
        self.joint_decls.append(_decl_jointtarget(name, t))
        return name


def _walk_procedure(proc: Procedure, decls: _Decls) -> list[str]:
    """Emit the body lines for one procedure; mutate ``decls`` with new targets."""
    lines: list[str] = []
    # Track last-emitted a_tcp_mm_s2 value so we only inject AccSet on change.
    state: dict = {}
    for step in proc.body:
        if isinstance(step, Move):
            speed_name = _speed_name(step.speed, decls.custom_speed_zone)
            zone_name = _zone_name(step.zone, decls.custom_speed_zone)

            # Inject AccSet when acceleration changes.
            accset = _accset_line(step.speed)
            if accset is not None and state.get("a_tcp_mm_s2") != step.speed.a_tcp_mm_s2:
                lines.append(accset)
                state["a_tcp_mm_s2"] = step.speed.a_tcp_mm_s2

            if step.kind == MoveKind.MOVE_C:
                assert step.circ_via is not None  # validated by IR
                via = decls.name_pose(step.circ_via)
                tgt = decls.name_pose(step.target)  # type: ignore[arg-type]
                joined = f"{via}, {tgt}"
                lines.append(_emit_move(step, joined, speed_name, zone_name))
            elif step.kind == MoveKind.MOVE_ABS_J:
                tgt = decls.name_joint(step.target)  # type: ignore[arg-type]
                lines.append(_emit_move(step, tgt, speed_name, zone_name))
            else:
                if isinstance(step.target, JointTarget):
                    tgt = decls.name_joint(step.target)
                else:
                    tgt = decls.name_pose(step.target)
                lines.append(_emit_move(step, tgt, speed_name, zone_name))
        elif isinstance(step, IOOp):
            lines.append(_emit_io(step))
        elif isinstance(step, Wait):
            lines.append(_emit_wait(step))
        elif isinstance(step, Comment):
            for raw_line in step.text.splitlines() or [""]:
                lines.append(f"! {raw_line}")
        else:  # pragma: no cover - IR validates step types upstream
            raise TypeError(f"Unknown procedure step: {type(step).__name__}")
    return lines


# ---------------------------------------------------------------------------
# Public RAPIDPost class
# ---------------------------------------------------------------------------


class RAPIDPost:
    """Emit ABB RAPID source from a vendor-neutral :class:`Program`."""

    name = "abb_rapid"
    file_extension = ".mod"

    def emit(self, program: Program) -> str:
        decls = _Decls()
        # Walk first so target / custom-speed declarations are known up front.
        proc_blocks: list[tuple[str, list[str]]] = []
        for proc in program.procedures:
            proc_blocks.append((proc.name, _walk_procedure(proc, decls)))

        out = StringIO()
        out.write(f"MODULE {program.name}\n")
        for key, val in sorted(program.modules_metadata.items()):
            out.write(f"  ! {key}: {val}\n")
        out.write("\n")

        for tool in program.tools:
            out.write(f"  {_decl_tooldata(tool)}\n")
        if program.tools:
            out.write("\n")

        for wobj in program.wobjs:
            out.write(f"  {_decl_wobjdata(wobj)}\n")
        if program.wobjs:
            out.write("\n")

        if decls.custom_speed_zone:
            for decl in decls.custom_speed_zone.values():
                out.write(f"  {decl}\n")
            out.write("\n")

        for decl in decls.pose_decls:
            out.write(f"  {decl}\n")
        for decl in decls.joint_decls:
            out.write(f"  {decl}\n")
        if decls.pose_decls or decls.joint_decls:
            out.write("\n")

        for name, body in proc_blocks:
            out.write(f"  PROC {name}()\n")
            for line in body:
                out.write(f"    {line}\n")
            out.write("  ENDPROC\n\n")

        out.write("ENDMODULE\n")
        return out.getvalue()

    def emit_to_file(self, program: Program, path: str) -> None:
        text = self.emit(program)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)


__all__ = ["RAPIDPost"]
