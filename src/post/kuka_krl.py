"""KUKA KRL post-processor.

Translates a vendor-neutral :class:`~src.motion.ir.Program` into a paired
KRL ``.src`` (program) plus ``.dat`` (data) source pair, emittable on a KR
C4/C5 controller. The two files are returned concatenated by :meth:`emit`
with a clear ``;FOLD .DAT FILE`` separator marker; :meth:`emit_to_file`
splits them back into ``<basename>.src`` and ``<basename>.dat``.

Conversions applied at the boundary:

* Distances: IR metres -> KRL millimetres (``* 1000``).
* Joint angles: IR radians -> KRL degrees.
* Orientations: IR quaternion ``(w, x, y, z)`` -> KRL ZYX intrinsic Euler
  triple ``(A, B, C)`` in degrees, where ``A`` rotates about Z, ``B`` about
  the new Y, and ``C`` about the new X (KUKA convention).
* TCP velocity: IR ``v_tcp_mm_s`` -> KRL ``$VEL.CP`` in m/s
  (``v_tcp_mm_s / 1000``).
* Blend: IR ``ZoneData(RADIUS, r_mm)`` -> KRL ``$APO.CDIS = r_mm``;
  ``ZoneData.FINE`` clears ``$APO`` (no advance distance set).

The emitter walks the program once to assign deterministic names to every
unique target encountered, emits ``DECL`` declarations into the ``.dat``
file, and emits the motion body into the ``.src`` file. KRL has no native
work-object frame; the IR ``WObjData.base_*`` is mapped to the controller's
``$BASE`` and the tool TCP into ``$TOOL`` ahead of each move whose
tool/wobj differs from the previous one.

Reference: KUKA System Software 8.x Programming Manual (KSS).
"""

from __future__ import annotations

import math
import os
from io import StringIO

from src.motion.ir import (
    Comment,
    IfSignal,
    IOKind,
    IOOp,
    JointTarget,
    Move,
    MoveKind,
    PoseTarget,
    Procedure,
    Program,
    SetSignal,
    SpeedData,
    ToolData,
    Wait,
    WaitSignal,
    WObjData,
    ZoneData,
    ZoneKind,
)

# Marker that splits the concatenated .src/.dat output produced by emit().
DAT_SEPARATOR = ";FOLD .DAT FILE"


# ---------------------------------------------------------------------------
# Number / vector formatting
# ---------------------------------------------------------------------------


def _fmt_num(x: float, precision: int = 6) -> str:
    """Format a scalar trimmed of trailing zeros; integers stay integer-shaped.

    ``-0.0`` is normalised to ``0`` so output is deterministic across platforms.
    """
    if math.isclose(x, 0.0, abs_tol=1e-12):
        x = 0.0
    if math.isclose(x, round(x), abs_tol=1e-9):
        return str(int(round(x)))
    return f"{x:.{precision}f}".rstrip("0").rstrip(".")


def _quat_to_zyx_deg(q_wxyz: tuple[float, ...]) -> tuple[float, float, float]:
    """Quaternion (w, x, y, z) -> KUKA (A, B, C) ZYX Euler in **degrees**.

    KUKA uses a ZYX intrinsic rotation (A about Z, then B about new Y, then
    C about new X). The closed-form solution from a unit quaternion is::

        A = atan2(2*(w*z + x*y), 1 - 2*(y*y + z*z))    # yaw   (Z)
        B = asin(clamp(2*(w*y - z*x), -1, 1))          # pitch (Y)
        C = atan2(2*(w*x + y*z), 1 - 2*(x*x + y*y))    # roll  (X)
    """
    w, x, y, z = q_wxyz

    # Yaw (Z)
    sinr_a = 2.0 * (w * z + x * y)
    cosr_a = 1.0 - 2.0 * (y * y + z * z)
    a = math.atan2(sinr_a, cosr_a)

    # Pitch (Y) — clamp for numerical safety near gimbal lock.
    sin_b = 2.0 * (w * y - z * x)
    sin_b = max(-1.0, min(1.0, sin_b))
    b = math.asin(sin_b)

    # Roll (X)
    sinr_c = 2.0 * (w * x + y * z)
    cosr_c = 1.0 - 2.0 * (x * x + y * y)
    c = math.atan2(sinr_c, cosr_c)

    return math.degrees(a), math.degrees(b), math.degrees(c)


def _fmt_frame(xyz_m: tuple[float, ...], q_wxyz: tuple[float, ...]) -> str:
    """KRL ``{X .., Y .., Z .., A .., B .., C ..}`` frame literal."""
    x_mm = xyz_m[0] * 1000.0
    y_mm = xyz_m[1] * 1000.0
    z_mm = xyz_m[2] * 1000.0
    a_deg, b_deg, c_deg = _quat_to_zyx_deg(q_wxyz)
    return (
        "{X " + _fmt_num(x_mm)
        + ", Y " + _fmt_num(y_mm)
        + ", Z " + _fmt_num(z_mm)
        + ", A " + _fmt_num(a_deg)
        + ", B " + _fmt_num(b_deg)
        + ", C " + _fmt_num(c_deg)
        + "}"
    )


def _fmt_axis(q_rad: tuple[float, ...]) -> str:
    """KRL ``{AXIS: A1 .., A2 .., ..., A6 ..}`` joint literal in **degrees**."""
    parts: list[str] = []
    for i in range(6):
        v = q_rad[i] if i < len(q_rad) else 0.0
        parts.append(f"A{i + 1} " + _fmt_num(math.degrees(v)))
    return "{AXIS: " + ", ".join(parts) + "}"


# ---------------------------------------------------------------------------
# Tool / WObj formatters — emitted as $TOOL / $BASE assignments
# ---------------------------------------------------------------------------


def _tool_assign(tool: ToolData) -> str:
    return "$TOOL = " + _fmt_frame(tool.tcp_xyz_m, tool.tcp_quat_wxyz)


def _base_assign(wobj: WObjData) -> str:
    return "$BASE = " + _fmt_frame(wobj.base_xyz_m, wobj.base_quat_wxyz)


# ---------------------------------------------------------------------------
# Speed / zone helpers
# ---------------------------------------------------------------------------


def _vel_cp_assign(speed: SpeedData) -> str:
    """``$VEL.CP`` in m/s for LIN/CIRC moves."""
    v_m_s = speed.v_tcp_mm_s / 1000.0
    return "$VEL.CP = " + _fmt_num(v_m_s)


def _vel_axis_assign(speed: SpeedData) -> str:
    """``$VEL_AXIS[i]`` in % of max for PTP moves.

    Map IR's TCP speed (mm/s) to a percentage by clamping ``v_tcp_mm_s/100``
    into ``[1, 100]``: 100 mm/s -> 1%, 5000 mm/s -> 50%, etc. This is a
    pragmatic mapping; precise mapping requires per-robot maximum velocities.
    """
    pct = max(1, min(100, int(round(speed.v_tcp_mm_s / 100.0))))
    parts = [f"$VEL_AXIS[{i}] = {pct}" for i in range(1, 7)]
    return "; ".join(parts)


def _zone_assign(zone: ZoneData) -> str | None:
    """Return the ``$APO.CDIS`` line for blends, or ``None`` for FINE."""
    if zone.kind == ZoneKind.FINE:
        return None
    return "$APO.CDIS = " + _fmt_num(zone.radius_mm)


def _acc_cp_assign(speed: SpeedData) -> str | None:
    """Return ``$ACC.CP = <value>`` in m/s², or ``None`` if unset.

    Args:
        speed: SpeedData from the Move.

    Returns:
        A KRL ``$ACC.CP = ...`` assignment string, or ``None``.
    """
    if speed.a_tcp_mm_s2 is None:
        return None
    return "$ACC.CP = " + _fmt_num(speed.a_tcp_mm_s2 / 1000.0)


def _acc_ori_assign(speed: SpeedData) -> str | None:
    """Return ``$ACC.ORI1 = <value>`` in deg/s², or ``None`` if unset.

    Args:
        speed: SpeedData from the Move.

    Returns:
        A KRL ``$ACC.ORI1 = ...`` assignment string, or ``None``.
    """
    if speed.a_ori_deg_s2 is None:
        return None
    return "$ACC.ORI1 = " + _fmt_num(speed.a_ori_deg_s2)


# ---------------------------------------------------------------------------
# Walk: collect target declarations
# ---------------------------------------------------------------------------


class _Decls:
    """Mutable collector for unique declarations encountered during the walk."""

    def __init__(self) -> None:
        self.pose_targets: dict[int, str] = {}
        self.joint_targets: dict[int, str] = {}
        self.pose_decls: list[str] = []
        self.joint_decls: list[str] = []
        self._pose_counter = 0
        self._joint_counter = 0

    def name_pose(self, t: PoseTarget) -> str:
        key = id(t)
        existing = self.pose_targets.get(key)
        if existing is not None:
            return existing
        self._pose_counter += 1
        name = f"P{self._pose_counter}"
        self.pose_targets[key] = name
        self.pose_decls.append(
            f"DECL E6POS {name} = " + _fmt_frame(t.xyz_m, t.quat_wxyz)
        )
        return name

    def name_joint(self, t: JointTarget) -> str:
        key = id(t)
        existing = self.joint_targets.get(key)
        if existing is not None:
            return existing
        self._joint_counter += 1
        name = f"J{self._joint_counter}"
        self.joint_targets[key] = name
        self.joint_decls.append(
            f"DECL E6AXIS {name} = " + _fmt_axis(t.q_rad)
        )
        return name


# ---------------------------------------------------------------------------
# Step emitters
# ---------------------------------------------------------------------------


def _emit_io(op: IOOp) -> list[str]:
    # Treat the signal as an integer port if numeric, else strip non-digits.
    digits = "".join(ch for ch in op.signal if ch.isdigit())
    port = digits if digits else op.signal
    if op.kind == IOKind.SET:
        on = "TRUE" if float(op.value) != 0.0 else "FALSE"
        return [f"$OUT[{port}] = {on}"]
    if op.kind == IOKind.PULSE:
        return [f"PULSE($OUT[{port}], TRUE, 0.2)"]
    if op.kind == IOKind.WAIT_HIGH:
        return [f"WAIT FOR $IN[{port}]"]
    if op.kind == IOKind.WAIT_LOW:
        return [f"WAIT FOR NOT $IN[{port}]"]
    raise ValueError(f"Unsupported IOKind: {op.kind}")  # pragma: no cover


def _emit_wait(w: Wait) -> list[str]:
    if w.seconds is not None:
        return ["WAIT SEC " + _fmt_num(w.seconds)]
    digits = "".join(ch for ch in (w.signal or "") if ch.isdigit())
    port = digits if digits else (w.signal or "")
    return [f"WAIT FOR $IN[{port}]"]


def _emit_move_lines(
    move: Move,
    decls: _Decls,
    state: dict,
) -> list[str]:
    """Emit one or more KRL lines for a single Move; updates ``state``.

    ``state`` carries the previously-emitted ``$TOOL``, ``$BASE``, ``$VEL.CP``,
    ``$VEL_AXIS`` and ``$APO`` to suppress redundant assignments.
    """
    lines: list[str] = []

    # Tool / base — emit when changed.
    tool_key = id(move.tool)
    if state.get("tool_id") != tool_key:
        lines.append(_tool_assign(move.tool))
        state["tool_id"] = tool_key

    base_key = id(move.wobj)
    if state.get("base_id") != base_key:
        lines.append(_base_assign(move.wobj))
        state["base_id"] = base_key

    # Speed: PTP uses $VEL_AXIS, LIN/CIRC use $VEL.CP. Track per-mode keys.
    if move.kind in (MoveKind.MOVE_J, MoveKind.MOVE_ABS_J):
        speed_line = _vel_axis_assign(move.speed)
        if state.get("vel_axis") != speed_line:
            lines.append(speed_line)
            state["vel_axis"] = speed_line
    else:
        speed_line = _vel_cp_assign(move.speed)
        if state.get("vel_cp") != speed_line:
            lines.append(speed_line)
            state["vel_cp"] = speed_line

    # Acceleration: $ACC.CP and $ACC.ORI1 for LIN/CIRC and MOVE_J(pose).
    # Emit only when the value changes; apply only for non-pure-joint moves.
    if move.kind not in (MoveKind.MOVE_ABS_J,) and not (
        move.kind == MoveKind.MOVE_J and isinstance(move.target, JointTarget)
    ):
        acc_cp = _acc_cp_assign(move.speed)
        if acc_cp is not None and state.get("acc_cp") != acc_cp:
            lines.append(acc_cp)
            state["acc_cp"] = acc_cp

        acc_ori = _acc_ori_assign(move.speed)
        if acc_ori is not None and state.get("acc_ori") != acc_ori:
            lines.append(acc_ori)
            state["acc_ori"] = acc_ori

    # Zone: $APO.CDIS for RADIUS, nothing for FINE. We track the last seen
    # value so successive equal blends don't re-emit.
    apo_line = _zone_assign(move.zone)
    if apo_line != state.get("apo"):
        if apo_line is not None:
            lines.append(apo_line)
        state["apo"] = apo_line

    # Motion line + C_DIS continuation marker for blends.
    cont = " C_DIS" if apo_line is not None else ""
    if move.kind == MoveKind.MOVE_J:
        if isinstance(move.target, JointTarget):
            tgt = decls.name_joint(move.target)
        else:
            tgt = decls.name_pose(move.target)
        lines.append(f"PTP {tgt}{cont}")
    elif move.kind == MoveKind.MOVE_L:
        tgt = decls.name_pose(move.target)  # type: ignore[arg-type]
        lines.append(f"LIN {tgt}{cont}")
    elif move.kind == MoveKind.MOVE_C:
        assert move.circ_via is not None  # IR-validated
        via = decls.name_pose(move.circ_via)
        tgt = decls.name_pose(move.target)  # type: ignore[arg-type]
        lines.append(f"CIRC {via}, {tgt}{cont}")
    elif move.kind == MoveKind.MOVE_ABS_J:
        tgt = decls.name_joint(move.target)  # type: ignore[arg-type]
        lines.append(f"PTP {tgt}{cont}")
    else:  # pragma: no cover
        raise ValueError(f"Unsupported MoveKind: {move.kind}")
    return lines


def _walk_procedure(proc: Procedure, decls: _Decls) -> list[str]:
    """Emit the body lines for one procedure; mutates ``decls``."""
    state: dict = {}
    lines: list[str] = []
    for step in proc.body:
        if isinstance(step, Move):
            lines.extend(_emit_move_lines(step, decls, state))
        elif isinstance(step, IOOp):
            lines.extend(_emit_io(step))
        elif isinstance(step, Wait):
            lines.extend(_emit_wait(step))
        elif isinstance(step, Comment):
            for raw in step.text.splitlines() or [""]:
                lines.append(f"; {raw}")
        elif isinstance(step, (SetSignal, WaitSignal, IfSignal)):
            # I/O step types are runtime-resolved; KRL emission is a future phase.
            lines.append(f"; {type(step).__name__}: {step}")
        else:  # pragma: no cover
            raise TypeError(f"Unknown procedure step: {type(step).__name__}")
    return lines


# ---------------------------------------------------------------------------
# Public KRLPost class
# ---------------------------------------------------------------------------


class KRLPost:
    """Emit KUKA KRL ``.src`` + ``.dat`` source from a vendor-neutral Program."""

    name = "kuka_krl"
    file_extension = ".src"

    def emit(self, program: Program) -> str:
        decls = _Decls()
        proc_blocks: list[tuple[str, list[str]]] = []
        for proc in program.procedures:
            proc_blocks.append((proc.name, _walk_procedure(proc, decls)))

        # ----- .src file ----------------------------------------------------
        src = StringIO()
        src.write(f"&ACCESS RVP\n&REL 1\nDEF {program.name}()\n")
        for key, val in sorted(program.modules_metadata.items()):
            src.write(f"  ; {key}: {val}\n")
        if program.modules_metadata:
            src.write("\n")

        # The first procedure is the entry point; its body is inlined into
        # the top-level DEF. Additional procedures are emitted as separate
        # DEFs after END.
        if proc_blocks:
            entry_name, entry_body = proc_blocks[0]
            for line in entry_body:
                src.write(f"  {line}\n")
        src.write("END\n")

        for name, body in proc_blocks[1:]:
            src.write(f"\nDEF {name}()\n")
            for line in body:
                src.write(f"  {line}\n")
            src.write("END\n")

        # ----- .dat file ----------------------------------------------------
        dat = StringIO()
        dat.write(f"&ACCESS RVP\n&REL 1\nDEFDAT {program.name}\n")
        for tool in program.tools:
            dat.write(f"  ; tool {tool.name}: mass {_fmt_num(tool.mass_kg)} kg\n")
            dat.write(f"  DECL FRAME {tool.name} = "
                      + _fmt_frame(tool.tcp_xyz_m, tool.tcp_quat_wxyz) + "\n")
        for wobj in program.wobjs:
            dat.write(f"  DECL FRAME {wobj.name} = "
                      + _fmt_frame(wobj.base_xyz_m, wobj.base_quat_wxyz) + "\n")
        if program.tools or program.wobjs:
            dat.write("\n")
        for decl in decls.pose_decls:
            dat.write(f"  {decl}\n")
        for decl in decls.joint_decls:
            dat.write(f"  {decl}\n")
        if decls.pose_decls or decls.joint_decls:
            dat.write("\n")
        dat.write("ENDDAT\n")

        return src.getvalue() + DAT_SEPARATOR + "\n" + dat.getvalue()

    def emit_to_file(self, program: Program, path: str) -> None:
        text = self.emit(program)
        # Strip *any* trailing extension so foo / foo.src / foo.dat / foo.SRC
        # all pair to foo.src + foo.dat. Without this, foo.dat would write
        # foo.dat.src + foo.dat.dat.
        base, _ = os.path.splitext(path)
        src_text, _, dat_text = text.partition(DAT_SEPARATOR + "\n")
        with open(base + ".src", "w", encoding="utf-8") as fh:
            fh.write(src_text)
        with open(base + ".dat", "w", encoding="utf-8") as fh:
            fh.write(dat_text)


__all__ = ["DAT_SEPARATOR", "KRLPost"]
