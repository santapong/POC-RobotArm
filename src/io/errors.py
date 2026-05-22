"""I/O subsystem error hierarchy.

All public exceptions inherit from :class:`IoError`.  Router and runtime code
catch these specific subclasses and map them to the ``IO_*`` error codes
defined in §K of the Phase 4 master plan.

Notes
-----
* This module is stdlib-only — no heavy protocol libs imported.
* ``import src.io.errors`` succeeds even when the ``[io]`` extra is absent.
* Each subclass carries a human-readable ``message`` as its first positional
  argument so ``str(exc)`` always returns something useful to an operator.
"""

from __future__ import annotations

__all__ = [
    "IoError",
    "IoUnavailable",
    "IoConnectionError",
    "IoNotConnected",
    "IoTimeout",
    "IoProtocolError",
    "IoSignalKindMismatch",
    "IoUnknownSignal",
]


class IoError(RuntimeError):
    """Base class for all I/O subsystem errors."""


class IoUnavailable(IoError):
    """Raised when a required library (pymodbus, asyncua, aiomqtt) is missing.

    ``import src.io`` succeeds on every platform; this error fires at the first
    concrete-adapter ``__init__`` that tries to import its library, or when
    ``build_adapter`` is called without the ``[io]`` extra installed.
    """


class IoConnectionError(IoError):
    """Raised when an adapter fails to establish or maintain a connection.

    Maps to HTTP 503 ``IO_CONNECTION_FAILED``.

    Examples
    --------
    * TCP connection refused.
    * OPC-UA handshake timeout.
    * MQTT broker unreachable.
    """


class IoNotConnected(IoError):
    """Raised when a read / write is attempted on a slot whose status is not ``open``.

    Maps to HTTP 503 ``IO_NOT_CONNECTED``.
    """


class IoTimeout(IoError):
    """Raised when an adapter call exceeds its configured timeout.

    Maps to HTTP 504 ``IO_TIMEOUT``.
    """


class IoProtocolError(IoError):
    """Raised on a protocol-level fault from the remote device.

    Examples: Modbus exception response 0x06 (server busy), OPC-UA
    ``BadUserAccessDenied``.  Maps to HTTP 502 ``IO_PROTOCOL_ERROR``.
    """


class IoSignalKindMismatch(IoError):
    """Raised when a write value is incompatible with the signal's declared kind.

    Example: writing a ``float`` to a ``digital_out`` signal.
    Maps to HTTP 422 ``IO_SIGNAL_KIND_MISMATCH``.
    """


class IoUnknownSignal(IoError):
    """Raised when a signal name is not found in the connection's signal map.

    Maps to HTTP 404 ``IO_SIGNAL_UNKNOWN``.
    """
