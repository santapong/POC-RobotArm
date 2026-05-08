"""Tests for :class:`src.drivers.abb.RWSDriver`.

The driver opens HTTPS connections to a real or virtual ABB controller, so
we exercise it against a mocked session. The session interface is small —
``get(path, **kw)`` and ``post(path, data=None, files=None, **kw)`` both
return ``(status, headers, body_bytes)`` — which makes a
:class:`unittest.mock.MagicMock` configured with ``.return_value`` and
``.side_effect`` more than enough.

Where realism matters (RWS JSON shapes, RAPID source cleanliness) we use
fixtures derived from ABB's documentation samples; field values are
plausible but not from a specific controller.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from src.drivers import Driver, RobotState, RWSDriver

# ---------------------------------------------------------------------------
# Fixtures: realistic RWS JSON payloads
# ---------------------------------------------------------------------------


def _system_payload() -> bytes:
    """A skeleton ``/rw/system`` body — used only for connect()."""
    return json.dumps(
        {
            "_links": {"self": {"href": "/rw/system"}},
            "_embedded": {
                "_state": [
                    {
                        "name": "ABB",
                        "rwversion": "7.4",
                        "robotware": "7.4.0",
                    }
                ]
            },
        }
    ).encode("utf-8")


def _jointtarget_payload() -> bytes:
    """Realistic jointtarget JSON: 6 joints in degrees."""
    return json.dumps(
        {
            "_embedded": {
                "_state": [
                    {
                        "_type": "rap-jointtarget",
                        "rax_1": 0.0,
                        "rax_2": 90.0,
                        "rax_3": -45.0,
                        "rax_4": 30.0,
                        "rax_5": 60.0,
                        "rax_6": -90.0,
                        "eax_a": "9E9",
                        "eax_b": "9E9",
                        "eax_c": "9E9",
                        "eax_d": "9E9",
                        "eax_e": "9E9",
                        "eax_f": "9E9",
                    }
                ]
            }
        }
    ).encode("utf-8")


def _robtarget_payload() -> bytes:
    """Realistic robtarget JSON: position in mm, quaternion (w, x, y, z)."""
    return json.dumps(
        {
            "_embedded": {
                "_state": [
                    {
                        "_type": "rap-robtarget",
                        "x": 1234.5,
                        "y": -200.0,
                        "z": 567.89,
                        "q1": 0.7071,  # w
                        "q2": 0.0,     # x
                        "q3": 0.7071,  # y
                        "q4": 0.0,     # z
                        "cf1": 0,
                        "cf4": 0,
                        "cf6": 0,
                        "cfx": 0,
                        "eax_a": "9E9",
                        "eax_b": "9E9",
                        "eax_c": "9E9",
                        "eax_d": "9E9",
                        "eax_e": "9E9",
                        "eax_f": "9E9",
                    }
                ]
            }
        }
    ).encode("utf-8")


def _exec_state_payload(running: bool) -> bytes:
    """Execution-state JSON: ``"running"`` or ``"stopped"``."""
    return json.dumps(
        {
            "_embedded": {
                "_state": [
                    {
                        "_type": "rap-execution",
                        "ctrlexecstate": "running" if running else "stopped",
                        "cycle": "once",
                    }
                ]
            }
        }
    ).encode("utf-8")


# ---------------------------------------------------------------------------
# Mock session helpers
# ---------------------------------------------------------------------------


def _ok(body: bytes = b"") -> tuple[int, dict, bytes]:
    return (200, {}, body)


def _no_content() -> tuple[int, dict, bytes]:
    return (204, {}, b"")


def _build_session(
    get_map: dict[str, tuple[int, dict, bytes]] | None = None,
    post_map: dict[str, tuple[int, dict, bytes]] | None = None,
    default_get: tuple[int, dict, bytes] = (200, {}, b""),
    default_post: tuple[int, dict, bytes] = (204, {}, b""),
) -> MagicMock:
    """Build a MagicMock session whose verbs dispatch on the *path prefix*.

    Path matching is a simple ``startswith`` against the keys of the maps;
    the longest matching prefix wins. This lets a single fixture answer
    e.g. ``/rw/rapid/execution?json=1`` (state) vs ``...?action=start``
    differently.
    """
    get_map = get_map or {}
    post_map = post_map or {}

    def _match(path: str, table: dict, default):
        # Prefer query-string matches first so e.g. ?action=start and ?json=1
        # land on different responses; fall back to the path stem.
        candidates = sorted(table.keys(), key=len, reverse=True)
        for key in candidates:
            if key in path:
                return table[key]
        return default

    session = MagicMock(name="DigestSession")

    def _get(path, **kwargs):
        return _match(path, get_map, default_get)

    def _post(path, data=None, files=None, **kwargs):
        return _match(path, post_map, default_post)

    session.get.side_effect = _get
    session.post.side_effect = _post
    return session


# ---------------------------------------------------------------------------
# Driver Protocol conformance
# ---------------------------------------------------------------------------


def test_rws_driver_satisfies_driver_protocol():
    session = _build_session()
    drv = RWSDriver(host="192.0.2.10", session=session)
    assert isinstance(drv, Driver)
    assert drv.name == "abb:192.0.2.10@443"
    assert drv.dof == 6
    for method in (
        "connect",
        "disconnect",
        "is_connected",
        "get_state",
        "move_joint",
        "move_linear",
        "run_program",
        "stop",
    ):
        assert callable(getattr(drv, method)), method


def test_rws_version_flag_is_validated():
    with pytest.raises(ValueError):
        RWSDriver(host="x", session=MagicMock(), rws_version="0.9")


# ---------------------------------------------------------------------------
# connect / disconnect
# ---------------------------------------------------------------------------


def test_connect_calls_system_endpoint_and_marks_connected():
    session = _build_session(get_map={"/rw/system": _ok(_system_payload())})
    drv = RWSDriver(host="192.0.2.10", session=session)

    assert drv.is_connected() is False
    drv.connect()
    assert drv.is_connected() is True

    # The first GET issued must be /rw/system.
    first_get = session.get.call_args_list[0]
    assert "/rw/system" in first_get.args[0]


def test_connect_failure_raises_connection_error():
    session = _build_session(default_get=(500, {}, b"controller offline"))
    drv = RWSDriver(host="x", session=session)
    with pytest.raises(ConnectionError) as excinfo:
        drv.connect()
    assert "500" in str(excinfo.value)


def test_connect_auth_failure_raises_permission_error():
    session = _build_session(default_get=(401, {}, b"unauthorized"))
    drv = RWSDriver(host="x", session=session)
    with pytest.raises(PermissionError):
        drv.connect()


def test_disconnect_is_idempotent_and_releases_mastership():
    session = _build_session()
    drv = RWSDriver(host="x", session=session)
    drv.connect = lambda: None  # avoid network
    drv._connected = True
    drv._has_mastership = True

    drv.disconnect()
    assert drv.is_connected() is False
    # Second call must be a safe no-op.
    drv.disconnect()
    assert drv.is_connected() is False
    # Mastership release must have been POSTed.
    posted_paths = [c.args[0] for c in session.post.call_args_list]
    assert any("/rw/mastership?action=release" in p for p in posted_paths)


# ---------------------------------------------------------------------------
# get_state — unit conversions
# ---------------------------------------------------------------------------


def test_get_state_parses_joints_pose_and_running_flag():
    session = _build_session(
        get_map={
            "/rw/motionsystem/mechunits/ROB_1/jointtarget": _ok(_jointtarget_payload()),
            "/rw/motionsystem/mechunits/ROB_1/robtarget": _ok(_robtarget_payload()),
            "/rw/rapid/execution": _ok(_exec_state_payload(running=True)),
        }
    )
    drv = RWSDriver(host="x", session=session)
    state = drv.get_state()
    assert isinstance(state, RobotState)

    # Joints: degrees -> radians. Joint 2 was 90deg -> pi/2.
    import math
    assert state.joints_rad[0] == pytest.approx(0.0)
    assert state.joints_rad[1] == pytest.approx(math.pi / 2)
    assert state.joints_rad[2] == pytest.approx(-math.pi / 4)
    assert state.joints_rad[5] == pytest.approx(-math.pi / 2)

    # Pose: mm -> m, quaternion preserved as wxyz.
    assert state.tcp_xyz_m == pytest.approx((1.2345, -0.2, 0.56789))
    assert state.tcp_quat_wxyz == pytest.approx((0.7071, 0.0, 0.7071, 0.0))

    # Execution state: "running" -> True.
    assert state.moving is True
    assert state.error is None


def test_get_state_running_false_when_stopped():
    session = _build_session(
        get_map={
            "/rw/motionsystem/mechunits/ROB_1/jointtarget": _ok(_jointtarget_payload()),
            "/rw/motionsystem/mechunits/ROB_1/robtarget": _ok(_robtarget_payload()),
            "/rw/rapid/execution": _ok(_exec_state_payload(running=False)),
        }
    )
    drv = RWSDriver(host="x", session=session)
    state = drv.get_state()
    assert state.moving is False


# ---------------------------------------------------------------------------
# run_program — sequence of HTTP calls
# ---------------------------------------------------------------------------


def test_run_program_emits_full_sequence_in_correct_order():
    """The full mastership -> upload -> load -> PP -> motors -> start -> release dance."""
    # Execution polls return "stopped" immediately so wait=True returns fast.
    session = _build_session(
        get_map={"/rw/rapid/execution": _ok(_exec_state_payload(running=False))},
    )
    drv = RWSDriver(host="x", session=session)

    drv.run_program("MODULE main\nENDMODULE\n", name="oneshot", wait=True, timeout_s=2.0)

    posted_paths = [c.args[0] for c in session.post.call_args_list]
    expected_order = [
        "/rw/mastership?action=request",
        "/fileservice/$HOME$/oneshot.mod",
        "/rw/rapid/tasks/T_ROB1/loadmodule",
        "resetpp",  # /rw/rapid/execution?action=resetpp
        "ctrl-state?action=setctrlstate",
        "/rw/rapid/execution?action=start",
        "/rw/mastership?action=release",
    ]
    # Walk both lists; each expected fragment must appear in order.
    cursor = 0
    for fragment in expected_order:
        while cursor < len(posted_paths) and fragment not in posted_paths[cursor]:
            cursor += 1
        assert cursor < len(posted_paths), (
            f"missing {fragment!r} in posted paths: {posted_paths}"
        )
        cursor += 1


def test_run_program_uploads_source_as_multipart_file():
    session = _build_session(
        get_map={"/rw/rapid/execution": _ok(_exec_state_payload(running=False))},
    )
    drv = RWSDriver(host="x", session=session)
    src = "MODULE main\n  PROC main()\n  ENDPROC\nENDMODULE\n"

    drv.run_program(src, name="prog42", wait=False)

    # Find the upload call by path; check the kw.files dict carried our source.
    upload_calls = [
        c
        for c in session.post.call_args_list
        if "/fileservice/$HOME$/prog42.mod" in c.args[0]
    ]
    assert len(upload_calls) == 1, upload_calls
    kwargs = upload_calls[0].kwargs
    assert "files" in kwargs and kwargs["files"]
    filename, content = kwargs["files"]["file"]
    assert filename == "prog42.mod"
    assert b"MODULE main" in content


def test_run_program_releases_mastership_even_on_failure():
    """If load fails midway, mastership must still be released."""

    def _post(path, data=None, files=None, **kwargs):
        if "loadmodule" in path:
            return (500, {}, b"unable to load")
        return (204, {}, b"")

    session = MagicMock()
    session.get.return_value = _ok(_exec_state_payload(running=False))
    session.post.side_effect = _post

    drv = RWSDriver(host="x", session=session)

    with pytest.raises(RuntimeError):
        drv.run_program("MODULE main\nENDMODULE\n", name="oneshot", wait=False)

    posted_paths = [c.args[0] for c in session.post.call_args_list]
    assert any("/rw/mastership?action=release" in p for p in posted_paths)


# ---------------------------------------------------------------------------
# move_joint / move_linear: lower into RAPID + run_program
# ---------------------------------------------------------------------------


def test_move_joint_builds_moveabsj_program_and_runs_it():
    session = _build_session(
        get_map={"/rw/rapid/execution": _ok(_exec_state_payload(running=False))},
    )
    drv = RWSDriver(host="x", session=session)

    drv.move_joint([0.0, 0.5, -0.5, 0.1, 0.2, 0.3], wait=False)

    # The upload body must contain a MoveAbsJ instruction.
    upload_calls = [
        c
        for c in session.post.call_args_list
        if "/fileservice/$HOME$/" in c.args[0] and ".mod" in c.args[0]
    ]
    assert len(upload_calls) == 1
    _filename, body = upload_calls[0].kwargs["files"]["file"]
    text = body.decode("utf-8")
    assert "MoveAbsJ" in text
    # Joints are converted to degrees in the RAPID source.
    assert "MODULE oneshot" in text


def test_move_joint_rejects_wrong_dof():
    session = _build_session()
    drv = RWSDriver(host="x", session=session, dof=6)
    with pytest.raises(ValueError):
        drv.move_joint([0.0, 0.1], wait=False)


def test_move_linear_builds_movel_program_and_runs_it():
    session = _build_session(
        get_map={"/rw/rapid/execution": _ok(_exec_state_payload(running=False))},
    )
    drv = RWSDriver(host="x", session=session)

    drv.move_linear(
        xyz_m=[0.4, 0.0, 0.5],
        quat_wxyz=[1.0, 0.0, 0.0, 0.0],
        speed_m_s=0.1,
        wait=False,
    )

    upload_calls = [
        c
        for c in session.post.call_args_list
        if "/fileservice/$HOME$/" in c.args[0] and ".mod" in c.args[0]
    ]
    assert len(upload_calls) == 1
    _filename, body = upload_calls[0].kwargs["files"]["file"]
    text = body.decode("utf-8")
    assert "MoveL" in text
    # Position is converted to mm: 0.4m -> 400, 0.5m -> 500.
    assert "400" in text and "500" in text


def test_move_linear_validates_arguments():
    session = _build_session()
    drv = RWSDriver(host="x", session=session)
    with pytest.raises(ValueError):
        drv.move_linear(xyz_m=[0.0, 0.1], quat_wxyz=[1.0, 0.0, 0.0, 0.0], wait=False)
    with pytest.raises(ValueError):
        drv.move_linear(xyz_m=[0.0, 0.1, 0.2], quat_wxyz=[1.0, 0.0, 0.0], wait=False)


# ---------------------------------------------------------------------------
# stop / error mapping
# ---------------------------------------------------------------------------


def test_stop_posts_action_stop():
    session = _build_session()
    drv = RWSDriver(host="x", session=session)
    drv.stop()
    posted_paths = [c.args[0] for c in session.post.call_args_list]
    assert any("/rw/rapid/execution?action=stop" in p for p in posted_paths)


def test_stop_error_500_raises_runtime_error():
    session = _build_session(default_post=(500, {}, b"controller fault"))
    drv = RWSDriver(host="x", session=session)
    with pytest.raises(RuntimeError) as excinfo:
        drv.stop()
    assert "500" in str(excinfo.value)
    assert "controller fault" in str(excinfo.value)


def test_get_state_401_raises_permission_error():
    session = _build_session(default_get=(401, {}, b"auth required"))
    drv = RWSDriver(host="x", session=session)
    with pytest.raises(PermissionError):
        drv.get_state()


def test_run_program_502_during_upload_raises_runtime_error():
    def _post(path, data=None, files=None, **kwargs):
        if "fileservice" in path:
            return (502, {}, b"upstream timeout")
        return (204, {}, b"")

    session = MagicMock()
    session.get.return_value = _ok(_exec_state_payload(running=False))
    session.post.side_effect = _post
    drv = RWSDriver(host="x", session=session)

    with pytest.raises(RuntimeError) as excinfo:
        drv.run_program("MODULE main\nENDMODULE\n", name="oneshot", wait=False)
    assert "502" in str(excinfo.value)


# ---------------------------------------------------------------------------
# rws_version flag selects different paths
# ---------------------------------------------------------------------------


def test_rws_version_1_uses_alt_pp_to_main_path():
    session = _build_session(
        get_map={"/rw/rapid/execution": _ok(_exec_state_payload(running=False))},
    )
    drv = RWSDriver(host="x", session=session, rws_version="1.0")
    drv.run_program("MODULE main\nENDMODULE\n", name="x", wait=False)
    posted_paths = [c.args[0] for c in session.post.call_args_list]
    # IRC5 PP-to-main lives under /rw/rapid/tasks/T_ROB1?action=resetpp.
    assert any(
        "/rw/rapid/tasks/T_ROB1?action=resetpp" in p for p in posted_paths
    )
