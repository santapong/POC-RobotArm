"""Tests for the project store + REST API + /mcp JSON-RPC endpoint."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from server.main import create_app
from server.services import project_store as ps


@pytest.fixture()
def client(tmp_path: Path) -> TestClient:
    # Point the project store at an isolated temp dir for each test.
    ps.reset_project_store(tmp_path / "projects")
    return TestClient(create_app())


# --------------------------------------------------------------------------- #
# REST
# --------------------------------------------------------------------------- #

def _rpc(client: TestClient, method: str, params: dict | None = None, req_id: int = 1) -> dict:
    body = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        body["params"] = params
    r = client.post("/mcp", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _call_tool(client: TestClient, name: str, args: dict, req_id: int = 1) -> dict:
    resp = _rpc(client, "tools/call", {"name": name, "arguments": args}, req_id=req_id)
    assert "error" not in resp, resp
    text = resp["result"]["content"][0]["text"]
    return json.loads(text)


def test_rest_crud_roundtrip(client: TestClient) -> None:
    # initially empty
    r = client.get("/api/projects")
    assert r.status_code == 200
    assert r.json() == []

    # create via MCP create_project, then load via REST
    out = _call_tool(client, "create_project", {"name": "Cell 7 Build"})
    pid = out["projectId"]
    assert pid == "cell-7-build"
    assert out["doc"]["job"]["ops"], "default job must seed at least one op"

    r = client.get(f"/api/projects/{pid}")
    assert r.status_code == 200
    doc = r.json()
    assert doc["meta"]["name"] == "Cell 7 Build"
    assert "ops" in doc["job"]

    # save (round-trip) — modify meta and PUT
    doc["meta"]["author"] = "OP·TEST"
    r = client.put(f"/api/projects/{pid}", json=doc)
    assert r.status_code == 200
    assert r.json()["meta"]["author"] == "OP·TEST"

    # listing now shows it
    r = client.get("/api/projects")
    listing = r.json()
    assert any(p["id"] == pid and p["name"] == "Cell 7 Build" for p in listing)


def test_mcp_initialize_and_tools_list(client: TestClient) -> None:
    init = _rpc(client, "initialize", {})
    assert init["result"]["protocolVersion"] == "2024-11-05"
    assert init["result"]["serverInfo"]["name"] == "arc-ops"
    assert init["result"]["capabilities"]["tools"] is not None

    tools = _rpc(client, "tools/list", {})["result"]["tools"]
    names = {t["name"] for t in tools}
    # ensure the critical editing tools are advertised
    for needed in (
        "list_projects", "load_project", "save_project", "create_project",
        "list_catalogs", "create_op", "delete_op",
        "set_tool", "set_part", "set_tcp", "set_strategy", "set_weave",
        "set_op_param", "add_pick",
    ):
        assert needed in names, f"missing MCP tool: {needed}"


def test_mcp_create_op_and_set_weave(client: TestClient) -> None:
    _call_tool(client, "create_project", {"name": "MCP test", "projectId": "mcp-test"})

    after_add = _call_tool(client, "create_op", {"projectId": "mcp-test", "kind": "WELD"})
    ops_after = after_add["job"]["ops"]
    weld = next(o for o in ops_after if o["kind"] == "WELD" and o["name"].startswith("WELD"))
    assert weld["params"]["weave"]["type"] == "SINE"  # default for a WELD op

    after_weave = _call_tool(client, "set_weave", {
        "projectId": "mcp-test", "opId": weld["id"],
        "type": "TRAPEZOID", "amplitude": 0.006, "wavelength": 0.018,
    })
    edited = next(o for o in after_weave["job"]["ops"] if o["id"] == weld["id"])
    assert edited["params"]["weave"]["type"] == "TRAPEZOID"
    assert edited["params"]["weave"]["amplitude"] == pytest.approx(0.006)
    assert edited["params"]["weave"]["wavelength"] == pytest.approx(0.018)


def test_mcp_set_part_regenerates_picks(client: TestClient) -> None:
    out = _call_tool(client, "create_project", {"name": "picks", "projectId": "picks"})
    op_id = next(o["id"] for o in out["doc"]["job"]["ops"] if o["kind"] == "PICKPLACE")

    after = _call_tool(client, "set_strategy", {
        "projectId": "picks", "opId": op_id, "strategy": "CONTOUR",
    })
    op = next(o for o in after["job"]["ops"] if o["id"] == op_id)
    # CONTOUR generates 5 corner points on the part's top face
    assert len(op["params"]["picks"]) == 5
    # all picks have a [0,1,0] normal (the top face)
    for p in op["params"]["picks"]:
        assert tuple(p["normal"]) == (0, 1, 0)


def test_mcp_unknown_tool_returns_error(client: TestClient) -> None:
    resp = _rpc(client, "tools/call", {"name": "no_such_tool", "arguments": {}})
    assert "error" in resp
    assert resp["error"]["code"] == -32602


def test_mcp_load_unknown_project_returns_isError(client: TestClient) -> None:
    resp = _rpc(client, "tools/call", {"name": "load_project", "arguments": {"projectId": "missing"}})
    assert resp["result"]["isError"] is True
    text = json.loads(resp["result"]["content"][0]["text"])
    assert "not found" in text["error"]


def test_mcp_notification_returns_202(client: TestClient) -> None:
    r = client.post("/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert r.status_code == 202


def test_mcp_unknown_notification_is_silent(client: TestClient) -> None:
    # JSON-RPC: server MUST NOT reply to a notification, even for unknown
    # methods. Absence of an `id` field is what makes it a notification.
    r = client.post("/mcp", json={"jsonrpc": "2.0", "method": "totally/unknown"})
    assert r.status_code == 202


def test_mcp_delete_unknown_project_is_error(client: TestClient) -> None:
    # Match REST 404 semantics: deleting a non-existent project surfaces as a
    # tool-level isError, not a misleading {deleted:false} success.
    resp = _rpc(client, "tools/call", {
        "name": "delete_project",
        "arguments": {"projectId": "no-such-project"},
    })
    assert resp["result"]["isError"] is True
    text = json.loads(resp["result"]["content"][0]["text"])
    assert "not found" in text["error"]


def test_mutate_skips_save_on_noop(client: TestClient) -> None:
    # Setting the tool to its current value mustn't bump meta.modified.
    out = _call_tool(client, "create_project", {"name": "noop", "projectId": "noop"})
    op_id = out["doc"]["job"]["ops"][0]["id"]
    current_tool = out["doc"]["job"]["ops"][0]["toolId"]
    modified_before = ps.get_project_store().load("noop").meta.modified

    # Call set_tool with the same toolId → mutate should detect no change and skip save.
    _call_tool(client, "set_tool", {"projectId": "noop", "opId": op_id, "toolId": current_tool})
    modified_after = ps.get_project_store().load("noop").meta.modified
    assert modified_after == modified_before, "meta.modified must not bump on no-op edit"


def test_mcp_call_handles_storage_oserror(client: TestClient, tmp_path, monkeypatch) -> None:
    # Force every save through a write that raises OSError; the tool should
    # come back as a clean isError, not a 500.
    def boom(*a, **kw): raise OSError(28, "no space left on device")
    monkeypatch.setattr("pathlib.Path.write_text", boom)
    resp = _rpc(client, "tools/call", {
        "name": "create_project",
        "arguments": {"name": "boom"},
    })
    assert resp["result"]["isError"] is True
    text = json.loads(resp["result"]["content"][0]["text"])
    assert "storage error" in text["error"]


def test_mcp_list_catalogs_shape(client: TestClient) -> None:
    out = _call_tool(client, "list_catalogs", {})
    assert {t["id"] for t in out["tools"]} >= {"grip-2f", "mig", "spindle"}
    assert {p["id"] for p in out["parts"]} >= {"part-box", "part-cyl", "part-plate", "part-step"}
    assert {t["id"] for t in out["tcps"]} >= {"tcp-flange", "tcp-tip", "tcp-weld"}
    assert {r["id"] for r in out["robots"]} >= {"ur5e", "abb-irb1300-10-115", "fanuc-lrmate-200id-7l"}
    assert out["defaultRobotId"] == "ur5e"
    assert set(out["opKinds"]) == {"PICKPLACE", "WELD", "MILL", "DISPENSE"}


def test_mcp_list_robots_shape(client: TestClient) -> None:
    out = _call_tool(client, "list_robots", {})
    assert out["defaultRobotId"] == "ur5e"
    ids = {r["id"] for r in out["robots"]}
    # at least the ABB IRB 1300 family + UR baseline are present
    assert ids >= {"ur5e", "abb-irb1300-7-140", "abb-irb1300-10-115", "abb-irb1300-11-090"}
    # each entry has the spec fields the editor consumes
    for r in out["robots"]:
        assert isinstance(r["payload"], (int, float))
        assert isinstance(r["reach"], (int, float))
        assert r["dof"] == 6
        assert len(r["jointLimits"]) == 6
        assert len(r["maxJointVel"]) == 6
        # link lengths must include the five named fields
        assert {"baseHeight", "upperArm", "forearm", "wristOffset", "flangeOffset"} <= set(r["links"].keys())


def test_mcp_set_robot_updates_doc_and_rejects_unknown(client: TestClient) -> None:
    _call_tool(client, "create_project", {"name": "rbtest", "projectId": "rbtest"})

    # set to a valid robot
    out = _call_tool(client, "set_robot", {"projectId": "rbtest", "robotId": "abb-irb1300-10-115"})
    assert out["robotId"] == "abb-irb1300-10-115"

    # unknown robot rejected with a clean isError
    resp = _rpc(client, "tools/call", {
        "name": "set_robot",
        "arguments": {"projectId": "rbtest", "robotId": "totally-fake-arm"},
    })
    assert resp["result"]["isError"] is True
    text = json.loads(resp["result"]["content"][0]["text"])
    assert "unknown robotId" in text["error"]


def test_doc_roundtrip_preserves_robot_id(client: TestClient) -> None:
    # v2 doc with robotId round-trips through PUT/GET.
    _call_tool(client, "create_project", {"name": "rt", "projectId": "rt"})
    _call_tool(client, "set_robot", {"projectId": "rt", "robotId": "abb-irb120"})

    r = client.get("/api/projects/rt")
    assert r.status_code == 200
    doc = r.json()
    assert doc["robotId"] == "abb-irb120"
    assert doc["version"] == 2

    # PUT it straight back unchanged
    r = client.put("/api/projects/rt", json=doc)
    assert r.status_code == 200
    assert r.json()["robotId"] == "abb-irb120"
