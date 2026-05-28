"""File-backed project (Doc) store + small operation helpers.

Persists every Doc as ``<repo>/data/projects/<id>.arcjob.json`` in the same
JSON shape the browser app produces (camelCase, identical to
``downloadDoc()`` in ``web-arc/src/lib/doc.ts``), so files round-trip across
both ends and can be edited via the MCP tools or the REST API
interchangeably.

The tool / part / TCP catalogs mirror ``web-arc/src/lib/catalogs.ts`` 1:1.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from pydantic import ValidationError

from server.models.project import (
    Doc,
    DocMeta,
    Job,
    Operation,
    OperationParams,
    Part,
    PartPose,
    Pick,
    TcpFrame,
    Tool,
    ToolLead,
    ToolSize,
    Mount,
    Payload,
    Strategy,
    OpKind,
    Weave,
)

# --------------------------------------------------------------------------- #
# Catalogs — mirror of web-arc/src/lib/catalogs.ts
# --------------------------------------------------------------------------- #

TCP_LIBRARY: List[TcpFrame] = [
    TcpFrame(id="tcp-flange", name="FLANGE",   offset=(0, 0, 0),         rpy=(0, 0, 0),   payload=Payload(mass=0.0, com=(0, 0, 0))),
    TcpFrame(id="tcp-tip",    name="TOOL TIP", offset=(0, 0.130, 0),     rpy=(0, 0, 0),   payload=Payload(mass=1.8, com=(0, 0, 0.05))),
    TcpFrame(id="tcp-weld",   name="WELD TIP", offset=(0.027, 0.158, 0), rpy=(-35, 0, 0), payload=Payload(mass=2.4, com=(0, 0, 0.06))),
]

TOOL_LIBRARY: List[Tool] = [
    Tool(id="grip-2f", name="GRIPPER-2F", type="GRIPPER_2F", tcp_offset=(0, 0.130, 0),
         size=ToolSize(stroke=0.056, length=0.06), lead=ToolLead.model_validate({"in": 0.02, "out": 0.02})),
    Tool(id="grip-3f", name="GRIPPER-3F", type="GRIPPER_3F", tcp_offset=(0, 0.130, 0),
         size=ToolSize(stroke=0.050, length=0.06), lead=ToolLead.model_validate({"in": 0.02, "out": 0.02})),
    Tool(id="suction", name="SUCTION",    type="SUCTION",    tcp_offset=(0, 0.120, 0),
         size=ToolSize(dia=0.05),            lead=ToolLead.model_validate({"in": 0.03, "out": 0.03})),
    Tool(id="mig",     name="WELDER-MIG", type="MIG",        tcp_offset=(0.027, 0.158, 0),
         size=ToolSize(length=0.16),         lead=ToolLead.model_validate({"in": 0.015, "out": 0.015})),
    Tool(id="spindle", name="SPINDLE-T7", type="SPINDLE",    tcp_offset=(0, 0.201, 0),
         size=ToolSize(length=0.18, dia=0.10), lead=ToolLead.model_validate({"in": 0.02, "out": 0.02})),
    Tool(id="disp",    name="DISPENSER",  type="DISPENSER",  tcp_offset=(0, 0.149, 0),
         size=ToolSize(length=0.14),         lead=ToolLead.model_validate({"in": 0.01, "out": 0.01})),
]

PART_LIBRARY: List[Part] = [
    Part(id="part-box",   name="BLOCK",    kind="BOX",
         dims={"w": 0.40, "h": 0.15, "d": 0.30}, pose=PartPose(pos=(0.50, 0, 0))),
    Part(id="part-cyl",   name="CYLINDER", kind="CYLINDER",
         dims={"r": 0.14, "h": 0.18},            pose=PartPose(pos=(0.50, 0, 0))),
    Part(id="part-plate", name="PLATE",    kind="PLATE",
         dims={"w": 0.50, "t": 0.02, "d": 0.35}, pose=PartPose(pos=(0.50, 0, 0))),
    Part(id="part-step",  name="STEP",     kind="STEP",
         dims={"w": 0.40, "h": 0.06, "d": 0.30, "topW": 0.28, "topH": 0.08, "topD": 0.22},
         pose=PartPose(pos=(0.50, 0, 0))),
]

OP_DEFAULT_TOOL: Dict[OpKind, str] = {"PICKPLACE": "grip-2f", "WELD": "mig", "MILL": "spindle", "DISPENSE": "disp"}
OP_DEFAULT_PART: Dict[OpKind, str] = {"PICKPLACE": "part-box", "WELD": "part-plate", "MILL": "part-box", "DISPENSE": "part-plate"}

WEAVE_DEFAULT = Weave()


def find_tool(tool_id: str) -> Optional[Tool]:
    return next((t for t in TOOL_LIBRARY if t.id == tool_id), None)


def find_part(part_id: str) -> Optional[Part]:
    return next((p for p in PART_LIBRARY if p.id == part_id), None)


def find_tcp(tcp_id: str) -> Optional[TcpFrame]:
    return next((t for t in TCP_LIBRARY if t.id == tcp_id), None)


# --------------------------------------------------------------------------- #
# Operation helpers — mirror of web-arc/src/lib/program.ts
# --------------------------------------------------------------------------- #


def _part_top_y(part: Part) -> float:
    d = part.dims
    base = part.pose.pos[1]
    if part.kind == "CYLINDER":
        return base + d.get("h", 0.18)
    if part.kind == "PLATE":
        return base + d.get("t", 0.02)
    if part.kind == "STEP":
        return base + d.get("h", 0.06) + d.get("topH", 0.08)
    return base + d.get("h", 0.15)


def _part_footprint(part: Part) -> dict:
    d = part.dims
    c = part.pose.pos
    y = _part_top_y(part)
    if part.kind == "CYLINDER":
        wx = wz = d.get("r", 0.14)
    elif part.kind == "STEP":
        wx, wz = d.get("topW", 0.28) / 2, d.get("topD", 0.22) / 2
    else:
        wx, wz = d.get("w", 0.40) / 2, d.get("d", 0.30) / 2
    inset = 0.04
    return {
        "x0": c[0] - wx + inset, "x1": c[0] + wx - inset,
        "z0": c[2] - wz + inset, "z1": c[2] + wz - inset, "y": y,
    }


def gen_picks(strategy: Strategy, part: Optional[Part]) -> List[Pick]:
    """Generate the default pick polyline for a strategy on a part's top face."""
    if part is None:
        return []
    fp = _part_footprint(part)
    n = (0.0, 1.0, 0.0)
    if strategy == "CONTOUR":
        return [
            Pick(point=(fp["x0"], fp["y"], fp["z0"]), normal=n),
            Pick(point=(fp["x1"], fp["y"], fp["z0"]), normal=n),
            Pick(point=(fp["x1"], fp["y"], fp["z1"]), normal=n),
            Pick(point=(fp["x0"], fp["y"], fp["z1"]), normal=n),
            Pick(point=(fp["x0"], fp["y"], fp["z0"]), normal=n),
        ]
    if strategy == "RASTER":
        pts: List[Pick] = []
        passes = 5
        for i in range(passes):
            z = fp["z0"] + (fp["z1"] - fp["z0"]) * (i / (passes - 1))
            if i % 2 == 0:
                pts.append(Pick(point=(fp["x0"], fp["y"], z), normal=n))
                pts.append(Pick(point=(fp["x1"], fp["y"], z), normal=n))
            else:
                pts.append(Pick(point=(fp["x1"], fp["y"], z), normal=n))
                pts.append(Pick(point=(fp["x0"], fp["y"], z), normal=n))
        return pts
    if strategy == "SEAM":
        z = (fp["z0"] + fp["z1"]) / 2
        return [
            Pick(point=(fp["x0"], fp["y"], z), normal=n),
            Pick(point=(fp["x1"], fp["y"], z), normal=n),
        ]
    return [Pick(point=((fp["x0"] + fp["x1"]) / 2, fp["y"], (fp["z0"] + fp["z1"]) / 2), normal=n)]


def make_op(op_id: int, kind: OpKind, name: Optional[str] = None) -> Operation:
    """Construct a default Operation. Picks are populated for the kind's default part."""
    part_id = OP_DEFAULT_PART[kind]
    tool_id = OP_DEFAULT_TOOL[kind]
    strategy: Strategy = "SEAM" if kind == "WELD" else "POINTS"
    weave = (
        Weave(type="SINE", amplitude=0.004, wavelength=0.012, edge_dwell=0.05)
        if kind == "WELD" else Weave()
    )
    picks = gen_picks(strategy, find_part(part_id))
    return Operation(
        id=op_id, name=name or f"{kind} {op_id}", enabled=True, kind=kind,
        part_id=part_id, tool_id=tool_id, tcp_id="tcp-tip",
        strategy=strategy,
        params=OperationParams(weave=weave, picks=picks),
    )


def default_job() -> Job:
    """The example pick-then-weld job seeded into a new project."""
    return Job(
        id="0142", name="CELL-07 PROGRAM", author="OP·KOSTA",
        active_tcp_id="tcp-tip", post_format="URScript",
        ops=[
            Operation(
                id=1, name="PICK BLANK", enabled=True, kind="PICKPLACE",
                part_id="part-box", tool_id="grip-2f", tcp_id="tcp-tip",
                strategy="POINTS",
                params=OperationParams(
                    standoff=5, approach=60, vel=40, acc=50, weave=Weave(),
                    picks=[Pick(point=(0.5, 0.15, 0.0), normal=(0, 1, 0))],
                ),
            ),
            Operation(
                id=2, name="WELD SEAM", enabled=True, kind="WELD",
                part_id="part-plate", tool_id="mig", tcp_id="tcp-weld",
                strategy="SEAM",
                params=OperationParams(
                    standoff=2, approach=50, vel=25, acc=40,
                    weave=Weave(type="SINE", amplitude=0.004, wavelength=0.012, edge_dwell=0.05),
                    picks=[
                        Pick(point=(0.40, 0.02, 0.0), normal=(0, 1, 0)),
                        Pick(point=(0.60, 0.02, 0.0), normal=(0, 1, 0)),
                    ],
                ),
            ),
        ],
    )


def make_default_doc(name: str = "Untitled Program") -> Doc:
    job = default_job()
    job.name = name
    return Doc(
        version=1,
        meta=DocMeta(name=name, author="OP·KOSTA", modified=_now_iso()),
        job=job,
        active_tcp_id="tcp-tip",
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# --------------------------------------------------------------------------- #
# File-backed store
# --------------------------------------------------------------------------- #

_PROJECT_ID_RE = re.compile(r"[^a-z0-9_-]+")


def safe_project_id(seed: str) -> str:
    """Slug-ify a name into a filesystem-safe project id."""
    s = _PROJECT_ID_RE.sub("-", seed.lower()).strip("-")
    return s or uuid.uuid4().hex[:8]


class ProjectNotFound(KeyError):
    pass


class ProjectInvalid(ValueError):
    pass


class ProjectStore:
    """JSON-file project store rooted at ``<repo>/data/projects``."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    # ---- discovery ------------------------------------------------------- #
    def _path(self, project_id: str) -> Path:
        # disallow any directory traversal
        clean = safe_project_id(project_id)
        return self.root / f"{clean}.arcjob.json"

    def list(self) -> List[dict]:
        out: List[dict] = []
        for p in sorted(self.root.glob("*.arcjob.json")):
            try:
                meta = json.loads(p.read_text())
            except Exception:  # noqa: BLE001
                continue
            project_id = p.stem.replace(".arcjob", "")
            out.append({
                "id": project_id,
                "name": (meta.get("meta") or {}).get("name") or project_id,
                "author": (meta.get("meta") or {}).get("author") or "OP",
                "modified": (meta.get("meta") or {}).get("modified") or "",
                "ops": len((meta.get("job") or {}).get("ops") or []),
            })
        return out

    # ---- CRUD ------------------------------------------------------------ #
    def load(self, project_id: str) -> Doc:
        p = self._path(project_id)
        if not p.is_file():
            raise ProjectNotFound(project_id)
        try:
            return Doc.model_validate_json(p.read_text())
        except ValidationError as e:
            raise ProjectInvalid(str(e)) from e

    def save(self, project_id: str, doc: Doc) -> Doc:
        doc.meta.modified = _now_iso()
        p = self._path(project_id)
        p.write_text(json.dumps(doc.model_dump(by_alias=True, exclude_none=True), indent=2))
        return doc

    def delete(self, project_id: str) -> bool:
        p = self._path(project_id)
        if not p.is_file():
            return False
        p.unlink()
        return True

    # ---- convenience editing -------------------------------------------- #
    def mutate(self, project_id: str, mutator) -> Doc:
        doc = self.load(project_id)
        mutator(doc)
        return self.save(project_id, doc)


# --------------------------------------------------------------------------- #
# Singleton
# --------------------------------------------------------------------------- #

_DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "data" / "projects"
_store: Optional[ProjectStore] = None


def get_project_store() -> ProjectStore:
    global _store
    if _store is None:
        _store = ProjectStore(_DEFAULT_ROOT)
    return _store


def reset_project_store(root: Optional[Path] = None) -> ProjectStore:
    """Test-friendly override."""
    global _store
    _store = ProjectStore(root or _DEFAULT_ROOT)
    return _store


__all__ = [
    "TCP_LIBRARY", "TOOL_LIBRARY", "PART_LIBRARY", "WEAVE_DEFAULT",
    "OP_DEFAULT_TOOL", "OP_DEFAULT_PART",
    "find_tool", "find_part", "find_tcp",
    "gen_picks", "make_op", "default_job", "make_default_doc",
    "safe_project_id", "ProjectNotFound", "ProjectInvalid",
    "ProjectStore", "get_project_store", "reset_project_store",
    "_ensure_iterable",
]


def _ensure_iterable(x) -> Iterable:  # re-exported for tests
    return x if isinstance(x, Iterable) else [x]
