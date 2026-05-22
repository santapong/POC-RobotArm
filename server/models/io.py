"""Pydantic v2 wire models for the I/O REST + WebSocket surface.

Field names are snake_case to match the JSON wire format.  These models
mirror ``src/io/types.py`` field-for-field and the TypeScript types in
``web/src/api/types.ts`` exactly (modulo Python vs TypeScript syntax).

Notes
-----
* ``ConnectionConfigModel`` is a discriminated union keyed by ``protocol``.
  Pydantic v2 selects the correct concrete model at parse time so invalid
  discriminator values produce a clear 422 immediately.
* ``model_config = ConfigDict(from_attributes=True)`` lets every model
  accept domain dataclasses directly via ``Model.model_validate(obj)``.
* ``IoEventModel.type`` maps to ``IoEvent.kind`` in the lib (the lib calls
  the field ``kind``; the wire protocol calls it ``type`` to align with the
  web TS contract).
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "SignalKindModel",
    "ConnectionProtocolModel",
    "ConnectionStatusKindModel",
    "ModbusTcpConfigModel",
    "ModbusRtuConfigModel",
    "OpcUaConfigModel",
    "MqttConfigModel",
    "ConnectionConfigModel",
    "SignalSpecModel",
    "IoConnectionStatusModel",
    "IoConnectionCreateRequest",
    "IoValueSnapshotModel",
    "IoEventTypeModel",
    "IoEventModel",
    "WriteSignalRequest",
    "WriteSignalResponse",
]


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SignalKindModel(str, Enum):
    """Direction and type of an I/O signal."""

    DIGITAL_IN = "digital_in"
    DIGITAL_OUT = "digital_out"
    ANALOG_IN = "analog_in"
    ANALOG_OUT = "analog_out"


class ConnectionProtocolModel(str, Enum):
    """Wire protocol for a connection."""

    MODBUS_TCP = "modbus_tcp"
    MODBUS_RTU = "modbus_rtu"
    OPCUA = "opcua"
    MQTT = "mqtt"


class ConnectionStatusKindModel(str, Enum):
    """Lifecycle state of a connection slot."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    OPEN = "open"
    ERROR = "error"
    CLOSING = "closing"


class IoEventTypeModel(str, Enum):
    """Event category emitted by the I/O WebSocket stream."""

    CONNECTION_CHANGED = "connection_changed"
    VALUE_CHANGED = "value_changed"
    WRITE_ACK = "write_ack"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Connection config models (discriminated union on ``protocol``)
# ---------------------------------------------------------------------------


class ModbusTcpConfigModel(BaseModel):
    """Modbus TCP client connection configuration."""

    model_config = ConfigDict(from_attributes=True)

    protocol: Literal["modbus_tcp"] = "modbus_tcp"
    host: str
    port: int = Field(default=502, ge=1, le=65535)
    unit_id: int = Field(default=1, ge=0, le=247)
    timeout_s: float = Field(default=3.0, gt=0)


class ModbusRtuConfigModel(BaseModel):
    """Modbus RTU (serial) client connection configuration."""

    model_config = ConfigDict(from_attributes=True)

    protocol: Literal["modbus_rtu"] = "modbus_rtu"
    device: str
    baudrate: int = Field(default=19200, ge=1200, le=921600)
    parity: Literal["N", "E", "O"] = "N"
    stopbits: Literal[1, 2] = 1
    bytesize: Literal[7, 8] = 8
    unit_id: int = Field(default=1, ge=0, le=247)
    timeout_s: float = Field(default=3.0, gt=0)


class OpcUaConfigModel(BaseModel):
    """OPC-UA client connection configuration (anonymous-only in Phase 4)."""

    model_config = ConfigDict(from_attributes=True)

    protocol: Literal["opcua"] = "opcua"
    url: str
    namespace: int = Field(default=2, ge=0)
    username: Optional[str] = None
    password: Optional[str] = None
    timeout_s: float = Field(default=5.0, gt=0)


class MqttConfigModel(BaseModel):
    """MQTT client connection configuration."""

    model_config = ConfigDict(from_attributes=True)

    protocol: Literal["mqtt"] = "mqtt"
    host: str
    port: int = Field(default=1883, ge=1, le=65535)
    client_id: str
    username: Optional[str] = None
    password: Optional[str] = None
    keepalive_s: int = Field(default=60, ge=1)
    qos: Literal[0, 1, 2] = 0
    timeout_s: float = Field(default=5.0, gt=0)


# Discriminated union — Pydantic v2 uses the ``protocol`` field to select the
# concrete model at parse time.
ConnectionConfigModel = Annotated[
    Union[ModbusTcpConfigModel, ModbusRtuConfigModel, OpcUaConfigModel, MqttConfigModel],
    Field(discriminator="protocol"),
]


# ---------------------------------------------------------------------------
# Signal spec
# ---------------------------------------------------------------------------


class SignalSpecModel(BaseModel):
    """Descriptor for one named I/O signal on a connection."""

    model_config = ConfigDict(from_attributes=True)

    name: str = Field(min_length=1)
    kind: SignalKindModel
    address: str = Field(min_length=1)
    scale: float = 1.0
    offset: float = 0.0
    poll_interval_s: Optional[float] = Field(default=None, gt=0)


# ---------------------------------------------------------------------------
# Connection status
# ---------------------------------------------------------------------------


class IoConnectionStatusModel(BaseModel):
    """Full connection state as returned by the REST API."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    config: ConnectionConfigModel
    status: ConnectionStatusKindModel
    last_error: Optional[str] = None
    connected_at: Optional[float] = None
    signals: list[SignalSpecModel] = []


# ---------------------------------------------------------------------------
# Request bodies
# ---------------------------------------------------------------------------


class IoConnectionCreateRequest(BaseModel):
    """Body for ``POST /api/io/connections``."""

    name: str = Field(min_length=1)
    config: ConnectionConfigModel
    signals: list[SignalSpecModel] = []


# ---------------------------------------------------------------------------
# Value snapshot
# ---------------------------------------------------------------------------


class IoValueSnapshotModel(BaseModel):
    """A single signal reading at a point in time."""

    model_config = ConfigDict(from_attributes=True)

    connection: str
    signal: str
    kind: SignalKindModel
    value: Union[bool, int, float]
    monotonic_s: float


# ---------------------------------------------------------------------------
# I/O event (WebSocket frame)
# ---------------------------------------------------------------------------


class IoEventModel(BaseModel):
    """One observable event emitted on ``/ws/io/stream``.

    Notes
    -----
    The field is named ``type`` here (matching the wire protocol / TypeScript
    contract) even though the underlying ``IoEvent`` dataclass in
    ``src/io/types.py`` calls the same field ``kind``.  The router is
    responsible for the translation.
    """

    model_config = ConfigDict(from_attributes=True)

    type: IoEventTypeModel
    connection: str
    signal: Optional[str] = None
    value: Optional[Union[bool, int, float]] = None
    status: Optional[ConnectionStatusKindModel] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    monotonic_s: float = Field(default_factory=time.monotonic)


# ---------------------------------------------------------------------------
# Write request / response
# ---------------------------------------------------------------------------


class WriteSignalRequest(BaseModel):
    """Body for ``POST /api/io/connections/{name}/signals/{signal}/write``."""

    value: Union[bool, int, float]


class WriteSignalResponse(BaseModel):
    """Response for a successful signal write."""

    connection: str
    signal: str
    value: Union[bool, int, float]
    monotonic_s: float
