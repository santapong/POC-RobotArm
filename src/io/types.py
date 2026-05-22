"""Frozen dataclasses, enums, and JSON round-trip utilities for the I/O layer.

Mirrors the convention established by :mod:`src.planning.types` and
:mod:`src.motion.ir`:

* All dataclasses are ``frozen=True`` (hashable, safe to share across coroutines).
* Validation runs in ``__post_init__`` — bad inputs raise :class:`ValueError`.
* JSON round-trip via :func:`to_dict` / :func:`from_dict` with a ``__type__``
  discriminator key for self-describing serialisation.

Notes
-----
* This module is stdlib-only.  ``import src.io.types`` succeeds without the
  ``[io]`` extra installed.
* All string literals that appear in ``__type__`` are stable public API —
  do not rename dataclasses without updating the registry.
* ``ConnectionConfig`` is a sealed Union discriminated by the ``protocol``
  field (str enum value), mirroring the Pydantic wire model in
  ``server/models/io.py``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from typing import Any, Literal, Union

from src.io.errors import IoError  # noqa: F401 — re-exported for convenience

__all__ = [
    # Enums
    "SignalKind",
    "ConnectionProtocol",
    "ConnectionStatusKind",
    # Configs
    "ModbusTcpConfig",
    "ModbusRtuConfig",
    "OpcUaConfig",
    "MqttConfig",
    "ConnectionConfig",
    # Signal / event
    "SignalSpec",
    "IoEvent",
    # JSON I/O
    "to_dict",
    "from_dict",
]


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SignalKind(str, Enum):
    """Direction and type of an I/O signal."""

    DIGITAL_IN = "digital_in"
    DIGITAL_OUT = "digital_out"
    ANALOG_IN = "analog_in"
    ANALOG_OUT = "analog_out"


class ConnectionProtocol(str, Enum):
    """Wire protocol for a connection."""

    MODBUS_TCP = "modbus_tcp"
    MODBUS_RTU = "modbus_rtu"
    OPCUA = "opcua"
    MQTT = "mqtt"


class ConnectionStatusKind(str, Enum):
    """Lifecycle state of a connection slot."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    OPEN = "open"
    ERROR = "error"
    CLOSING = "closing"


# ---------------------------------------------------------------------------
# Connection configs — discriminated by ``protocol``
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModbusTcpConfig:
    """Configuration for a Modbus TCP client connection."""

    host: str
    port: int = 502
    unit_id: int = 1
    timeout_s: float = 3.0
    protocol: Literal["modbus_tcp"] = "modbus_tcp"

    def __post_init__(self) -> None:
        if not self.host:
            raise ValueError("ModbusTcpConfig.host must not be empty")
        if not (1 <= self.port <= 65535):
            raise ValueError(f"ModbusTcpConfig.port must be 1-65535, got {self.port}")
        if not (0 <= self.unit_id <= 247):
            raise ValueError(f"ModbusTcpConfig.unit_id must be 0-247, got {self.unit_id}")
        if self.timeout_s <= 0.0:
            raise ValueError(f"ModbusTcpConfig.timeout_s must be > 0, got {self.timeout_s}")


@dataclass(frozen=True)
class ModbusRtuConfig:
    """Configuration for a Modbus RTU (serial) client connection."""

    device: str
    baudrate: int = 19200
    parity: Literal["N", "E", "O"] = "N"
    stopbits: Literal[1, 2] = 1
    bytesize: Literal[7, 8] = 8
    unit_id: int = 1
    timeout_s: float = 3.0
    protocol: Literal["modbus_rtu"] = "modbus_rtu"

    def __post_init__(self) -> None:
        if not self.device:
            raise ValueError("ModbusRtuConfig.device must not be empty")
        if not (1200 <= self.baudrate <= 921600):
            raise ValueError(f"ModbusRtuConfig.baudrate must be 1200-921600, got {self.baudrate}")
        if self.parity not in ("N", "E", "O"):
            raise ValueError(f"ModbusRtuConfig.parity must be N/E/O, got {self.parity!r}")
        if self.stopbits not in (1, 2):
            raise ValueError(f"ModbusRtuConfig.stopbits must be 1 or 2, got {self.stopbits}")
        if self.bytesize not in (7, 8):
            raise ValueError(f"ModbusRtuConfig.bytesize must be 7 or 8, got {self.bytesize}")
        if not (0 <= self.unit_id <= 247):
            raise ValueError(f"ModbusRtuConfig.unit_id must be 0-247, got {self.unit_id}")
        if self.timeout_s <= 0.0:
            raise ValueError(f"ModbusRtuConfig.timeout_s must be > 0, got {self.timeout_s}")


@dataclass(frozen=True)
class OpcUaConfig:
    """Configuration for an OPC-UA client connection (anonymous-only in Phase 4)."""

    url: str
    namespace: int = 2
    timeout_s: float = 5.0
    username: str | None = None
    password: str | None = None
    protocol: Literal["opcua"] = "opcua"

    def __post_init__(self) -> None:
        if not self.url:
            raise ValueError("OpcUaConfig.url must not be empty")
        if self.namespace < 0:
            raise ValueError(f"OpcUaConfig.namespace must be >= 0, got {self.namespace}")
        if self.timeout_s <= 0.0:
            raise ValueError(f"OpcUaConfig.timeout_s must be > 0, got {self.timeout_s}")


@dataclass(frozen=True)
class MqttConfig:
    """Configuration for an MQTT client connection."""

    host: str
    port: int = 1883
    timeout_s: float = 5.0
    client_id: str = ""
    username: str | None = None
    password: str | None = None
    keepalive_s: int = 60
    qos: Literal[0, 1, 2] = 0
    protocol: Literal["mqtt"] = "mqtt"

    def __post_init__(self) -> None:
        if not self.host:
            raise ValueError("MqttConfig.host must not be empty")
        if not (1 <= self.port <= 65535):
            raise ValueError(f"MqttConfig.port must be 1-65535, got {self.port}")
        if self.timeout_s <= 0.0:
            raise ValueError(f"MqttConfig.timeout_s must be > 0, got {self.timeout_s}")
        if self.keepalive_s < 1:
            raise ValueError(f"MqttConfig.keepalive_s must be >= 1, got {self.keepalive_s}")
        if self.qos not in (0, 1, 2):
            raise ValueError(f"MqttConfig.qos must be 0, 1, or 2, got {self.qos}")


# Sealed union discriminated by the ``protocol`` field value.
ConnectionConfig = Union[ModbusTcpConfig, ModbusRtuConfig, OpcUaConfig, MqttConfig]

# Mapping from protocol string to config class — used by from_dict discriminator.
_PROTOCOL_TO_CONFIG: dict[str, type] = {
    "modbus_tcp": ModbusTcpConfig,
    "modbus_rtu": ModbusRtuConfig,
    "opcua": OpcUaConfig,
    "mqtt": MqttConfig,
}


# ---------------------------------------------------------------------------
# Signal spec
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SignalSpec:
    """Descriptor for one I/O signal on a connection.

    Parameters
    ----------
    name:
        Logical name used by the program IR (e.g. ``"di0"``).
    kind:
        Signal direction and type.
    address:
        Protocol-specific address string.  Modbus: ``"coil:0"`` or
        ``"holding:3"``.  OPC-UA: ``"i=42"`` or ``"s=MyTag"``.
        MQTT: ``"robot/cycles"`` (topic path).
    poll_interval_s:
        Polling interval for Modbus (which has no push).  ``None`` means
        "use the adapter default" or "subscribe" for OPC-UA / MQTT.
    qos:
        MQTT QoS level override for this signal.  ``None`` inherits from the
        connection config.
    scale:
        Analog scale factor applied on read.  Default 1.0 (no scaling).
    offset:
        Analog offset applied on read (after scaling).  Default 0.0.
    """

    name: str
    kind: SignalKind
    address: str
    poll_interval_s: float | None = None
    qos: int | None = None
    scale: float = 1.0
    offset: float = 0.0

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("SignalSpec.name must not be empty")
        if not isinstance(self.kind, SignalKind):
            object.__setattr__(self, "kind", SignalKind(self.kind))
        if not self.address:
            raise ValueError("SignalSpec.address must not be empty")
        if self.poll_interval_s is not None and self.poll_interval_s <= 0.0:
            raise ValueError(
                f"SignalSpec.poll_interval_s must be > 0 when set, got {self.poll_interval_s}"
            )
        if self.qos is not None and self.qos not in (0, 1, 2):
            raise ValueError(f"SignalSpec.qos must be 0, 1, or 2, got {self.qos}")


# ---------------------------------------------------------------------------
# I/O event
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IoEvent:
    """One observable event emitted by an adapter's ``watch()`` generator.

    Parameters
    ----------
    connection:
        Name of the connection this event belongs to.
    kind:
        Event category.  ``"connection_changed"`` fires when the connection
        status changes.  ``"value_changed"`` fires on a polled or subscribed
        signal update.  ``"write_ack"`` is synthetic — emitted by
        :class:`IoRuntime` after a successful write.  ``"error"`` wraps an
        adapter-level fault.
    signal:
        Signal name, or ``None`` for connection-level events.
    value:
        Signal value for ``"value_changed"`` / ``"write_ack"``, or ``None``.
    status:
        New connection status for ``"connection_changed"`` events, or ``None``.
    monotonic_s:
        ``time.monotonic()`` timestamp taken at event creation.
    """

    connection: str
    kind: Literal["connection_changed", "value_changed", "write_ack", "error"]
    signal: str | None = None
    value: bool | int | float | None = None
    status: str | None = None
    monotonic_s: float | None = None

    def __post_init__(self) -> None:
        if not self.connection:
            raise ValueError("IoEvent.connection must not be empty")
        if self.kind not in ("connection_changed", "value_changed", "write_ack", "error"):
            raise ValueError(f"IoEvent.kind {self.kind!r} is not a valid event kind")
        # Resolve None sentinel to now; a caller-supplied value (including 0.0) is kept as-is.
        if self.monotonic_s is None:
            object.__setattr__(self, "monotonic_s", time.monotonic())


# ---------------------------------------------------------------------------
# JSON round-trip  (mirrors src/motion/ir.py and src/planning/types.py)
# ---------------------------------------------------------------------------

_TYPE_REGISTRY: dict[str, type] = {
    "ModbusTcpConfig": ModbusTcpConfig,
    "ModbusRtuConfig": ModbusRtuConfig,
    "OpcUaConfig": OpcUaConfig,
    "MqttConfig": MqttConfig,
    "SignalSpec": SignalSpec,
    "IoEvent": IoEvent,
}


def _encode(value: Any) -> Any:
    """Recursively convert a dataclass tree to JSON-friendly primitives."""
    if value is None:
        return None
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        out: dict[str, Any] = {"__type__": type(value).__name__}
        for f in fields(value):
            out[f.name] = _encode(getattr(value, f.name))
        return out
    if isinstance(value, dict):
        return {str(k): _encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(v) for v in value]
    if isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"Cannot encode value of type {type(value).__name__}: {value!r}")


def _decode(value: Any, hint: Any = None) -> Any:
    """Recursively reconstruct dataclasses from JSON primitives."""
    if value is None:
        return None

    if isinstance(value, dict) and "__type__" in value:
        type_name = value["__type__"]
        cls = _TYPE_REGISTRY.get(type_name)
        if cls is None:
            raise ValueError(f"Unknown __type__ in JSON: {type_name!r}")
        kwargs: dict[str, Any] = {}
        cls_fields = {f.name: f for f in fields(cls)}
        for key, raw in value.items():
            if key == "__type__":
                continue
            if key not in cls_fields:
                # Forward-compat: drop unknown keys rather than crashing.
                continue
            kwargs[key] = _decode(raw, cls_fields[key].type)
        return cls(**kwargs)

    if isinstance(value, dict):
        return {k: _decode(v) for k, v in value.items()}

    if isinstance(value, list):
        decoded = [_decode(v) for v in value]
        if isinstance(hint, str) and hint.startswith("tuple"):
            return tuple(decoded)
        return decoded

    return value


def to_dict(obj: Any) -> Any:
    """Serialize an I/O dataclass to a JSON-compatible dict."""
    return _encode(obj)


def from_dict(data: Any, cls: type | None = None) -> Any:
    """Deserialize a dict tree back to I/O dataclasses.

    The ``__type__`` discriminator is self-describing; ``cls`` is advisory
    and used only to validate the top-level decoded type.
    """
    decoded = _decode(data)
    if cls is not None and not isinstance(decoded, cls):
        raise ValueError(
            f"Decoded type {type(decoded).__name__} does not match expected {cls.__name__}"
        )
    return decoded
