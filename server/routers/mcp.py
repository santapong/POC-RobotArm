"""Minimal MCP (Model Context Protocol) server at POST /mcp.

Implements just enough of the 2024-11-05 wire format for any MCP client
(Claude Desktop, agents, ``mcp-cli``, …) to discover + call our project
tools. The transport is "Streamable HTTP" — clients POST a single JSON-RPC
2.0 request, we return a single JSON-RPC response with
``Content-Type: application/json``. No SSE / streaming is needed because
every tool here is synchronous.

The tools wrap the same ``ProjectStore`` and helpers the REST API uses
(``server.services.project_store``), so an MCP agent and the browser app
edit the same Doc JSON and stay consistent.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from server.models.project import Doc
from server.services.project_store import (
    OP_DEFAULT_PART,
    OP_DEFAULT_TOOL,
    PART_LIBRARY,
    ProjectInvalid,
    ProjectNotFound,
    TCP_LIBRARY,
    TOOL_LIBRARY,
    find_part,
    find_tool,
    gen_picks,
    get_project_store,
    make_default_doc,
    make_op,
    safe_project_id,
)

router = APIRouter(tags=["mcp"])

MCP_PROTOCOL_VERSION = "2024-11-05"
MCP_SERVER_INFO = {"name": "arc-ops", "version": "1.0.0"}

# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #


@dataclass
class Tool:
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[[Dict[str, Any]], Any]


def _doc_payload(doc: Doc) -> Dict[str, Any]:
    return doc.model_dump(by_alias=True, exclude_none=True)


def _mutate(project_id: str, fn: Callable[[Doc], None]) -> Dict[str, Any]:
    pid = safe_project_id(project_id)
    doc = get_project_store().mutate(pid, fn)
    return _doc_payload(doc)


def _require(d: Dict[str, Any], *keys: str) -> List[Any]:
    missing = [k for k in keys if k not in d or d[k] is None]
    if missing:
        raise ValueError(f"missing required argument(s): {', '.join(missing)}")
    return [d[k] for k in keys]


def _find_op(doc: Doc, op_id: int):
    op = next((o for o in doc.job.ops if o.id == op_id), None)
    if op is None:
        raise ValueError(f"op {op_id} not found in project")
    return op


# ---- list / load / save / delete / create -------------------------------- #


def _tool_list_projects(_: Dict[str, Any]) -> Any:
    return {"projects": get_project_store().list()}


def _tool_load_project(args: Dict[str, Any]) -> Any:
    [pid] = _require(args, "projectId")
    return _doc_payload(get_project_store().load(safe_project_id(pid)))


def _tool_save_project(args: Dict[str, Any]) -> Any:
    [pid, payload] = _require(args, "projectId", "doc")
    try:
        doc = Doc.model_validate(payload)
    except ValidationError as e:
        raise ProjectInvalid(str(e)) from e
    saved = get_project_store().save(safe_project_id(pid), doc)
    return _doc_payload(saved)


def _tool_delete_project(args: Dict[str, Any]) -> Any:
    [pid] = _require(args, "projectId")
    return {"deleted": get_project_store().delete(safe_project_id(pid))}


def _tool_create_project(args: Dict[str, Any]) -> Any:
    name = args.get("name") or "Untitled Program"
    pid = safe_project_id(args.get("projectId") or name)
    doc = make_default_doc(name=name)
    get_project_store().save(pid, doc)
    return {"projectId": pid, "doc": _doc_payload(doc)}


# ---- catalogs ------------------------------------------------------------ #


def _tool_list_catalogs(_: Dict[str, Any]) -> Any:
    return {
        "tools": [t.model_dump(by_alias=True, exclude_none=True) for t in TOOL_LIBRARY],
        "parts": [p.model_dump(by_alias=True, exclude_none=True) for p in PART_LIBRARY],
        "tcps":  [t.model_dump(by_alias=True, exclude_none=True) for t in TCP_LIBRARY],
        "opKinds": list(OP_DEFAULT_TOOL.keys()),
    }


# ---- operation editing --------------------------------------------------- #


def _tool_create_op(args: Dict[str, Any]) -> Any:
    [pid, kind] = _require(args, "projectId", "kind")
    name = args.get("name")
    def m(doc: Doc) -> None:
        nid = max((o.id for o in doc.job.ops), default=0) + 1
        doc.job.ops.append(make_op(nid, kind, name=name))
    return _mutate(pid, m)


def _tool_delete_op(args: Dict[str, Any]) -> Any:
    [pid, op_id] = _require(args, "projectId", "opId")
    def m(doc: Doc) -> None:
        doc.job.ops = [o for o in doc.job.ops if o.id != op_id]
    return _mutate(pid, m)


def _tool_set_tool(args: Dict[str, Any]) -> Any:
    [pid, op_id, tool_id] = _require(args, "projectId", "opId", "toolId")
    if not find_tool(tool_id):
        raise ValueError(f"unknown tool '{tool_id}'")
    def m(doc: Doc) -> None:
        _find_op(doc, op_id).tool_id = tool_id
    return _mutate(pid, m)


def _tool_set_part(args: Dict[str, Any]) -> Any:
    [pid, op_id, part_id] = _require(args, "projectId", "opId", "partId")
    part = find_part(part_id)
    if not part:
        raise ValueError(f"unknown part '{part_id}'")
    def m(doc: Doc) -> None:
        op = _find_op(doc, op_id)
        op.part_id = part_id
        op.params.picks = gen_picks(op.strategy, part)
    return _mutate(pid, m)


def _tool_set_tcp(args: Dict[str, Any]) -> Any:
    [pid, op_id, tcp_id] = _require(args, "projectId", "opId", "tcpId")
    def m(doc: Doc) -> None:
        _find_op(doc, op_id).tcp_id = tcp_id
    return _mutate(pid, m)


def _tool_set_strategy(args: Dict[str, Any]) -> Any:
    [pid, op_id, strategy] = _require(args, "projectId", "opId", "strategy")
    def m(doc: Doc) -> None:
        op = _find_op(doc, op_id)
        op.strategy = strategy
        op.params.picks = gen_picks(strategy, find_part(op.part_id))
    return _mutate(pid, m)


def _tool_set_weave(args: Dict[str, Any]) -> Any:
    [pid, op_id, type_] = _require(args, "projectId", "opId", "type")
    amp = args.get("amplitude")
    wl = args.get("wavelength")
    dwell = args.get("edgeDwell")
    def m(doc: Doc) -> None:
        op = _find_op(doc, op_id)
        op.params.weave.type = type_
        if amp is not None: op.params.weave.amplitude = float(amp)
        if wl is not None: op.params.weave.wavelength = float(wl)
        if dwell is not None: op.params.weave.edge_dwell = float(dwell)
    return _mutate(pid, m)


_PARAM_KEYS = {"vel", "acc", "standoff", "approach"}


def _tool_set_op_param(args: Dict[str, Any]) -> Any:
    [pid, op_id, key, value] = _require(args, "projectId", "opId", "key", "value")
    if key in _PARAM_KEYS:
        def m_param(doc: Doc) -> None:
            op = _find_op(doc, op_id)
            setattr(op.params, key, float(value))
        return _mutate(pid, m_param)
    if key == "enabled":
        def m_enabled(doc: Doc) -> None:
            _find_op(doc, op_id).enabled = bool(value)
        return _mutate(pid, m_enabled)
    if key == "name":
        def m_name(doc: Doc) -> None:
            _find_op(doc, op_id).name = str(value)
        return _mutate(pid, m_name)
    raise ValueError(f"unsupported param key '{key}'")


def _tool_add_pick(args: Dict[str, Any]) -> Any:
    [pid, op_id, point, normal] = _require(args, "projectId", "opId", "point", "normal")
    def m(doc: Doc) -> None:
        from server.models.project import Pick
        _find_op(doc, op_id).params.picks.append(
            Pick(point=tuple(point), normal=tuple(normal)),
        )
    return _mutate(pid, m)


# ---- registry ------------------------------------------------------------ #

_PROJECT_ID_S = {"type": "string", "description": "Project id (slug or name)."}
_OP_ID_S = {"type": "integer", "description": "Operation id (1-based)."}
_VEC3_S = {"type": "array", "items": {"type": "number"}, "minItems": 3, "maxItems": 3}

TOOLS: List[Tool] = [
    Tool("list_projects", "List every saved project (id + meta + op count).",
         {"type": "object", "properties": {}, "additionalProperties": False},
         _tool_list_projects),
    Tool("load_project", "Load a project by id and return its Doc JSON.",
         {"type": "object", "required": ["projectId"], "properties": {"projectId": _PROJECT_ID_S}},
         _tool_load_project),
    Tool("save_project", "Save (create or overwrite) a project from a Doc JSON.",
         {"type": "object", "required": ["projectId", "doc"], "properties": {"projectId": _PROJECT_ID_S, "doc": {"type": "object"}}},
         _tool_save_project),
    Tool("delete_project", "Delete a project by id.",
         {"type": "object", "required": ["projectId"], "properties": {"projectId": _PROJECT_ID_S}},
         _tool_delete_project),
    Tool("create_project", "Create a new project from the default template.",
         {"type": "object", "properties": {"projectId": _PROJECT_ID_S, "name": {"type": "string"}}},
         _tool_create_project),

    Tool("list_catalogs", "List the tool / part / TCP catalogs and op kinds the editor knows about.",
         {"type": "object", "properties": {}, "additionalProperties": False},
         _tool_list_catalogs),

    Tool("create_op", "Append a new operation to a project. kind ∈ PICKPLACE|WELD|MILL|DISPENSE.",
         {"type": "object", "required": ["projectId", "kind"],
          "properties": {"projectId": _PROJECT_ID_S, "kind": {"type": "string", "enum": list(OP_DEFAULT_TOOL.keys())}, "name": {"type": "string"}}},
         _tool_create_op),
    Tool("delete_op", "Remove an operation from a project.",
         {"type": "object", "required": ["projectId", "opId"],
          "properties": {"projectId": _PROJECT_ID_S, "opId": _OP_ID_S}},
         _tool_delete_op),
    Tool("set_tool", "Set an op's end-effector (toolId ∈ catalogs).",
         {"type": "object", "required": ["projectId", "opId", "toolId"],
          "properties": {"projectId": _PROJECT_ID_S, "opId": _OP_ID_S, "toolId": {"type": "string"}}},
         _tool_set_tool),
    Tool("set_part", "Set an op's part (regenerates picks for the current strategy).",
         {"type": "object", "required": ["projectId", "opId", "partId"],
          "properties": {"projectId": _PROJECT_ID_S, "opId": _OP_ID_S, "partId": {"type": "string"}}},
         _tool_set_part),
    Tool("set_tcp", "Set an op's TCP frame.",
         {"type": "object", "required": ["projectId", "opId", "tcpId"],
          "properties": {"projectId": _PROJECT_ID_S, "opId": _OP_ID_S, "tcpId": {"type": "string"}}},
         _tool_set_tcp),
    Tool("set_strategy", "Set an op's strategy ∈ POINTS|CONTOUR|RASTER|SEAM (regenerates picks).",
         {"type": "object", "required": ["projectId", "opId", "strategy"],
          "properties": {"projectId": _PROJECT_ID_S, "opId": _OP_ID_S, "strategy": {"type": "string", "enum": ["POINTS", "CONTOUR", "RASTER", "SEAM"]}}},
         _tool_set_strategy),
    Tool("set_weave", "Set an op's weld weave. type ∈ NONE|SINE|ZIGZAG|TRIANGLE|TRAPEZOID.",
         {"type": "object", "required": ["projectId", "opId", "type"],
          "properties": {"projectId": _PROJECT_ID_S, "opId": _OP_ID_S,
                         "type": {"type": "string", "enum": ["NONE", "SINE", "ZIGZAG", "TRIANGLE", "TRAPEZOID"]},
                         "amplitude": {"type": "number"}, "wavelength": {"type": "number"}, "edgeDwell": {"type": "number"}}},
         _tool_set_weave),
    Tool("set_op_param", "Set an op param: key ∈ vel|acc|standoff|approach|enabled|name.",
         {"type": "object", "required": ["projectId", "opId", "key", "value"],
          "properties": {"projectId": _PROJECT_ID_S, "opId": _OP_ID_S,
                         "key": {"type": "string", "enum": ["vel", "acc", "standoff", "approach", "enabled", "name"]},
                         "value": {}}},
         _tool_set_op_param),
    Tool("add_pick", "Append a pick (point + normal) to an op's pick polyline.",
         {"type": "object", "required": ["projectId", "opId", "point", "normal"],
          "properties": {"projectId": _PROJECT_ID_S, "opId": _OP_ID_S, "point": _VEC3_S, "normal": _VEC3_S}},
         _tool_add_pick),
]

_BY_NAME: Dict[str, Tool] = {t.name: t for t in TOOLS}


# --------------------------------------------------------------------------- #
# JSON-RPC dispatch
# --------------------------------------------------------------------------- #

def _rpc_result(req_id: Any, result: Any) -> Dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _rpc_error(req_id: Any, code: int, message: str, data: Any = None) -> Dict[str, Any]:
    err: Dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


def _content(payload: Any) -> Dict[str, Any]:
    return {"content": [{"type": "text", "text": json.dumps(payload, indent=2)}]}


def _dispatch(method: str, params: Dict[str, Any], req_id: Any) -> Optional[Dict[str, Any]]:
    if method == "initialize":
        return _rpc_result(req_id, {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": MCP_SERVER_INFO,
        })

    if method in ("notifications/initialized", "notifications/cancelled"):
        # JSON-RPC notification: never reply.
        return None

    if method == "ping":
        return _rpc_result(req_id, {})

    if method == "tools/list":
        return _rpc_result(req_id, {
            "tools": [
                {"name": t.name, "description": t.description, "inputSchema": t.input_schema}
                for t in TOOLS
            ],
        })

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        tool = _BY_NAME.get(name or "")
        if tool is None:
            return _rpc_error(req_id, -32602, f"unknown tool: {name}")
        try:
            payload = tool.handler(args)
        except ProjectNotFound as e:
            return _rpc_result(req_id, {**_content({"error": f"project '{e.args[0]}' not found"}), "isError": True})
        except (ValueError, ProjectInvalid) as e:
            return _rpc_result(req_id, {**_content({"error": str(e)}), "isError": True})
        return _rpc_result(req_id, _content(payload))

    return _rpc_error(req_id, -32601, f"method not found: {method}")


@router.post("/mcp")
async def mcp_endpoint(request: Request) -> JSONResponse:
    """Streamable-HTTP MCP transport — one JSON-RPC request → one JSON response."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(_rpc_error(None, -32700, "parse error"), status_code=400)

    # JSON-RPC may be a single object or a batch — handle both.
    requests = body if isinstance(body, list) else [body]
    responses: List[Dict[str, Any]] = []
    for msg in requests:
        if not isinstance(msg, dict):
            responses.append(_rpc_error(None, -32600, "invalid request"))
            continue
        method = msg.get("method")
        if not isinstance(method, str):
            responses.append(_rpc_error(msg.get("id"), -32600, "invalid request"))
            continue
        params = msg.get("params") or {}
        if not isinstance(params, dict):
            responses.append(_rpc_error(msg.get("id"), -32602, "invalid params"))
            continue
        resp = _dispatch(method, params, msg.get("id"))
        if resp is not None:
            responses.append(resp)

    if not responses:
        # All inputs were notifications — empty 202 per MCP spec.
        return JSONResponse(content=None, status_code=202)
    return JSONResponse(responses[0] if not isinstance(body, list) else responses)


__all__ = ["router", "TOOLS", "MCP_PROTOCOL_VERSION"]
