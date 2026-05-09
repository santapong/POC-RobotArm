"""``RWSDriver`` — an online :class:`~src.drivers.Driver` for ABB controllers.

The driver speaks ABB Robot Web Services (RWS) over HTTPS with digest
authentication. It targets both flavours of the protocol:

* RWS 1.0 — IRC5 controllers running RobotWare 5/6.
* RWS 2.0 — OmniCore controllers running RobotWare 7+.

Endpoint paths and minor payload shapes differ between the two; the
``rws_version`` constructor flag picks the right URL prefixes.

Design notes
------------
* The HTTP client is **dependency-injected**: pass a ``session`` with a
  ``requests``-like ``.get/.post`` surface and the driver never touches the
  network. This is how unit tests mock the controller. When ``session`` is
  ``None`` we build a lightweight :class:`_DigestSession` from
  :mod:`urllib.request` so the only runtime requirement is the standard
  library.
* Real-time motion is **not** the goal here: RWS is a programming and
  monitoring channel. Cartesian / joint commands therefore lower into a
  one-shot RAPID program (built via :class:`~src.post.abb_rapid.RAPIDPost`)
  that is uploaded and executed by ``run_program``. EGM (10 ms cyclic
  control) is Phase 6 and lives in a different driver.
* Pose conventions follow the project-wide canon: metres, radians,
  ``(w, x, y, z)`` quaternions. ABB's native units are mm/deg and ABB's
  quaternion order is already wxyz, so the wxyz reordering that the sim
  driver does is a no-op here — only the unit conversions matter.
* All HTTP failures are translated to clean Python exceptions:
  :class:`ConnectionError` for network/connect issues,
  :class:`PermissionError` for 401/403 (auth / mastership denied), and
  :class:`RuntimeError` for any other 4xx/5xx (controller-side error).
  The response body is included in the message so failures are debuggable.
"""

from __future__ import annotations

import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Iterable, Optional, Sequence, Tuple

from src.drivers.base import RobotState
from src.motion.ir import (
    JointTarget,
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
from src.post.abb_rapid import RAPIDPost

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

# Maximum time we'll wait for ``run_program`` execution to finish before
# raising. Long enough for a typical pick-and-place; tests override.
_PROGRAM_WAIT_TIMEOUT_S = 120.0
_PROGRAM_WAIT_POLL_S = 0.25

# Multipart form boundary — we generate a fresh one per upload; tokens are
# random so payloads never collide with body content.
_MULTIPART_BOUNDARY_PREFIX = "----RWSDriverBoundary"


# ---------------------------------------------------------------------------
# URL prefix table — RWS 1.0 vs 2.0
# ---------------------------------------------------------------------------

# OmniCore (RWS 2.0) standardised on /rw/* roots; IRC5 (RWS 1.0) used the
# same prefix for most endpoints but with a slightly different file service
# root and slightly different payload shapes. Where the path differs we
# branch in the helper that builds the URL; otherwise the table is shared.
_PATHS_BY_VERSION = {
    "2.0": {
        "system": "/rw/system?json=1",
        "joints": "/rw/motionsystem/mechunits/ROB_1/jointtarget?json=1",
        "robtarget": "/rw/motionsystem/mechunits/ROB_1/robtarget?json=1",
        "exec_state": "/rw/rapid/execution?json=1",
        "exec_start": "/rw/rapid/execution?action=start",
        "exec_stop": "/rw/rapid/execution?action=stop",
        "fileservice": "/fileservice/$HOME$/{filename}",
        "load_module": "/rw/rapid/tasks/T_ROB1/loadmodule",
        "pp_to_main": "/rw/rapid/execution?action=resetpp",
        "motors_on": "/rw/panel/ctrl-state?action=setctrlstate",
        "mastership_request": "/rw/mastership?action=request",
        "mastership_release": "/rw/mastership?action=release",
        "set_var": "/rw/rapid/symbol/data/RAPID/T_ROB1/{module}/{var}?action=set",
    },
    "1.0": {
        # IRC5 differs mostly in the absence of the ``json=1`` requirement
        # (XML is the default) and a slightly different file service root.
        "system": "/rw/system?json=1",
        "joints": "/rw/motionsystem/mechunits/ROB_1/jointtarget?json=1",
        "robtarget": "/rw/motionsystem/mechunits/ROB_1/robtarget?json=1",
        "exec_state": "/rw/rapid/execution?json=1",
        "exec_start": "/rw/rapid/execution?action=start",
        "exec_stop": "/rw/rapid/execution?action=stop",
        "fileservice": "/fileservice/$HOME$/{filename}",
        "load_module": "/rw/rapid/tasks/T_ROB1/loadmodule",
        "pp_to_main": "/rw/rapid/tasks/T_ROB1?action=resetpp",
        "motors_on": "/rw/panel/ctrlstate?action=setctrlstate",
        "mastership_request": "/rw/mastership?action=request",
        "mastership_release": "/rw/mastership?action=release",
        "set_var": "/rw/rapid/symbol/data/RAPID/T_ROB1/{module}/{var}?action=set",
    },
}


# ---------------------------------------------------------------------------
# Session interface — minimal, requests-compatible-ish
# ---------------------------------------------------------------------------


class _DigestSession:
    """Tiny HTTPS+digest client built on :mod:`urllib.request`.

    This is **not** a full ``requests`` replacement — it implements only
    the two verbs (``get``, ``post``) and the data shapes (form-encoded,
    multipart-file) that :class:`RWSDriver` actually needs. The return
    value is a 3-tuple ``(status, headers, body_bytes)`` so callers can
    inspect status codes without raising on 4xx/5xx — error mapping
    happens at the driver layer.

    Cookies are kept across requests via a :class:`http.cookiejar.CookieJar`
    so the controller's session affinity (``ABBCX``) and CSRF tokens
    survive between calls.
    """

    def __init__(self, base_url: str, username: str, password: str, timeout: float = 10.0) -> None:
        # Late import to avoid pulling cookiejar in test paths that mock the session.
        import http.cookiejar

        self._base_url = base_url.rstrip("/")
        self._username = username
        self._password = password
        self._timeout = timeout

        password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        password_mgr.add_password(None, base_url, username, password)
        digest_handler = urllib.request.HTTPDigestAuthHandler(password_mgr)
        cookie_jar = http.cookiejar.CookieJar()
        cookie_handler = urllib.request.HTTPCookieProcessor(cookie_jar)
        self._opener = urllib.request.build_opener(digest_handler, cookie_handler)
        # ABB's RWS rejects requests without a User-Agent in some firmware
        # builds; set a sane default that callers can override.
        self._opener.addheaders = [("User-Agent", "RWSDriver/1.0")]

    # ----------------------------------------------------------- public API

    def get(self, path: str, **kwargs: Any) -> Tuple[int, dict, bytes]:
        """Issue an HTTP GET; return ``(status, headers, body_bytes)``."""
        return self._request("GET", path, data=None, **kwargs)

    def post(
        self,
        path: str,
        data: Optional[Any] = None,
        files: Optional[dict] = None,
        **kwargs: Any,
    ) -> Tuple[int, dict, bytes]:
        """Issue an HTTP POST; ``data`` is form-encoded, ``files`` is multipart.

        ``data`` may be a ``dict`` (form-encoded), ``bytes`` (sent as-is),
        or ``None``. ``files`` is a ``dict[name, (filename, content_bytes)]``;
        when set, the body is encoded as ``multipart/form-data``.
        """
        if files:
            body, content_type = _encode_multipart(files, data or {})
            kwargs.setdefault("headers", {})
            kwargs["headers"].setdefault("Content-Type", content_type)
            return self._request("POST", path, data=body, **kwargs)
        if isinstance(data, dict):
            body = urllib.parse.urlencode(data).encode("utf-8")
            kwargs.setdefault("headers", {})
            kwargs["headers"].setdefault(
                "Content-Type", "application/x-www-form-urlencoded"
            )
            return self._request("POST", path, data=body, **kwargs)
        return self._request("POST", path, data=data, **kwargs)

    def close(self) -> None:
        """Best-effort cleanup; urllib openers don't need explicit close."""
        # Kept for API symmetry with ``requests.Session``.
        return None

    # --------------------------------------------------------- internal helpers

    def _request(
        self,
        method: str,
        path: str,
        data: Optional[bytes],
        headers: Optional[dict] = None,
        timeout: Optional[float] = None,
    ) -> Tuple[int, dict, bytes]:
        url = self._absolute(path)
        req = urllib.request.Request(url, data=data, method=method)
        for key, val in (headers or {}).items():
            req.add_header(key, val)
        try:
            response = self._opener.open(req, timeout=timeout or self._timeout)
        except urllib.error.HTTPError as exc:
            # 4xx/5xx come back as HTTPError on urllib; re-shape to the
            # common (status, headers, body) tuple so the driver can map.
            return (exc.code, dict(exc.headers or {}), exc.read())
        except urllib.error.URLError as exc:
            raise ConnectionError(f"RWS request to {url!r} failed: {exc.reason}") from exc

        body = response.read()
        return (response.status, dict(response.headers), body)

    def _absolute(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        return f"{self._base_url}{path}"


def _encode_multipart(
    files: dict, fields: dict, boundary: Optional[str] = None
) -> Tuple[bytes, str]:
    """Encode ``files`` and ``fields`` as a ``multipart/form-data`` body.

    ``files`` values are ``(filename, content_bytes)`` tuples. We keep the
    encoder local rather than pulling in ``requests`` so the driver stays
    on the standard library.
    """
    if boundary is None:
        boundary = f"{_MULTIPART_BOUNDARY_PREFIX}{secrets.token_hex(8)}"
    lines: list[bytes] = []
    for name, value in fields.items():
        lines.append(f"--{boundary}".encode("utf-8"))
        lines.append(
            f'Content-Disposition: form-data; name="{name}"'.encode("utf-8")
        )
        lines.append(b"")
        lines.append(str(value).encode("utf-8"))
    for name, (filename, content) in files.items():
        lines.append(f"--{boundary}".encode("utf-8"))
        lines.append(
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"'.encode(
                "utf-8"
            )
        )
        lines.append(b"Content-Type: application/octet-stream")
        lines.append(b"")
        if isinstance(content, str):
            content = content.encode("utf-8")
        lines.append(content)
    lines.append(f"--{boundary}--".encode("utf-8"))
    lines.append(b"")
    body = b"\r\n".join(lines)
    return body, f"multipart/form-data; boundary={boundary}"


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


class RWSDriver:
    """ABB Robot Web Services online driver.

    Conforms to the :class:`~src.drivers.Driver` Protocol; lowers high-level
    motion calls into one-shot RAPID programs that get uploaded, loaded, and
    executed via the standard RWS workflow.
    """

    def __init__(
        self,
        host: str,
        port: int = 443,
        username: str = "Default User",
        password: str = "robotics",
        rws_version: str = "2.0",
        session: Optional[Any] = None,
        dof: int = 6,
    ) -> None:
        if rws_version not in _PATHS_BY_VERSION:
            raise ValueError(
                f"rws_version must be one of {list(_PATHS_BY_VERSION)}, got {rws_version!r}"
            )
        self._host = host
        self._port = int(port)
        self._username = username
        self._password = password
        self._rws_version = rws_version
        self._paths = _PATHS_BY_VERSION[rws_version]
        # Public Driver Protocol attributes.
        self.name = f"abb:{host}@{port}"
        self.dof = int(dof)

        # Connection state and mastership tracking.
        self._connected = False
        self._has_mastership = False
        # Whether *we* built the session; if so, ``disconnect`` closes it.
        # Externally-supplied sessions (DI in tests) are caller-owned.
        self._owns_session = session is None
        self._session = session if session is not None else self._build_default_session()

    # ----------------------------------------------------------- session

    def _build_default_session(self) -> _DigestSession:
        """Build the stdlib-backed digest session pointed at this controller."""
        scheme = "https" if self._port == 443 else "https"  # RWS is HTTPS by spec
        base = f"{scheme}://{self._host}:{self._port}"
        return _DigestSession(base, self._username, self._password)

    # ------------------------------------------------------------- lifecycle

    def connect(self) -> None:
        """Open the controller link by hitting ``/rw/system``.

        The system endpoint is cheap, requires auth, and proves both the
        TCP/TLS connection and the credentials. Any non-2xx status is
        translated to :class:`ConnectionError` (or :class:`PermissionError`
        on 401) with the response body in the message.
        """
        try:
            status, _hdrs, body = self._session.get(self._paths["system"])
        except ConnectionError:
            raise
        except Exception as exc:  # network layer raised something exotic
            raise ConnectionError(
                f"RWS connect to {self.name} failed: {exc!s}"
            ) from exc

        if status == 401 or status == 403:
            raise PermissionError(
                f"RWS auth rejected for {self.name}: HTTP {status} {_decode(body)!r}"
            )
        if not 200 <= status < 300:
            raise ConnectionError(
                f"RWS connect to {self.name} failed: HTTP {status} {_decode(body)!r}"
            )

        self._connected = True

    def disconnect(self) -> None:
        """Tear down the link; release mastership if held. Idempotent."""
        if self._has_mastership:
            try:
                self._release_mastership()
            except Exception:
                # Best-effort during teardown; don't mask the original error
                # path that called disconnect().
                pass
        if self._owns_session and self._session is not None:
            try:
                close = getattr(self._session, "close", None)
                if callable(close):
                    close()
            except Exception:
                pass
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    # ----------------------------------------------------------------- state

    def get_state(self) -> RobotState:
        """Read joints, TCP pose, and execution state from the controller.

        ABB returns joints in degrees and Cartesian coordinates in mm; this
        method converts both to canonical SI (radians, metres). The
        quaternion order ``(q1, q2, q3, q4) = (w, x, y, z)`` matches our
        canonical wxyz so no reorder is needed.
        """
        joints_deg = self._get_jointtarget()
        xyz_mm, quat_wxyz = self._get_robtarget()
        moving = self._is_running()

        joints_rad = tuple(_deg2rad(v) for v in joints_deg)
        xyz_m = tuple(v / 1000.0 for v in xyz_mm)

        return RobotState(
            joints_rad=joints_rad,
            tcp_xyz_m=(xyz_m[0], xyz_m[1], xyz_m[2]),
            tcp_quat_wxyz=(quat_wxyz[0], quat_wxyz[1], quat_wxyz[2], quat_wxyz[3]),
            moving=moving,
            error=None,
        )

    # ---------------------------------------------------------- motion API

    def move_joint(
        self,
        q_rad: Sequence[float],
        speed_frac: float = 0.5,
        blend_m: float = 0.0,
        wait: bool = True,
    ) -> None:
        """Lower a joint-space target into a one-shot ``MoveAbsJ`` program."""
        joints = [float(a) for a in q_rad]
        if len(joints) != self.dof:
            raise ValueError(
                f"move_joint expected {self.dof} joint angles, got {len(joints)}"
            )
        program = self._oneshot_program(
            kind=MoveKind.MOVE_ABS_J,
            joints_rad=joints,
            xyz_m=None,
            quat_wxyz=None,
            speed_frac=speed_frac,
            blend_m=blend_m,
        )
        source = RAPIDPost().emit(program)
        self.run_program(source, name="oneshot", wait=wait)

    def move_linear(
        self,
        xyz_m: Sequence[float],
        quat_wxyz: Sequence[float],
        speed_m_s: float = 0.1,
        blend_m: float = 0.0,
        wait: bool = True,
    ) -> None:
        """Lower a Cartesian target into a one-shot ``MoveL`` program."""
        position = [float(v) for v in xyz_m]
        if len(position) != 3:
            raise ValueError(
                f"move_linear expected 3 xyz components, got {len(position)}"
            )
        quat = tuple(float(v) for v in quat_wxyz)
        # check_quat enforces both length and unit-norm; protects the real
        # controller from receiving a non-unit quaternion that would be
        # silently re-normalized or trigger a Math error mid-motion.
        from src.motion.ir import check_quat
        check_quat(quat, "quat_wxyz")
        # Convert SpeedData speed: speed_m_s -> mm/s for RAPID.
        speed_mm_s = max(speed_m_s * 1000.0, 1.0)
        program = self._oneshot_program(
            kind=MoveKind.MOVE_L,
            joints_rad=None,
            xyz_m=position,
            quat_wxyz=quat,
            speed_frac=None,
            blend_m=blend_m,
            speed_mm_s_override=speed_mm_s,
        )
        source = RAPIDPost().emit(program)
        self.run_program(source, name="oneshot", wait=wait)

    def run_program(
        self,
        source: str,
        name: str = "main",
        wait: bool = True,
        timeout_s: float = _PROGRAM_WAIT_TIMEOUT_S,
    ) -> None:
        """Upload, load, and execute a RAPID module on T_ROB1.

        Sequence (matches ABB documentation for unattended program execution):

        1. ``POST /rw/mastership?action=request`` — exclusive write lock.
        2. ``POST /fileservice/$HOME$/<name>.mod`` — upload module bytes.
        3. ``POST /rw/rapid/tasks/T_ROB1/loadmodule`` — load uploaded file.
        4. ``POST /rw/rapid/execution?action=resetpp`` — PP to ``main``.
        5. ``POST /rw/panel/ctrl-state?action=setctrlstate`` — motors on.
        6. ``POST /rw/rapid/execution?action=start`` — kick off execution.
        7. (optional) Poll ``/rw/rapid/execution`` until ``stopped``.
        8. ``POST /rw/mastership?action=release`` — drop the write lock.
        """
        filename = f"{name}.mod"
        self._request_mastership()
        try:
            self._upload_module(filename, source)
            self._load_module(filename)
            self._reset_pp_to_main()
            self._motors_on()
            self._start_execution()
            if wait:
                self._wait_until_stopped(timeout_s=timeout_s)
        finally:
            # Even if a step above raises, we owe the controller a release
            # so the next session can write. Errors from release itself are
            # swallowed; the original exception (if any) propagates.
            try:
                self._release_mastership()
            except Exception:
                pass

    def stop(self) -> None:
        """Send the abort to the controller via ``execution?action=stop``."""
        status, _hdrs, body = self._session.post(
            self._paths["exec_stop"],
            data={},
        )
        _raise_for_status(status, body, "stop execution")

    # ------------------------------------------------------------ helpers
    # ------ state readers -------------------------------------------------

    def _get_jointtarget(self) -> Tuple[float, ...]:
        """Return the 6 joint angles in degrees from RWS."""
        status, _hdrs, body = self._session.get(self._paths["joints"])
        _raise_for_status(status, body, "read jointtarget")
        payload = _parse_json(body)
        # RWS payload structure: _embedded._state[0] holds rax_1..rax_6.
        joints = _extract_first_state(payload, prefix="rax_")
        return tuple(float(joints[f"rax_{i}"]) for i in range(1, 7))

    def _get_robtarget(self) -> Tuple[Tuple[float, float, float], Tuple[float, float, float, float]]:
        """Return ``(xyz_mm, quat_wxyz)`` from the current robtarget."""
        status, _hdrs, body = self._session.get(self._paths["robtarget"])
        _raise_for_status(status, body, "read robtarget")
        payload = _parse_json(body)
        state = _extract_first_state(payload, prefix="x")
        x = float(state["x"])
        y = float(state["y"])
        z = float(state["z"])
        # ABB returns q1..q4 as (w, x, y, z) — same as our canonical order.
        q1 = float(state["q1"])
        q2 = float(state["q2"])
        q3 = float(state["q3"])
        q4 = float(state["q4"])
        return ((x, y, z), (q1, q2, q3, q4))

    def _is_running(self) -> bool:
        status, _hdrs, body = self._session.get(self._paths["exec_state"])
        _raise_for_status(status, body, "read execution state")
        payload = _parse_json(body)
        state = _extract_first_state(payload, prefix="ctrlexecstate") or _extract_first_state(
            payload, prefix="execstate"
        )
        if not state:
            return False
        # OmniCore reports `ctrlexecstate`; older firmware uses `execstate`.
        # Both map "running" / "stopped" strings to a boolean directly.
        for key in ("ctrlexecstate", "execstate"):
            val = state.get(key)
            if isinstance(val, str):
                return val.strip().lower() == "running"
        return False

    # ------ mastership ----------------------------------------------------

    def _request_mastership(self) -> None:
        status, _hdrs, body = self._session.post(
            self._paths["mastership_request"], data={}
        )
        _raise_for_status(status, body, "request mastership")
        self._has_mastership = True

    def _release_mastership(self) -> None:
        if not self._has_mastership:
            return
        status, _hdrs, body = self._session.post(
            self._paths["mastership_release"], data={}
        )
        _raise_for_status(status, body, "release mastership")
        self._has_mastership = False

    # ------ program lifecycle --------------------------------------------

    def _upload_module(self, filename: str, source: str) -> None:
        path = self._paths["fileservice"].format(filename=filename)
        files = {"file": (filename, source.encode("utf-8"))}
        status, _hdrs, body = self._session.post(path, files=files)
        _raise_for_status(status, body, f"upload {filename}")

    def _load_module(self, filename: str) -> None:
        # The exact form parameter is documented as `modulepath`; some
        # firmware accepts unquoted `$HOME$`, others require the URL-quoted
        # form. We send the literal string and rely on the controller's
        # tolerant parser.
        data = {"modulepath": f"$HOME$/{filename}"}
        status, _hdrs, body = self._session.post(self._paths["load_module"], data=data)
        _raise_for_status(status, body, f"load module {filename}")

    def _reset_pp_to_main(self) -> None:
        status, _hdrs, body = self._session.post(self._paths["pp_to_main"], data={})
        _raise_for_status(status, body, "reset PP to main")

    def _motors_on(self) -> None:
        # The ctrl-state endpoint expects ``ctrl-state=motoron`` (or
        # ``motoroff``) as the form body. Older firmware named the field
        # ``ctrlstate``; we send both spellings for compatibility because
        # extraneous keys are ignored.
        data = {"ctrl-state": "motoron", "ctrlstate": "motoron"}
        status, _hdrs, body = self._session.post(self._paths["motors_on"], data=data)
        _raise_for_status(status, body, "set motors on")

    def _start_execution(self) -> None:
        # Exact body documented at /rw/rapid/execution?action=start.
        data = {
            "regain": "continue",
            "execmode": "continue",
            "cycle": "once",
            "condition": "none",
            "stopatbp": "disabled",
            "alltaskbytsp": "false",
        }
        status, _hdrs, body = self._session.post(self._paths["exec_start"], data=data)
        _raise_for_status(status, body, "start execution")

    def _wait_until_stopped(self, timeout_s: float) -> None:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if not self._is_running():
                return
            time.sleep(_PROGRAM_WAIT_POLL_S)
        raise TimeoutError(
            f"RWS run_program: execution did not stop within {timeout_s:.1f}s"
        )

    # ------ one-shot program builder -------------------------------------

    def _oneshot_program(
        self,
        kind: MoveKind,
        joints_rad: Optional[Iterable[float]],
        xyz_m: Optional[Iterable[float]],
        quat_wxyz: Optional[Iterable[float]],
        speed_frac: Optional[float],
        blend_m: float,
        speed_mm_s_override: Optional[float] = None,
    ) -> Program:
        """Build a single-move :class:`Program` ready for ``RAPIDPost.emit``."""
        tool = ToolData(
            name="tool0",
            mass_kg=1.0,
            tcp_xyz_m=(0.0, 0.0, 0.0),
            tcp_quat_wxyz=(1.0, 0.0, 0.0, 0.0),
        )
        wobj = WObjData(
            name="wobj0",
            base_xyz_m=(0.0, 0.0, 0.0),
            base_quat_wxyz=(1.0, 0.0, 0.0, 0.0),
            user_xyz_m=(0.0, 0.0, 0.0),
            user_quat_wxyz=(1.0, 0.0, 0.0, 0.0),
        )
        if speed_mm_s_override is not None:
            speed = SpeedData(v_tcp_mm_s=speed_mm_s_override)
        else:
            # Map fractional speed onto a sensible mm/s. The RAPID side
            # honours the value verbatim; this is just a default scale.
            frac = speed_frac if speed_frac is not None else 0.5
            speed = SpeedData(v_tcp_mm_s=max(frac * 1000.0, 1.0))
        zone = ZoneData.fine() if blend_m <= 0.0 else ZoneData(ZoneData.RADIUS, blend_m * 1000.0)

        if kind == MoveKind.MOVE_ABS_J:
            assert joints_rad is not None
            target = JointTarget(q_rad=tuple(joints_rad))
        elif kind == MoveKind.MOVE_L:
            assert xyz_m is not None and quat_wxyz is not None
            target = PoseTarget(xyz_m=tuple(xyz_m), quat_wxyz=tuple(quat_wxyz))
        else:  # pragma: no cover - guarded by callers
            raise ValueError(f"Unsupported one-shot MoveKind: {kind}")

        move = Move(kind=kind, target=target, speed=speed, zone=zone, tool=tool, wobj=wobj)
        proc = Procedure(name="main", body=(move,))
        return Program(name="oneshot", tools=(tool,), wobjs=(wobj,), procedures=(proc,))


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _deg2rad(x: float) -> float:
    """Local degree→radian (avoids importing ``math`` everywhere)."""
    return x * 0.017453292519943295  # math.pi / 180


def _decode(body: bytes) -> str:
    """Decode a response body for inclusion in an exception message."""
    if not body:
        return ""
    try:
        return body.decode("utf-8", errors="replace")
    except Exception:
        return repr(body)


def _parse_json(body: bytes) -> Any:
    """Parse a JSON body, returning ``{}`` on empty/invalid payloads."""
    if not body:
        return {}
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}


def _extract_first_state(payload: Any, prefix: str) -> dict:
    """Pull the first ``_state[*]`` dict out of an RWS JSON envelope.

    RWS responses follow a HAL-like shape::

        {"_links": {...},
         "_embedded": {"_state": [{"rax_1": 0.0, "rax_2": 0.0, ...}]}}

    Both RWS 1.0 and 2.0 use this structure. We accept either ``_state`` or
    a top-level ``state`` array for robustness against firmware variations.
    The ``prefix`` argument lets callers pick the right state in cases
    where multiple states are bundled (e.g. some firmware nests
    ``ctrlexecstate`` under a different key).
    """
    if not isinstance(payload, dict):
        return {}
    embedded = payload.get("_embedded") or payload
    state_list = (
        embedded.get("_state")
        or embedded.get("state")
        or payload.get("state")
        or []
    )
    if not isinstance(state_list, list) or not state_list:
        return {}
    # Prefer entries whose keys start with the requested prefix (matches the
    # caller's expectation).
    for entry in state_list:
        if isinstance(entry, dict) and any(k.startswith(prefix) for k in entry.keys()):
            return entry
    # Fall back to the first dict regardless of prefix — better than empty
    # when the firmware uses an unexpected key naming.
    for entry in state_list:
        if isinstance(entry, dict):
            return entry
    return {}


def _raise_for_status(status: int, body: bytes, action: str) -> None:
    """Translate a non-2xx response into the right Python exception."""
    if 200 <= status < 300:
        return
    msg = f"RWS {action}: HTTP {status} {_decode(body)!r}"
    if status in (401, 403):
        raise PermissionError(msg)
    if 500 <= status < 600:
        raise RuntimeError(msg)
    # 4xx other than auth — controller-side rejection of the request.
    raise RuntimeError(msg)


__all__ = ["RWSDriver"]
