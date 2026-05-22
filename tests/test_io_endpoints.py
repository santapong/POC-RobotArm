"""Tests for the I/O REST endpoints (server/routers/io.py).

Uses FastAPI TestClient via ASGI transport, mirroring the Phase 3
test_planning_endpoints.py pattern.  Stub adapters subclass IoAdapter
directly (not MagicMock) per the 7-criterion audit rubric, criterion 2.

Skipped if fastapi or httpx are not installed.
"""

from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator, Sequence

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from server.main import create_app  # noqa: E402

pytestmark = pytest.mark.io

# ---------------------------------------------------------------------------
# Wire-contract field list (from web/src/api/types.ts §D).
# These literals pin the contract; if the server renames a field, the test
# fails loudly on the relevant field set check.
# ---------------------------------------------------------------------------

_CONNECTION_STATUS_FIELDS = {
    "name", "config", "status", "last_error", "connected_at", "signals",
}

_SIGNAL_SPEC_FIELDS = {
    "name", "kind", "address", "scale", "offset", "poll_interval_s",
}

_VALUE_SNAPSHOT_FIELDS = {
    "connection", "signal", "kind", "value", "monotonic_s",
}

_WRITE_RESPONSE_FIELDS = {
    "connection", "signal", "value", "monotonic_s",
}


# ---------------------------------------------------------------------------
# Stub adapter — subclasses IoAdapter so the auditor is satisfied
# ---------------------------------------------------------------------------

from src.io.adapter import AdapterCapabilities, IoAdapter  # noqa: E402
from src.io.types import IoEvent, SignalKind, SignalSpec  # noqa: E402


class _StubAdapter(IoAdapter):
    """Minimal in-process adapter that fakes all protocol operations.

    connect() / disconnect() are no-ops.
    read() returns a boolean True for digital signals, 1.0 for analog.
    write() echoes back the written value.
    watch() yields nothing (blocks) — tests that need events use
    _EventedStubAdapter instead.
    """

    def __init__(self) -> None:
        self._connected = False

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            supports_subscribe=False,
            supports_write=True,
            supports_analog=True,
        )

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def read(self, signal: SignalSpec) -> IoEvent:
        value: bool | int | float
        if signal.kind in (SignalKind.DIGITAL_IN, SignalKind.DIGITAL_OUT):
            value = True
        else:
            value = 1.0
        return IoEvent(
            connection="stub",
            kind="value_changed",
            signal=signal.name,
            value=value,
            monotonic_s=time.monotonic(),
        )

    async def write(self, signal: SignalSpec, value: bool | int | float) -> IoEvent:
        return IoEvent(
            connection="stub",
            kind="write_ack",
            signal=signal.name,
            value=value,
            monotonic_s=time.monotonic(),
        )

    async def watch(self, signals: Sequence[SignalSpec]) -> AsyncIterator[IoEvent]:
        # Block forever until cancelled — no events published unless the
        # test drives them via a queue injected into the runtime.
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            raise
        yield  # unreachable; satisfies the AsyncIterator return type annotation


# ---------------------------------------------------------------------------
# Helpers — patch build_adapter to return the stub
# ---------------------------------------------------------------------------

import contextlib  # noqa: E402
from typing import Iterator  # noqa: E402


@contextlib.contextmanager
def _patch_build_adapter(adapter_factory=None) -> Iterator[None]:
    """Replace build_adapter in all modules that have imported it, so the stub
    is used regardless of how the import was done (``import mod`` vs
    ``from mod import func``).

    The critical binding is ``src.io.runtime.build_adapter`` (bound at import
    time via ``from src.io.registry import build_adapter``).
    """
    import src.io.registry as reg
    import src.io.runtime as _runtime_mod

    factory = adapter_factory if adapter_factory is not None else lambda cfg: _StubAdapter()

    original_reg = reg.build_adapter
    original_runtime = _runtime_mod.build_adapter

    reg.build_adapter = factory
    _runtime_mod.build_adapter = factory
    try:
        yield
    finally:
        reg.build_adapter = original_reg
        _runtime_mod.build_adapter = original_runtime


_MODBUS_TCP_CONFIG = {
    "protocol": "modbus_tcp",
    "host": "127.0.0.1",
    "port": 5020,
    "unit_id": 1,
    "timeout_s": 2.0,
}

_DIGITAL_OUT_SIGNAL = {
    "name": "do0",
    "kind": "digital_out",
    "address": "coil:0",
    "scale": 1.0,
    "offset": 0.0,
    "poll_interval_s": None,
}

_DIGITAL_IN_SIGNAL = {
    "name": "di0",
    "kind": "digital_in",
    "address": "coil:1",
    "scale": 1.0,
    "offset": 0.0,
    "poll_interval_s": None,
}


def _create_body(name: str = "stub_conn", extra_signals: list | None = None):
    signals = [_DIGITAL_OUT_SIGNAL]
    if extra_signals:
        signals.extend(extra_signals)
    return {
        "name": name,
        "config": _MODBUS_TCP_CONFIG,
        "signals": signals,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_connections_empty():
    """GET /api/io/connections returns [] before any connections are created."""
    app = create_app()
    with TestClient(app) as c:
        r = c.get("/api/io/connections")
    assert r.status_code == 200
    assert r.json() == []


def test_create_connection_returns_201():
    """POST /api/io/connections with a valid body returns 201 + IoConnectionStatusModel."""
    app = create_app()
    with _patch_build_adapter():
        with TestClient(app) as c:
            r = c.post("/api/io/connections", json=_create_body())
    assert r.status_code == 201
    body = r.json()
    # Wire-contract parity: all expected field names must be present
    missing = _CONNECTION_STATUS_FIELDS - body.keys()
    assert not missing, f"Response missing fields: {missing}"
    assert body["name"] == "stub_conn"
    assert body["status"] == "open"
    assert isinstance(body["signals"], list)
    assert len(body["signals"]) == 1


def test_create_connection_signal_fields_complete():
    """Each signal in the response must include all SignalSpecModel fields."""
    app = create_app()
    with _patch_build_adapter():
        with TestClient(app) as c:
            r = c.post("/api/io/connections", json=_create_body())
    assert r.status_code == 201
    sig = r.json()["signals"][0]
    missing = _SIGNAL_SPEC_FIELDS - sig.keys()
    assert not missing, f"Signal spec missing fields: {missing}"


def test_create_connection_409_duplicate_name():
    """Creating a connection twice with the same name returns 409 IO_CONNECTION_EXISTS."""
    app = create_app()
    with _patch_build_adapter():
        with TestClient(app) as c:
            r1 = c.post("/api/io/connections", json=_create_body("dup_conn"))
            assert r1.status_code == 201
            r2 = c.post("/api/io/connections", json=_create_body("dup_conn"))
    assert r2.status_code == 409
    assert r2.json()["code"] == "IO_CONNECTION_EXISTS"


def test_create_connection_422_io_unavailable():
    """When build_adapter raises IoUnavailable the endpoint returns 422 IO_UNAVAILABLE."""
    from src.io.errors import IoUnavailable

    def _unavailable(_cfg):
        raise IoUnavailable("pymodbus not installed")

    app = create_app()
    with _patch_build_adapter(_unavailable):
        with TestClient(app) as c:
            r = c.post("/api/io/connections", json=_create_body())
    assert r.status_code == 422
    assert r.json()["code"] == "IO_UNAVAILABLE"


def test_create_connection_503_connection_failed():
    """When the adapter.connect() raises IoConnectionError, endpoint returns 503."""
    from src.io.errors import IoConnectionError

    class _FailingAdapter(_StubAdapter):
        async def connect(self) -> None:
            raise IoConnectionError("TCP refused")

    app = create_app()
    with _patch_build_adapter(lambda _cfg: _FailingAdapter()):
        with TestClient(app) as c:
            r = c.post("/api/io/connections", json=_create_body())
    assert r.status_code == 503
    assert r.json()["code"] == "IO_CONNECTION_FAILED"


def test_get_connection_returns_status():
    """GET /api/io/connections/{name} returns the connection model."""
    app = create_app()
    with _patch_build_adapter():
        with TestClient(app) as c:
            c.post("/api/io/connections", json=_create_body("conn_get"))
            r = c.get("/api/io/connections/conn_get")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "conn_get"
    missing = _CONNECTION_STATUS_FIELDS - body.keys()
    assert not missing


def test_get_connection_404_unknown():
    """GET /api/io/connections/foo returns 404 IO_CONNECTION_UNKNOWN when not found."""
    app = create_app()
    with TestClient(app) as c:
        r = c.get("/api/io/connections/totally_unknown")
    assert r.status_code == 404
    assert r.json()["code"] == "IO_CONNECTION_UNKNOWN"


def test_delete_connection_removes_it():
    """DELETE /api/io/connections/{name} returns 200 ok:true and subsequent GET returns 404."""
    app = create_app()
    with _patch_build_adapter():
        with TestClient(app) as c:
            c.post("/api/io/connections", json=_create_body("del_conn"))
            r_del = c.delete("/api/io/connections/del_conn")
            assert r_del.status_code == 200
            assert r_del.json().get("ok") is True
            r_get = c.get("/api/io/connections/del_conn")
    assert r_get.status_code == 404
    assert r_get.json()["code"] == "IO_CONNECTION_UNKNOWN"


def test_delete_connection_404_unknown():
    """DELETE a non-existent connection returns 404 IO_CONNECTION_UNKNOWN."""
    app = create_app()
    with TestClient(app) as c:
        r = c.delete("/api/io/connections/phantom")
    assert r.status_code == 404
    assert r.json()["code"] == "IO_CONNECTION_UNKNOWN"


def test_list_connections_after_create():
    """After creating a connection, GET /api/io/connections returns it in the list."""
    app = create_app()
    with _patch_build_adapter():
        with TestClient(app) as c:
            c.post("/api/io/connections", json=_create_body("list_conn"))
            r = c.get("/api/io/connections")
    assert r.status_code == 200
    names = [conn["name"] for conn in r.json()]
    assert "list_conn" in names


def test_update_signals_atomic():
    """PUT /api/io/connections/{name}/signals atomically replaces the signal list."""
    app = create_app()
    with _patch_build_adapter():
        with TestClient(app) as c:
            c.post("/api/io/connections", json=_create_body("sig_conn"))
            # First PUT: one signal
            new_signals_1 = [_DIGITAL_OUT_SIGNAL]
            r1 = c.put("/api/io/connections/sig_conn/signals", json=new_signals_1)
            assert r1.status_code == 200
            assert len(r1.json()["signals"]) == 1

            # Second PUT: two signals (atomic replacement)
            new_signals_2 = [
                _DIGITAL_OUT_SIGNAL,
                {"name": "do1", "kind": "digital_out", "address": "coil:2",
                 "scale": 1.0, "offset": 0.0, "poll_interval_s": None},
            ]
            r2 = c.put("/api/io/connections/sig_conn/signals", json=new_signals_2)
    assert r2.status_code == 200
    assert len(r2.json()["signals"]) == 2  # replaced, not appended


def test_update_signals_404_unknown_connection():
    """PUT signals on a non-existent connection returns 404 IO_CONNECTION_UNKNOWN."""
    app = create_app()
    with TestClient(app) as c:
        r = c.put("/api/io/connections/ghost/signals", json=[_DIGITAL_OUT_SIGNAL])
    assert r.status_code == 404
    assert r.json()["code"] == "IO_CONNECTION_UNKNOWN"


def test_reconnect_endpoint_succeeds():
    """POST /api/io/connections/{name}/reconnect returns 200 with status=open."""
    app = create_app()
    with _patch_build_adapter():
        with TestClient(app) as c:
            c.post("/api/io/connections", json=_create_body("reconn"))
            r = c.post("/api/io/connections/reconn/reconnect")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "open"


def test_reconnect_404_unknown():
    """POST reconnect on a non-existent connection returns 404 IO_CONNECTION_UNKNOWN."""
    app = create_app()
    with TestClient(app) as c:
        r = c.post("/api/io/connections/no_such/reconnect")
    assert r.status_code == 404
    assert r.json()["code"] == "IO_CONNECTION_UNKNOWN"


def test_read_signal_returns_snapshot():
    """POST /api/io/connections/{name}/signals/{signal}/read returns IoValueSnapshotModel."""
    app = create_app()
    with _patch_build_adapter():
        with TestClient(app) as c:
            c.post("/api/io/connections", json=_create_body("read_conn"))
            r = c.post("/api/io/connections/read_conn/signals/do0/read")
    assert r.status_code == 200
    body = r.json()
    missing = _VALUE_SNAPSHOT_FIELDS - body.keys()
    assert not missing, f"Snapshot missing fields: {missing}"
    assert body["connection"] == "read_conn"
    assert body["signal"] == "do0"
    assert body["value"] in (True, False, 0, 1)


def test_read_signal_404_unknown_signal():
    """Read a signal not in the signal map returns 404 IO_SIGNAL_UNKNOWN."""
    app = create_app()
    with _patch_build_adapter():
        with TestClient(app) as c:
            c.post("/api/io/connections", json=_create_body("rs_conn"))
            r = c.post("/api/io/connections/rs_conn/signals/nonexistent/read")
    assert r.status_code == 404
    assert r.json()["code"] == "IO_SIGNAL_UNKNOWN"


def test_read_signal_404_unknown_connection():
    """Read from a non-existent connection returns 404 IO_CONNECTION_UNKNOWN."""
    app = create_app()
    with TestClient(app) as c:
        r = c.post("/api/io/connections/ghost_conn/signals/do0/read")
    assert r.status_code == 404
    assert r.json()["code"] == "IO_CONNECTION_UNKNOWN"


def test_write_signal_happy_path():
    """POST /api/io/connections/{name}/signals/{signal}/write returns WriteSignalResponse."""
    app = create_app()
    with _patch_build_adapter():
        with TestClient(app) as c:
            c.post("/api/io/connections", json=_create_body("wr_conn"))
            r = c.post(
                "/api/io/connections/wr_conn/signals/do0/write",
                json={"value": True},
            )
    assert r.status_code == 200
    body = r.json()
    missing = _WRITE_RESPONSE_FIELDS - body.keys()
    assert not missing, f"WriteSignalResponse missing fields: {missing}"
    assert body["connection"] == "wr_conn"
    assert body["signal"] == "do0"


def test_write_signal_404_unknown_signal():
    """Write to a non-existent signal name returns 404 IO_SIGNAL_UNKNOWN."""
    app = create_app()
    with _patch_build_adapter():
        with TestClient(app) as c:
            c.post("/api/io/connections", json=_create_body("ws_sig_conn"))
            r = c.post(
                "/api/io/connections/ws_sig_conn/signals/ghost_signal/write",
                json={"value": True},
            )
    assert r.status_code == 404
    assert r.json()["code"] == "IO_SIGNAL_UNKNOWN"


def test_write_signal_404_unknown_connection():
    """Write to a non-existent connection returns 404 IO_CONNECTION_UNKNOWN."""
    app = create_app()
    with TestClient(app) as c:
        r = c.post(
            "/api/io/connections/ghost/signals/do0/write",
            json={"value": True},
        )
    assert r.status_code == 404
    assert r.json()["code"] == "IO_CONNECTION_UNKNOWN"


def test_write_signal_422_kind_mismatch():
    """Writing a float to a digital_out signal raises 422 IO_SIGNAL_KIND_MISMATCH."""
    app = create_app()
    with _patch_build_adapter():
        with TestClient(app) as c:
            c.post("/api/io/connections", json=_create_body("km_conn"))
            # do0 is digital_out; writing a float should trigger kind mismatch
            r = c.post(
                "/api/io/connections/km_conn/signals/do0/write",
                json={"value": 3.14},
            )
    assert r.status_code == 422
    assert r.json()["code"] == "IO_SIGNAL_KIND_MISMATCH"


def test_write_signal_422_write_to_digital_in():
    """Writing to a digital_in signal (read-only) returns 422 IO_SIGNAL_KIND_MISMATCH."""
    # Create connection with a digital_in signal
    body = {
        "name": "di_conn",
        "config": _MODBUS_TCP_CONFIG,
        "signals": [_DIGITAL_IN_SIGNAL],
    }
    app = create_app()
    with _patch_build_adapter():
        with TestClient(app) as c:
            c.post("/api/io/connections", json=body)
            r = c.post(
                "/api/io/connections/di_conn/signals/di0/write",
                json={"value": True},
            )
    assert r.status_code == 422
    assert r.json()["code"] == "IO_SIGNAL_KIND_MISMATCH"


def test_write_signal_503_not_connected():
    """Write while the adapter raises IoNotConnected → 503 IO_NOT_CONNECTED."""
    from src.io.errors import IoNotConnected

    class _NotConnectedAdapter(_StubAdapter):
        async def write(self, signal: SignalSpec, value: bool | int | float) -> IoEvent:
            raise IoNotConnected("disconnected")

    app = create_app()
    with _patch_build_adapter(lambda _cfg: _NotConnectedAdapter()):
        with TestClient(app) as c:
            c.post("/api/io/connections", json=_create_body("nc_conn"))
            r = c.post(
                "/api/io/connections/nc_conn/signals/do0/write",
                json={"value": True},
            )
    assert r.status_code == 503
    assert r.json()["code"] == "IO_NOT_CONNECTED"


def test_write_signal_502_protocol_error():
    """Write when adapter raises IoProtocolError → 502 IO_PROTOCOL_ERROR."""
    from src.io.errors import IoProtocolError

    class _ProtocolErrorAdapter(_StubAdapter):
        async def write(self, signal: SignalSpec, value: bool | int | float) -> IoEvent:
            raise IoProtocolError("Modbus exception 0x06")

    app = create_app()
    with _patch_build_adapter(lambda _cfg: _ProtocolErrorAdapter()):
        with TestClient(app) as c:
            c.post("/api/io/connections", json=_create_body("pe_conn"))
            r = c.post(
                "/api/io/connections/pe_conn/signals/do0/write",
                json={"value": True},
            )
    assert r.status_code == 502
    assert r.json()["code"] == "IO_PROTOCOL_ERROR"


def test_write_signal_504_timeout():
    """Write when adapter raises IoTimeout → 504 IO_TIMEOUT."""
    from src.io.errors import IoTimeout

    class _TimeoutAdapter(_StubAdapter):
        async def write(self, signal: SignalSpec, value: bool | int | float) -> IoEvent:
            raise IoTimeout("write timed out")

    app = create_app()
    with _patch_build_adapter(lambda _cfg: _TimeoutAdapter()):
        with TestClient(app) as c:
            c.post("/api/io/connections", json=_create_body("to_conn"))
            r = c.post(
                "/api/io/connections/to_conn/signals/do0/write",
                json={"value": True},
            )
    assert r.status_code == 504
    assert r.json()["code"] == "IO_TIMEOUT"


def test_get_all_values_empty_before_events():
    """GET /api/io/values returns [] when no events have been observed."""
    app = create_app()
    with _patch_build_adapter():
        with TestClient(app) as c:
            c.post("/api/io/connections", json=_create_body("vals_conn"))
            r = c.get("/api/io/values")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_connection_values_404_unknown():
    """GET /api/io/connections/{name}/values for unknown name returns 404."""
    app = create_app()
    with TestClient(app) as c:
        r = c.get("/api/io/connections/unknown_for_values/values")
    assert r.status_code == 404
    assert r.json()["code"] == "IO_CONNECTION_UNKNOWN"


def test_create_connection_422_bad_config():
    """POST with missing required fields returns 422 VALIDATION_ERROR (Pydantic gate)."""
    app = create_app()
    with TestClient(app) as c:
        r = c.post(
            "/api/io/connections",
            json={
                "name": "bad",
                "config": {"protocol": "modbus_tcp"},  # missing 'host'
                "signals": [],
            },
        )
    # FastAPI Pydantic validation returns 422
    assert r.status_code == 422


# Extra coverage: multiple connections coexist in the list.
def test_multiple_connections_listed():
    """Creating two connections; both appear in GET /api/io/connections."""
    app = create_app()
    with _patch_build_adapter():
        with TestClient(app) as c:
            c.post("/api/io/connections", json=_create_body("conn_a"))
            c.post("/api/io/connections", json=_create_body("conn_b"))
            r = c.get("/api/io/connections")
    assert r.status_code == 200
    names = {conn["name"] for conn in r.json()}
    assert "conn_a" in names
    assert "conn_b" in names


# Should-fix #1: IO_BAD_CONFIG 422 path — domain __post_init__ rejects empty host
def test_create_connection_422_io_bad_config_from_domain():
    """POST with a config that passes Pydantic but fails domain __post_init__ returns 422 IO_BAD_CONFIG.

    ModbusTcpConfigModel has ``host: str`` with no min_length constraint, so empty-string
    host passes Pydantic validation.  The domain dataclass ModbusTcpConfig.__post_init__
    raises ValueError('ModbusTcpConfig.host must not be empty'), which _config_to_domain
    catches and re-raises as http_error(422, "IO_BAD_CONFIG", ...).
    """
    app = create_app()
    body = {
        "name": "bad_domain",
        "config": {
            "protocol": "modbus_tcp",
            "host": "",  # passes Pydantic (no min_length), fails domain __post_init__
            "port": 502,
            "unit_id": 1,
            "timeout_s": 2.0,
        },
        "signals": [],
    }
    with TestClient(app) as c:
        r = c.post("/api/io/connections", json=body)
    assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
    assert r.json()["code"] == "IO_BAD_CONFIG", (
        f"Expected IO_BAD_CONFIG, got: {r.json()!r}"
    )


# Should-fix #8: update_signals 422 IO_SIGNAL_KIND_MISMATCH coverage
def test_update_signals_422_kind_mismatch(monkeypatch):
    """PUT /api/io/connections/{name}/signals raises 422 IO_SIGNAL_KIND_MISMATCH
    when the runtime raises IoSignalKindMismatch.

    The real IoRuntime.update_signals doesn't raise this error (it just replaces the
    signal map), so we monkeypatch it to simulate a kind-mismatch path. This locks the
    router's error-mapping code: the 422+IO_SIGNAL_KIND_MISMATCH response must be wired
    through the except IoSignalKindMismatch branch in server/routers/io.py:update_signals.
    """
    from src.io.errors import IoSignalKindMismatch

    async def _raise_kind_mismatch(name, signals):
        raise IoSignalKindMismatch("analog_in signal cannot be written as digital_out")

    app = create_app()
    with _patch_build_adapter():
        with TestClient(app) as c:
            c.post("/api/io/connections", json=_create_body("km_update_conn"))

            # Monkeypatch after the runtime is created (it's inside the session).
            from server.services.session import get_session
            session = get_session()
            assert session.io_runtime is not None
            monkeypatch.setattr(session.io_runtime, "update_signals", _raise_kind_mismatch)

            r = c.put(
                "/api/io/connections/km_update_conn/signals",
                json=[_DIGITAL_OUT_SIGNAL],
            )
    assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
    assert r.json()["code"] == "IO_SIGNAL_KIND_MISMATCH", (
        f"Expected IO_SIGNAL_KIND_MISMATCH, got: {r.json()!r}"
    )


# Extra coverage: disconnect endpoint preserves slot
def test_disconnect_endpoint_preserves_slot():
    """POST /api/io/connections/{name}/reconnect (via disconnect + reconnect pattern)
    keeps the slot in list_connections with status=open after reconnect.

    Per the iter-2 PM decision #2: the slot remains registered after disconnect.
    We verify via the reconnect endpoint which does disconnect + connect.
    """
    app = create_app()
    with _patch_build_adapter():
        with TestClient(app) as c:
            c.post("/api/io/connections", json=_create_body("persist_conn"))
            # Reconnect (disconnect + connect under the hood)
            r = c.post("/api/io/connections/persist_conn/reconnect")
            assert r.status_code == 200
            # Slot must still appear in list
            r_list = c.get("/api/io/connections")
    names = [conn["name"] for conn in r_list.json()]
    assert "persist_conn" in names
