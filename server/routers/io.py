"""I/O REST router.

Endpoints
---------
- ``POST   /api/io/connections``                                  — add a connection.
- ``GET    /api/io/connections``                                  — list connections.
- ``GET    /api/io/connections/{name}``                           — get one connection.
- ``DELETE /api/io/connections/{name}``                           — remove a connection.
- ``POST   /api/io/connections/{name}/reconnect``                 — reconnect.
- ``PUT    /api/io/connections/{name}/signals``                   — replace signal map.
- ``GET    /api/io/values``                                       — all cached values.
- ``GET    /api/io/connections/{name}/values``                    — per-connection values.
- ``POST   /api/io/connections/{name}/signals/{signal}/read``     — live read.
- ``POST   /api/io/connections/{name}/signals/{signal}/write``    — write a value.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from server.models.io import (
    ConnectionConfigModel,
    ConnectionStatusKindModel,
    IoConnectionCreateRequest,
    IoConnectionStatusModel,
    IoValueSnapshotModel,
    ModbusRtuConfigModel,
    ModbusTcpConfigModel,
    MqttConfigModel,
    OpcUaConfigModel,
    SignalKindModel,
    SignalSpecModel,
    WriteSignalRequest,
    WriteSignalResponse,
)
from server.services.errors import http_error
from server.services.io import get_or_create_io_runtime
from server.services.session import Session, get_session

router = APIRouter(prefix="/api/io")


# ---------------------------------------------------------------------------
# Domain ↔ wire-model helpers
# ---------------------------------------------------------------------------


def _config_to_domain(config: Any) -> Any:
    """Convert a Pydantic ``ConnectionConfigModel`` to a domain dataclass.

    Raises
    ------
    HTTPException (422)
        If the domain dataclass ``__post_init__`` rejects the values.
    """
    from src.io.types import ModbusRtuConfig, ModbusTcpConfig, MqttConfig, OpcUaConfig

    try:
        if isinstance(config, ModbusTcpConfigModel):
            return ModbusTcpConfig(
                host=config.host,
                port=config.port,
                unit_id=config.unit_id,
                timeout_s=config.timeout_s,
            )
        if isinstance(config, ModbusRtuConfigModel):
            return ModbusRtuConfig(
                device=config.device,
                baudrate=config.baudrate,
                parity=config.parity,
                stopbits=config.stopbits,
                bytesize=config.bytesize,
                unit_id=config.unit_id,
                timeout_s=config.timeout_s,
            )
        if isinstance(config, OpcUaConfigModel):
            return OpcUaConfig(
                url=config.url,
                namespace=config.namespace,
                username=config.username,
                password=config.password,
            )
        if isinstance(config, MqttConfigModel):
            return MqttConfig(
                host=config.host,
                port=config.port,
                client_id=config.client_id,
                username=config.username,
                password=config.password,
                keepalive_s=config.keepalive_s,
                qos=config.qos,
            )
    except ValueError as exc:
        raise http_error(422, "IO_BAD_CONFIG", str(exc)) from exc
    raise http_error(422, "IO_BAD_CONFIG", f"Unknown protocol in config: {type(config).__name__}")


def _signal_spec_to_domain(spec: SignalSpecModel) -> Any:
    """Convert a Pydantic ``SignalSpecModel`` to a ``SignalSpec`` domain dataclass."""
    from src.io.types import SignalKind, SignalSpec

    try:
        return SignalSpec(
            name=spec.name,
            kind=SignalKind(spec.kind.value),
            address=spec.address,
            scale=spec.scale,
            offset=spec.offset,
            poll_interval_s=spec.poll_interval_s,
        )
    except ValueError as exc:
        raise http_error(422, "IO_BAD_CONFIG", str(exc)) from exc


def _slot_to_status(slot: Any) -> IoConnectionStatusModel:
    """Convert a ``_ConnectionSlot`` to an ``IoConnectionStatusModel``."""
    from src.io.types import (
        ModbusRtuConfig,
        ModbusTcpConfig,
        MqttConfig,
        OpcUaConfig,
    )

    cfg = slot.config
    if isinstance(cfg, ModbusTcpConfig):
        config_model: ConnectionConfigModel = ModbusTcpConfigModel(
            protocol="modbus_tcp",
            host=cfg.host,
            port=cfg.port,
            unit_id=cfg.unit_id,
            timeout_s=cfg.timeout_s,
        )
    elif isinstance(cfg, ModbusRtuConfig):
        config_model = ModbusRtuConfigModel(
            protocol="modbus_rtu",
            device=cfg.device,
            baudrate=cfg.baudrate,
            parity=cfg.parity,
            stopbits=cfg.stopbits,
            bytesize=cfg.bytesize,
            unit_id=cfg.unit_id,
            timeout_s=cfg.timeout_s,
        )
    elif isinstance(cfg, OpcUaConfig):
        config_model = OpcUaConfigModel(
            protocol="opcua",
            url=cfg.url,
            namespace=cfg.namespace,
            username=cfg.username,
            password=cfg.password,
        )
    elif isinstance(cfg, MqttConfig):
        config_model = MqttConfigModel(
            protocol="mqtt",
            host=cfg.host,
            port=cfg.port,
            client_id=cfg.client_id,
            username=cfg.username,
            password=cfg.password,
            keepalive_s=cfg.keepalive_s,
            qos=cfg.qos,
        )
    else:
        raise http_error(500, "INTERNAL_ERROR", f"Unknown config type: {type(cfg).__name__}")

    signals = [
        SignalSpecModel(
            name=sig.name,
            kind=SignalKindModel(sig.kind.value),
            address=sig.address,
            scale=sig.scale,
            offset=sig.offset,
            poll_interval_s=sig.poll_interval_s,
        )
        for sig in slot.signals.values()
    ]

    return IoConnectionStatusModel(
        name=slot.name,
        config=config_model,
        status=ConnectionStatusKindModel(slot.status.value),
        last_error=slot.last_error,
        connected_at=slot.connected_at,
        signals=signals,
    )


def _event_to_snapshot(event: Any, kind: Any) -> IoValueSnapshotModel:
    """Build an ``IoValueSnapshotModel`` from an ``IoEvent`` + signal kind."""
    from src.io.types import SignalKind

    return IoValueSnapshotModel(
        connection=event.connection,
        signal=event.signal or "",
        kind=SignalKindModel(kind.value if isinstance(kind, SignalKind) else kind),
        value=event.value if event.value is not None else 0,
        monotonic_s=event.monotonic_s,
    )


def _cached_event_to_snapshot(event: Any, slot: Any) -> IoValueSnapshotModel:
    """Build a snapshot from a cached ``IoEvent``, looking up the signal kind."""
    signal_name = event.signal or ""
    sig = slot.signals.get(signal_name) if slot else None
    kind = sig.kind if sig is not None else None
    return IoValueSnapshotModel(
        connection=event.connection,
        signal=signal_name,
        kind=SignalKindModel(kind.value if kind is not None else "digital_in"),
        value=event.value if event.value is not None else 0,
        monotonic_s=event.monotonic_s,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/connections", response_model=IoConnectionStatusModel, status_code=201)
async def create_connection(
    body: IoConnectionCreateRequest,
    session: Session = Depends(get_session),
) -> IoConnectionStatusModel:
    """Add and connect a new I/O connection.

    Raises ``409 IO_CONNECTION_EXISTS`` if the name is already registered,
    ``422 IO_UNAVAILABLE`` if the ``[io]`` extra is not installed,
    ``503 IO_CONNECTION_FAILED`` if the adapter cannot connect.
    """
    from src.io.errors import IoConnectionError, IoUnavailable

    runtime = get_or_create_io_runtime(session)

    domain_config = _config_to_domain(body.config)
    domain_signals = [_signal_spec_to_domain(s) for s in body.signals]

    try:
        slot = await runtime.add_connection(body.name, domain_config, domain_signals)
    except ValueError as exc:
        # add_connection raises ValueError when the name already exists.
        raise http_error(409, "IO_CONNECTION_EXISTS", str(exc)) from exc
    except IoUnavailable as exc:
        raise http_error(
            422,
            "IO_UNAVAILABLE",
            str(exc),
            hint="Install the [io] extra: pip install 'poc-robotarm[io]'",
        ) from exc
    except IoConnectionError as exc:
        raise http_error(503, "IO_CONNECTION_FAILED", str(exc)) from exc

    return _slot_to_status(slot)


@router.get("/connections", response_model=list[IoConnectionStatusModel])
async def list_connections(
    session: Session = Depends(get_session),
) -> list[IoConnectionStatusModel]:
    """Return all registered connections."""
    if session.io_runtime is None:
        return []
    return [_slot_to_status(s) for s in session.io_runtime.list_connections()]


@router.get("/connections/{name}", response_model=IoConnectionStatusModel)
async def get_connection(
    name: str,
    session: Session = Depends(get_session),
) -> IoConnectionStatusModel:
    """Return one connection by name.

    Raises ``404 IO_CONNECTION_UNKNOWN`` if not found.
    """
    if session.io_runtime is None:
        raise http_error(404, "IO_CONNECTION_UNKNOWN", f"Connection '{name}' not found.")
    try:
        slot = session.io_runtime.get_connection(name)
    except KeyError:
        raise http_error(404, "IO_CONNECTION_UNKNOWN", f"Connection '{name}' not found.")
    return _slot_to_status(slot)


@router.delete("/connections/{name}")
async def remove_connection(
    name: str,
    session: Session = Depends(get_session),
) -> dict:
    """Disconnect and remove a connection.

    Returns ``{"ok": true}``.
    Raises ``404 IO_CONNECTION_UNKNOWN`` if not found.
    """
    if session.io_runtime is None:
        raise http_error(404, "IO_CONNECTION_UNKNOWN", f"Connection '{name}' not found.")
    try:
        await session.io_runtime.remove_connection(name)
    except KeyError:
        raise http_error(404, "IO_CONNECTION_UNKNOWN", f"Connection '{name}' not found.")
    return {"ok": True}


@router.post("/connections/{name}/reconnect", response_model=IoConnectionStatusModel)
async def reconnect_connection(
    name: str,
    session: Session = Depends(get_session),
) -> IoConnectionStatusModel:
    """Disconnect and reconnect with the same config and signal map.

    Raises ``404 IO_CONNECTION_UNKNOWN`` or ``503 IO_CONNECTION_FAILED``.
    """
    from src.io.errors import IoConnectionError

    if session.io_runtime is None:
        raise http_error(404, "IO_CONNECTION_UNKNOWN", f"Connection '{name}' not found.")
    try:
        slot = await session.io_runtime.reconnect(name)
    except KeyError:
        raise http_error(404, "IO_CONNECTION_UNKNOWN", f"Connection '{name}' not found.")
    except IoConnectionError as exc:
        raise http_error(503, "IO_CONNECTION_FAILED", str(exc)) from exc
    return _slot_to_status(slot)


@router.put("/connections/{name}/signals", response_model=IoConnectionStatusModel)
async def update_signals(
    name: str,
    body: list[SignalSpecModel],
    session: Session = Depends(get_session),
) -> IoConnectionStatusModel:
    """Atomically replace the signal map for a connection.

    Raises ``404 IO_CONNECTION_UNKNOWN`` or ``422 IO_SIGNAL_KIND_MISMATCH``.
    """
    from src.io.errors import IoSignalKindMismatch

    if session.io_runtime is None:
        raise http_error(404, "IO_CONNECTION_UNKNOWN", f"Connection '{name}' not found.")

    domain_signals = [_signal_spec_to_domain(s) for s in body]

    try:
        slot = await session.io_runtime.update_signal_map(name, domain_signals)
    except KeyError:
        raise http_error(404, "IO_CONNECTION_UNKNOWN", f"Connection '{name}' not found.")
    except IoSignalKindMismatch as exc:
        raise http_error(422, "IO_SIGNAL_KIND_MISMATCH", str(exc)) from exc
    return _slot_to_status(slot)


@router.get("/values", response_model=list[IoValueSnapshotModel])
async def get_all_values(
    session: Session = Depends(get_session),
) -> list[IoValueSnapshotModel]:
    """Return all cached signal values across all connections."""
    if session.io_runtime is None:
        return []

    runtime = session.io_runtime
    events = runtime.last_values()
    result = []
    for event in events:
        if event.value is None or event.signal is None:
            continue
        try:
            slot = runtime.get_connection(event.connection)
        except KeyError:
            continue
        result.append(_cached_event_to_snapshot(event, slot))
    return result


@router.get("/connections/{name}/values", response_model=list[IoValueSnapshotModel])
async def get_connection_values(
    name: str,
    session: Session = Depends(get_session),
) -> list[IoValueSnapshotModel]:
    """Return all cached signal values for one connection.

    Raises ``404 IO_CONNECTION_UNKNOWN`` if not found.
    """
    if session.io_runtime is None:
        raise http_error(404, "IO_CONNECTION_UNKNOWN", f"Connection '{name}' not found.")

    runtime = session.io_runtime
    try:
        slot = runtime.get_connection(name)
    except KeyError:
        raise http_error(404, "IO_CONNECTION_UNKNOWN", f"Connection '{name}' not found.")

    events = runtime.last_values_for(name)
    result = []
    for event in events:
        if event.value is None or event.signal is None:
            continue
        result.append(_cached_event_to_snapshot(event, slot))
    return result


@router.post(
    "/connections/{name}/signals/{signal}/read",
    response_model=IoValueSnapshotModel,
)
async def read_signal(
    name: str,
    signal: str,
    session: Session = Depends(get_session),
) -> IoValueSnapshotModel:
    """Perform a live read of one signal.

    Raises ``404 IO_CONNECTION_UNKNOWN``, ``404 IO_SIGNAL_UNKNOWN``,
    ``503 IO_NOT_CONNECTED``, ``504 IO_TIMEOUT``.
    """
    from src.io.errors import IoNotConnected, IoTimeout, IoUnknownSignal

    if session.io_runtime is None:
        raise http_error(404, "IO_CONNECTION_UNKNOWN", f"Connection '{name}' not found.")

    runtime = session.io_runtime
    try:
        slot = runtime.get_connection(name)
    except KeyError:
        raise http_error(404, "IO_CONNECTION_UNKNOWN", f"Connection '{name}' not found.")

    # Resolve signal kind before calling the runtime (for the snapshot model).
    sig = slot.signals.get(signal)
    if sig is None:
        raise http_error(404, "IO_SIGNAL_UNKNOWN", f"Signal '{signal}' not in connection '{name}'.")

    try:
        event = await runtime.read(name, signal)
    except KeyError:
        raise http_error(404, "IO_CONNECTION_UNKNOWN", f"Connection '{name}' not found.")
    except IoUnknownSignal:
        raise http_error(404, "IO_SIGNAL_UNKNOWN", f"Signal '{signal}' not in connection '{name}'.")
    except IoNotConnected as exc:
        raise http_error(503, "IO_NOT_CONNECTED", str(exc)) from exc
    except IoTimeout as exc:
        raise http_error(504, "IO_TIMEOUT", str(exc)) from exc

    return _event_to_snapshot(event, sig.kind)


@router.post(
    "/connections/{name}/signals/{signal}/write",
    response_model=WriteSignalResponse,
)
async def write_signal(
    name: str,
    signal: str,
    body: WriteSignalRequest,
    session: Session = Depends(get_session),
) -> WriteSignalResponse:
    """Write a value to one signal.

    Raises ``404 IO_CONNECTION_UNKNOWN``, ``404 IO_SIGNAL_UNKNOWN``,
    ``422 IO_SIGNAL_KIND_MISMATCH``, ``503 IO_NOT_CONNECTED``,
    ``504 IO_TIMEOUT``, ``502 IO_PROTOCOL_ERROR``.
    """
    from src.io.errors import (
        IoNotConnected,
        IoProtocolError,
        IoSignalKindMismatch,
        IoTimeout,
        IoUnknownSignal,
    )

    if session.io_runtime is None:
        raise http_error(404, "IO_CONNECTION_UNKNOWN", f"Connection '{name}' not found.")

    runtime = session.io_runtime
    try:
        slot = runtime.get_connection(name)
    except KeyError:
        raise http_error(404, "IO_CONNECTION_UNKNOWN", f"Connection '{name}' not found.")

    if signal not in slot.signals:
        raise http_error(404, "IO_SIGNAL_UNKNOWN", f"Signal '{signal}' not in connection '{name}'.")

    try:
        event = await runtime.write(name, signal, body.value)
    except KeyError:
        raise http_error(404, "IO_CONNECTION_UNKNOWN", f"Connection '{name}' not found.")
    except IoUnknownSignal:
        raise http_error(404, "IO_SIGNAL_UNKNOWN", f"Signal '{signal}' not in connection '{name}'.")
    except IoSignalKindMismatch as exc:
        raise http_error(422, "IO_SIGNAL_KIND_MISMATCH", str(exc)) from exc
    except IoNotConnected as exc:
        raise http_error(503, "IO_NOT_CONNECTED", str(exc)) from exc
    except IoTimeout as exc:
        raise http_error(504, "IO_TIMEOUT", str(exc)) from exc
    except IoProtocolError as exc:
        raise http_error(502, "IO_PROTOCOL_ERROR", str(exc)) from exc

    return WriteSignalResponse(
        connection=name,
        signal=signal,
        value=event.value if event.value is not None else body.value,
        monotonic_s=event.monotonic_s,
    )


__all__ = ["router"]
