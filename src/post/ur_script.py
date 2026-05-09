"""Universal Robots URScript post-processor.

Translates a vendor-neutral :class:`~src.motion.ir.Program` into a flat
URScript ``.script`` source file that can be sent over the secondary
interface (port 30002) of any UR controller running PolyScope 3.x or 5.x.

URScript has no module / procedure construct. The whole program is emitted
as a single ``def main():`` block followed by a top-level ``main()`` call,
which is the canonical form expected by the controller's interpreter.

Conversions applied at the boundary:

* Distances: IR metres == URScript metres (no conversion).
* Joint angles: IR radians == URScript radians (no conversion).
* Orientations: IR quaternion ``(w, x, y, z)`` -> URScript axis-angle
  rotation vector ``(rx, ry, rz)`` where ``angle = 2*acos(w)`` and the
  axis is the imaginary part normalised. The ``angle == 0`` edge case
  (identity rotation) is mapped to ``(0, 0, 0)``.
* TCP velocity: IR ``v_tcp_mm_s`` -> URScript ``v=`` argument in m/s
  (``v_tcp_mm_s / 1000``).
* Blend: IR ``ZoneData(RADIUS, r_mm)`` -> URScript ``r=`` argument in
  metres (``r_mm / 1000``); ``ZoneData.FINE`` omits ``r``.

The emitter walks the program once, emits ``set_tcp(...)`` for each tool
change, comments the workobject (URScript has no native object frame),
and emits ``movej`` / ``movel`` / ``movec`` lines for each Move. Digital
I/O is emitted via ``set_digital_out`` and a ``while get_digital_in()``
spin-loop for waits.

Reference: Universal Robots Script Manual (rev. 5.x).
"""

from __future__ import annotations

import math
from io import StringIO

from src.motion.ir import (
    Comment,
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

# Default acceleration arguments. URScript requires a=... and v=... on
# every move; the IR doesn't model acceleration explicitly so we use
# vendor-typical defaults that the user can override on the controller.
DEFAULT_ACCEL_LIN = 1.2  # m/s^2 for movel/movec
DEFAULT_ACCEL_J = 1.4    # rad/s^2 for movej

# Indent inside ``def main():``.
INDENT = "  "


# ---------------------------------------------------------------------------
# Number / vector formatting
# ---------------------------------------------------------------------------


def _fmt_num(x: float, precision: int = 6) -> str:
    """Format a scalar trimmed of trailing zeros; integers stay integer-shaped.

    ``-0.0`` is normalised to ``0`` for deterministic golden-file tests.
    """
    if math.isclose(x, 0.0, abs_tol=1e-12):
        x = 0.0
    if math.isclose(x, round(x), abs_tol=1e-9):
        return str(int(round(x)))
    return f"{x:.{precision}f}".rstrip("0").rstrip(".")


def _quat_to_rotvec(q_wxyz: tuple[float, ...]) -> tuple[float, float, float]:
    """Quaternion (w, x, y, z) -> URScript axis-angle rotation vector.

    The rotation vector is ``axis * angle``: the unit axis scaled by the
    rotation angle in radians. Identity quaternions (``angle == 0``) map
    to ``(0, 0, 0)`` since the axis is undefined.
    """
    w, x, y, z = q_wxyz
    # Clamp w into [-1, 1] for numerical safety; acos is sensitive at edges.
    w_clamped = max(-1.0, min(1.0, w))
    angle = 2.0 * math.acos(w_clamped)
    s = math.sin(angle / 2.0)
    if abs(s) < 1e-12:
        # Identity (or near-identity) rotation: axis is undefined.
        return 0.0, 0.0, 0.0
    return (x / s) * angle, (y / s) * angle, (z / s) * angle


def _fmt_pose(xyz_m: tuple[float, ...], q_wxyz: tuple[float, ...]) -> str:
    """URScript ``p[x, y, z, rx, ry, rz]`` literal in SI units."""
    rx, ry, rz = _quat_to_rotvec(q_wxyz)
    parts = [
        _fmt_num(xyz_m[0]),
        _fmt_num(xyz_m[1]),
        _fmt_num(xyz_m[2]),
        _fmt_num(rx),
        _fmt_num(ry),
        _fmt_num(rz),
    ]
    return "p[" + ", ".join(parts) + "]"


def _fmt_joints(q_rad: tuple[float, ...]) -> str:
    """URScript ``[j1, j2, j3, j4, j5, j6]`` joint literal in radians."""
    out: list[str] = []
    for i in range(6):
        v = q_rad[i] if i < len(q_rad) else 0.0
        out.append(_fmt_num(v))
    return "[" + ", ".join(out) + "]"


# ---------------------------------------------------------------------------
# IO port helpers
# ---------------------------------------------------------------------------


def _io_port(signal: str) -> str:
    """Pick the integer port out of an IR signal name; fall back to the name."""
    digits = "".join(ch for ch in signal if ch.isdigit())
    return digits if digits else signal


# ---------------------------------------------------------------------------
# Move emitters
# ---------------------------------------------------------------------------


def _move_args(speed: SpeedData, zone: ZoneData, accel: float) -> str:
    """Common ``a=, v=, r=`` argument tail for movej/movel/movec."""
    v_m_s = speed.v_tcp_mm_s / 1000.0
    parts = [f"a={_fmt_num(accel)}", f"v={_fmt_num(v_m_s)}"]
    if zone.kind == ZoneKind.RADIUS:
        parts.append(f"r={_fmt_num(zone.radius_mm / 1000.0)}")
    return ", ".join(parts)


def _emit_move(move: Move) -> list[str]:
    """Return one URScript line for the given Move.

    Acceleration is derived from :attr:`~src.motion.ir.SpeedData.a_tcp_mm_s2`
    (for linear/circular moves, in m/s²) or
    :attr:`~src.motion.ir.SpeedData.a_ori_deg_s2` converted to rad/s² (for
    joint moves). Falls back to the module-level ``DEFAULT_ACCEL_*`` constants
    when the field is ``None``.
    """
    import math as _math

    if move.kind == MoveKind.MOVE_J:
        if move.speed.a_ori_deg_s2 is not None:
            accel = _math.radians(move.speed.a_ori_deg_s2)
        else:
            accel = DEFAULT_ACCEL_J
        args = _move_args(move.speed, move.zone, accel)
        if isinstance(move.target, JointTarget):
            tgt = _fmt_joints(move.target.q_rad)
        else:
            tgt = _fmt_pose(move.target.xyz_m, move.target.quat_wxyz)
        return [f"movej({tgt}, {args})"]
    if move.kind == MoveKind.MOVE_L:
        if move.speed.a_tcp_mm_s2 is not None:
            accel = move.speed.a_tcp_mm_s2 / 1000.0
        else:
            accel = DEFAULT_ACCEL_LIN
        args = _move_args(move.speed, move.zone, accel)
        assert isinstance(move.target, PoseTarget)
        tgt = _fmt_pose(move.target.xyz_m, move.target.quat_wxyz)
        return [f"movel({tgt}, {args})"]
    if move.kind == MoveKind.MOVE_C:
        if move.speed.a_tcp_mm_s2 is not None:
            accel = move.speed.a_tcp_mm_s2 / 1000.0
        else:
            accel = DEFAULT_ACCEL_LIN
        args = _move_args(move.speed, move.zone, accel)
        assert isinstance(move.target, PoseTarget) and move.circ_via is not None
        via = _fmt_pose(move.circ_via.xyz_m, move.circ_via.quat_wxyz)
        tgt = _fmt_pose(move.target.xyz_m, move.target.quat_wxyz)
        return [f"movec({via}, {tgt}, {args})"]
    if move.kind == MoveKind.MOVE_ABS_J:
        if move.speed.a_ori_deg_s2 is not None:
            accel = _math.radians(move.speed.a_ori_deg_s2)
        else:
            accel = DEFAULT_ACCEL_J
        args = _move_args(move.speed, move.zone, accel)
        assert isinstance(move.target, JointTarget)
        tgt = _fmt_joints(move.target.q_rad)
        return [f"movej({tgt}, {args})"]
    raise ValueError(f"Unsupported MoveKind: {move.kind}")  # pragma: no cover


# ---------------------------------------------------------------------------
# IO / Wait / Comment emitters
# ---------------------------------------------------------------------------


def _emit_io(op: IOOp) -> list[str]:
    port = _io_port(op.signal)
    if op.kind == IOKind.SET:
        flag = "True" if float(op.value) != 0.0 else "False"
        return [f"set_digital_out({port}, {flag})"]
    if op.kind == IOKind.PULSE:
        return [
            f"set_digital_out({port}, True)",
            "sleep(0.2)",
            f"set_digital_out({port}, False)",
        ]
    if op.kind == IOKind.WAIT_HIGH:
        return [
            f"while get_digital_in({port}) != True:",
            f"{INDENT}sync()",
            "end",
        ]
    if op.kind == IOKind.WAIT_LOW:
        return [
            f"while get_digital_in({port}) != False:",
            f"{INDENT}sync()",
            "end",
        ]
    raise ValueError(f"Unsupported IOKind: {op.kind}")  # pragma: no cover


def _emit_wait(w: Wait) -> list[str]:
    if w.seconds is not None:
        return [f"sleep({_fmt_num(w.seconds)})"]
    port = _io_port(w.signal or "")
    return [
        f"while get_digital_in({port}) != True:",
        f"{INDENT}sync()",
        "end",
    ]


# ---------------------------------------------------------------------------
# Walk procedures, tracking tool/wobj state
# ---------------------------------------------------------------------------


def _set_tcp_line(tool: ToolData) -> str:
    return f"set_tcp({_fmt_pose(tool.tcp_xyz_m, tool.tcp_quat_wxyz)})"


def _wobj_comment(wobj: WObjData) -> str:
    """Workobjects don't exist in URScript; emit a faithful comment instead."""
    rx, ry, rz = _quat_to_rotvec(wobj.base_quat_wxyz)
    return (
        f"# wobj {wobj.name}: base = ["
        f"{_fmt_num(wobj.base_xyz_m[0])}, "
        f"{_fmt_num(wobj.base_xyz_m[1])}, "
        f"{_fmt_num(wobj.base_xyz_m[2])}, "
        f"{_fmt_num(rx)}, {_fmt_num(ry)}, {_fmt_num(rz)}]"
    )


def _walk_procedure(proc: Procedure) -> list[str]:
    """Emit body lines for one procedure; tracks the active tool/wobj."""
    state: dict = {}
    lines: list[str] = []
    for step in proc.body:
        if isinstance(step, Move):
            tool_key = id(step.tool)
            if state.get("tool_id") != tool_key:
                lines.append(_set_tcp_line(step.tool))
                state["tool_id"] = tool_key
            wobj_key = id(step.wobj)
            if state.get("wobj_id") != wobj_key:
                lines.append(_wobj_comment(step.wobj))
                state["wobj_id"] = wobj_key
            lines.extend(_emit_move(step))
        elif isinstance(step, IOOp):
            lines.extend(_emit_io(step))
        elif isinstance(step, Wait):
            lines.extend(_emit_wait(step))
        elif isinstance(step, Comment):
            for raw in step.text.splitlines() or [""]:
                lines.append(f"# {raw}")
        else:  # pragma: no cover - IR validates step types
            raise TypeError(f"Unknown procedure step: {type(step).__name__}")
    return lines


# ---------------------------------------------------------------------------
# Public URScriptPost class
# ---------------------------------------------------------------------------


class URScriptPost:
    """Emit Universal Robots URScript source from a vendor-neutral Program."""

    name = "ur_script"
    file_extension = ".script"

    def emit(self, program: Program) -> str:
        out = StringIO()
        out.write(f"# program: {program.name}\n")
        for key, val in sorted(program.modules_metadata.items()):
            out.write(f"# {key}: {val}\n")
        out.write("def main():\n")

        # Walk every procedure; URScript has no PROC construct, so we inline
        # the bodies. Procedures beyond the first are emitted with a leading
        # ``# proc <name>`` separator comment so their boundaries remain
        # visible in the output.
        first = True
        for proc in program.procedures:
            if not first:
                out.write(f"{INDENT}# proc {proc.name}\n")
            first = False
            for line in _walk_procedure(proc):
                out.write(f"{INDENT}{line}\n")

        out.write("end\n")
        out.write("main()\n")
        return out.getvalue()

    def emit_to_file(self, program: Program, path: str) -> None:
        text = self.emit(program)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)


__all__ = ["URScriptPost"]
