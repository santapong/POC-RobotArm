"""Abstract base class for I/O protocol adapters.

Every concrete adapter (Modbus TCP, Modbus RTU, OPC-UA, MQTT) implements
this ABC.  The runtime holds a reference to an :class:`IoAdapter` instance
per connection and calls :meth:`connect`, :meth:`watch`, :meth:`read`,
:meth:`write`, and :meth:`disconnect` on it.

Notes
-----
* All methods are ``async``.  Adapters MUST NOT block the event loop.
* :meth:`watch` is an **async generator** — ``async for event in
  adapter.watch(signals): ...``.  The generator must propagate
  ``asyncio.CancelledError`` without swallowing it.
* Adapters assume serial access from a single coroutine — write
  serialisation via ``asyncio.Lock`` is the responsibility of
  :class:`IoRuntime`, not the adapter.
* Concrete ``__init__`` raises :class:`~src.io.errors.IoUnavailable` when
  the underlying library is not installed.
"""

from __future__ import annotations

import abc
from typing import AsyncIterator, Sequence

from src.io.errors import IoUnavailable  # noqa: F401 — convenience re-export
from src.io.types import IoEvent, SignalSpec

__all__ = [
    "IoAdapter",
    "AdapterCapabilities",
]


class AdapterCapabilities:
    """Bitmask-style capability flags returned by :attr:`IoAdapter.capabilities`.

    Attributes
    ----------
    supports_subscribe:
        ``True`` when the adapter can push value-changed events without
        polling (OPC-UA monitored items, MQTT subscriptions).
        ``False`` for Modbus (poll-only).
    supports_write:
        ``True`` when the adapter can write signal values.  All four
        Phase-4 adapters support write; the flag is here for extensibility.
    supports_analog:
        ``True`` when the adapter can read / write analog (float) signals.
    """

    __slots__ = ("supports_subscribe", "supports_write", "supports_analog")

    def __init__(
        self,
        *,
        supports_subscribe: bool,
        supports_write: bool,
        supports_analog: bool,
    ) -> None:
        self.supports_subscribe = supports_subscribe
        self.supports_write = supports_write
        self.supports_analog = supports_analog

    def __repr__(self) -> str:
        return (
            f"AdapterCapabilities(subscribe={self.supports_subscribe}, "
            f"write={self.supports_write}, analog={self.supports_analog})"
        )


class IoAdapter(abc.ABC):
    """Protocol-agnostic async I/O adapter.

    Lifecycle
    ---------
    1. ``await adapter.connect()`` — open the connection.
    2. ``async for event in adapter.watch(signals)`` — receive events.
    3. ``await adapter.read(signal)`` — read one signal on demand.
    4. ``await adapter.write(signal, value)`` — write one signal.
    5. ``await adapter.disconnect()`` — close the connection (idempotent).

    All methods must honour ``asyncio.CancelledError``; ``connect()`` must
    close any partially-opened socket on cancellation.
    """

    # ------------------------------------------------------------------ #
    # Capabilities                                                          #
    # ------------------------------------------------------------------ #

    @property
    @abc.abstractmethod
    def capabilities(self) -> AdapterCapabilities:
        """Return the static capability flags for this adapter type."""

    # ------------------------------------------------------------------ #
    # Lifecycle                                                             #
    # ------------------------------------------------------------------ #

    @abc.abstractmethod
    async def connect(self) -> None:
        """Open the connection to the remote device / broker.

        Raises
        ------
        IoConnectionError
            If the connection cannot be established.
        IoUnavailable
            If the required library is not installed.
        asyncio.CancelledError
            Propagated if the caller cancels during connect.
        """

    @abc.abstractmethod
    async def disconnect(self) -> None:
        """Close the connection.  Idempotent — safe to call more than once."""

    # ------------------------------------------------------------------ #
    # Read / write                                                          #
    # ------------------------------------------------------------------ #

    @abc.abstractmethod
    async def read(self, signal: SignalSpec) -> IoEvent:
        """Read the current value of ``signal`` and return an :class:`IoEvent`.

        Parameters
        ----------
        signal:
            The :class:`SignalSpec` describing the signal to read.

        Returns
        -------
        IoEvent
            An event with ``kind="value_changed"`` containing the raw value.

        Raises
        ------
        IoNotConnected
            If the adapter is not in the ``open`` state.
        IoTimeout
            If the remote device does not respond within the configured timeout.
        IoProtocolError
            On a protocol-level fault from the remote device.
        """

    @abc.abstractmethod
    async def write(self, signal: SignalSpec, value: bool | int | float) -> IoEvent:
        """Write ``value`` to ``signal``.

        Parameters
        ----------
        signal:
            The :class:`SignalSpec` describing the signal to write.
        value:
            The value to write.  The adapter may coerce types as needed by
            the protocol (e.g. int → bool for a Modbus coil).

        Returns
        -------
        IoEvent
            A synthetic event with ``kind="write_ack"`` for the caller to
            forward to subscribers.

        Raises
        ------
        IoNotConnected
            If the adapter is not in the ``open`` state.
        IoTimeout
            If the remote device does not respond within the configured timeout.
        IoProtocolError
            On a protocol-level fault (e.g. Modbus exception 0x06, OPC-UA
            ``BadUserAccessDenied``).
        """

    @abc.abstractmethod
    async def watch(self, signals: Sequence[SignalSpec]) -> AsyncIterator[IoEvent]:
        """Async generator that yields :class:`IoEvent` objects indefinitely.

        The generator runs until it is cancelled or the connection is lost.
        ``asyncio.CancelledError`` is **not** swallowed — it propagates to
        the caller, allowing the ``_watch_loop`` task in :class:`IoRuntime`
        to unwind cleanly.

        Parameters
        ----------
        signals:
            The signals to watch.  For Modbus, these are polled at
            ``signal.poll_interval_s`` (or the adapter default).  For OPC-UA
            and MQTT, the adapter subscribes / subscribes-to-topics.

        Yields
        ------
        IoEvent
            Value-changed events, one per signal update.  Connection-changed
            events are emitted by :class:`IoRuntime`, not by the adapter.
        """
        # Satisfy the typing system — concrete implementations use ``yield``.
        raise NotImplementedError
        # This line is unreachable but satisfies the AsyncIterator return type.
        yield  # type: ignore[misc]
