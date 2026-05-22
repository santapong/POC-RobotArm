"""Industrial I/O layer — Modbus TCP/RTU, OPC-UA, MQTT.

Phase 4 adds this package to provide a uniform async interface over four
industrial protocols.  Programs running in the server can read and write
named signals; the I/O tab in the web UI shows live values.

Sub-packages
------------
:mod:`src.io.types`
    Frozen dataclasses: :class:`~src.io.types.SignalSpec`,
    :class:`~src.io.types.IoEvent`, config dataclasses,
    JSON round-trip helpers.
:mod:`src.io.errors`
    Exception hierarchy (:class:`~src.io.errors.IoError` and subclasses).
:mod:`src.io.adapter`
    Abstract base class :class:`~src.io.adapter.IoAdapter`.
:mod:`src.io.registry`
    :func:`~src.io.registry.build_adapter` factory.
:mod:`src.io.runtime`
    :class:`~src.io.runtime.IoRuntime` — central brain for one session.
:mod:`src.io.adapters`
    Concrete adapters (lazy-import; pymodbus / asyncua / aiomqtt not
    required at import time).
:mod:`src.io.simulators`
    Test-fixture simulators (pymodbus server, asyncua server,
    mosquitto subprocess).

Notes
-----
* ``import src.io`` succeeds without the ``[io]`` extra installed.  Heavy
  library imports live inside adapter method bodies.
* All units are SI.  All async methods propagate ``asyncio.CancelledError``.
* This package is **not** imported at the server module level — it is
  instantiated lazily when the first connection is created (mirrors the
  ``vision_runtime`` / ``planning_runtime`` pattern).
"""

from __future__ import annotations

# Re-export the public symbols that callers need without diving into sub-modules.
from src.io.adapter import AdapterCapabilities, IoAdapter
from src.io.errors import (
    IoConnectionError,
    IoError,
    IoNotConnected,
    IoProtocolError,
    IoSignalKindMismatch,
    IoTimeout,
    IoUnavailable,
    IoUnknownSignal,
)
from src.io.registry import build_adapter
from src.io.runtime import IoRuntime
from src.io.types import (
    ConnectionConfig,
    ConnectionProtocol,
    ConnectionStatusKind,
    IoEvent,
    ModbusRtuConfig,
    ModbusTcpConfig,
    MqttConfig,
    OpcUaConfig,
    SignalKind,
    SignalSpec,
    from_dict,
    to_dict,
)

__all__ = [
    # Adapter ABC
    "IoAdapter",
    "AdapterCapabilities",
    # Errors
    "IoError",
    "IoUnavailable",
    "IoConnectionError",
    "IoNotConnected",
    "IoTimeout",
    "IoProtocolError",
    "IoSignalKindMismatch",
    "IoUnknownSignal",
    # Types
    "SignalKind",
    "ConnectionProtocol",
    "ConnectionStatusKind",
    "ModbusTcpConfig",
    "ModbusRtuConfig",
    "OpcUaConfig",
    "MqttConfig",
    "ConnectionConfig",
    "SignalSpec",
    "IoEvent",
    # Factory
    "build_adapter",
    # Runtime
    "IoRuntime",
    # JSON I/O
    "to_dict",
    "from_dict",
]
