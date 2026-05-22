"""IoRuntime — owns connections, dispatches events, and serialises writes.

This is the central brain of the I/O layer.  A single :class:`IoRuntime`
instance lives per server session (analogous to ``PlanningRuntime`` in
Phase 3).

Notes
-----
* All connection lifecycle operations are protected by ``IoRuntime.lock``
  (an ``asyncio.Lock``) to serialise ``add_connection``, ``remove_connection``,
  and ``update_signals``.  Adapter calls (``connect``, ``disconnect``) happen
  **outside** the lock to avoid stalling other connections during a slow handshake.
* Per-connection write serialisation is provided by ``_ConnectionSlot.write_lock``
  (``asyncio.Lock``), preventing interleaving of concurrent REST writes and
  program-executor writes (risk #7).
* ``_last_values`` is guarded by ``_values_lock`` (``threading.Lock``) because
  two concurrent ``_watch_loop`` tasks may both write, and synchronous GET
  routes want a copy without suspending.  This matches the ``_plan_cache_lock``
  precedent in ``server/services/planning.py``.
* The watch loop (``_watch_loop``) is a long-lived ``asyncio.Task`` per
  connection.  ``remove_connection`` cancels it and awaits completion within
  3 s.  ``stop()`` cancels all and awaits within 5 s.
* ``asyncio.CancelledError`` propagates through every adapter method — the
  watch loop unwinds cleanly on cancellation without leaving sockets open.
* Auto-reconnect is **client-driven only** in Phase 4.  If a watch loop
  terminates with an error (status=ERROR), the operator must POST
  ``/api/io/connections/{name}/reconnect`` to re-establish the connection.
  The runtime does not attempt any automatic reconnection.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Sequence

from src.io.adapter import IoAdapter
from src.io.errors import (
    IoConnectionError,
    IoNotConnected,
    IoSignalKindMismatch,
    IoTimeout,
    IoUnknownSignal,
)
from src.io.registry import build_adapter
from src.io.types import (
    ConnectionConfig,
    ConnectionStatusKind,
    IoEvent,
    SignalKind,
    SignalSpec,
)

__all__ = ["IoRuntime"]

_log = logging.getLogger(__name__)

_REMOVE_TIMEOUT_S = 3.0
_STOP_TIMEOUT_S = 5.0
_CONNECT_DEFAULT_TIMEOUT_S = 5.0


@dataclass
class _ConnectionSlot:
    """Internal slot tracking one active connection."""

    name: str
    config: ConnectionConfig
    adapter: IoAdapter
    signals: dict[str, SignalSpec]  # keyed by signal.name
    watch_task: asyncio.Task | None
    write_lock: asyncio.Lock
    status: ConnectionStatusKind
    last_error: str | None
    connected_at: float | None


class IoRuntime:
    """Central I/O runtime that owns connections, events, and writes.

    One instance per server session.  Create, then call
    :meth:`add_connection` for each connection.  Call :meth:`stop` during
    server shutdown.
    """

    def __init__(self) -> None:
        self._connections: dict[str, _ConnectionSlot] = {}
        # Serialises lifecycle mutations (add / remove / update_signals).
        self.lock: asyncio.Lock = asyncio.Lock()
        # Guards _last_values; threading.Lock so sync GET routes don't suspend.
        self._values_lock: threading.Lock = threading.Lock()
        self._last_values: dict[str, IoEvent] = {}  # "<conn>.<signal>" → IoEvent
        # WebSocket subscriber queues.
        self._subscribers: list[asyncio.Queue] = []

    # ------------------------------------------------------------------
    # WS pub/sub
    # ------------------------------------------------------------------

    def subscribe(self, q: asyncio.Queue) -> None:
        """Register a WebSocket event queue."""
        if q not in self._subscribers:
            self._subscribers.append(q)

    def unsubscribe(self, q: asyncio.Queue) -> None:
        """Deregister a WebSocket event queue."""
        try:
            self._subscribers.remove(q)
        except ValueError:
            pass

    def _publish(self, event: IoEvent) -> None:
        """Forward an event to all subscriber queues (drop oldest on full)."""
        for q in list(self._subscribers):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Drop oldest to keep the queue moving (risk #15).
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass

    # ------------------------------------------------------------------
    # Internal watch loop
    # ------------------------------------------------------------------

    async def _watch_loop(self, slot: _ConnectionSlot) -> None:
        """Consume events from ``slot.adapter.watch()`` and forward them."""
        try:
            async for event in slot.adapter.watch(list(slot.signals.values())):
                # Update the last-values cache.
                key = f"{slot.name}.{event.signal}"
                with self._values_lock:
                    self._last_values[key] = event
                # Attach the connection name (adapter sets its own internal id).
                forwarded = IoEvent(
                    connection=slot.name,
                    kind=event.kind,
                    signal=event.signal,
                    value=event.value,
                    status=event.status,
                    monotonic_s=event.monotonic_s,
                )
                self._publish(forwarded)
        except asyncio.CancelledError:
            raise  # propagate for clean task teardown
        except Exception:
            # Adapter failure — mark slot as error. Auto-reconnect is client-driven
            # (operator must POST /api/io/connections/{name}/reconnect).
            _log.exception("watch loop %s failed", slot.name)
            slot.status = ConnectionStatusKind.ERROR
            self._publish(
                IoEvent(
                    connection=slot.name,
                    kind="connection_changed",
                    status=ConnectionStatusKind.ERROR.value,
                    monotonic_s=time.monotonic(),
                )
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def add_connection(
        self,
        name: str,
        config: ConnectionConfig,
        signals: Sequence[SignalSpec],
    ) -> _ConnectionSlot:
        """Add and connect a new I/O connection.

        Parameters
        ----------
        name:
            Logical name for this connection (unique per runtime).
        config:
            Protocol-specific connection config.
        signals:
            Initial signal map for this connection.

        Raises
        ------
        ValueError
            If ``name`` already exists (maps to ``IO_CONNECTION_EXISTS`` 409).
        IoConnectionError
            If the adapter fails to connect.
        """
        async with self.lock:
            if name in self._connections:
                raise ValueError(f"connection {name!r} already exists")

        adapter = build_adapter(config)

        # Connect outside the lock so a slow handshake doesn't block other connections.
        timeout = getattr(config, "timeout_s", _CONNECT_DEFAULT_TIMEOUT_S)
        try:
            await asyncio.wait_for(adapter.connect(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise IoConnectionError(
                f"Connection {name!r} timed out after {timeout} s"
            ) from exc

        slot = _ConnectionSlot(
            name=name,
            config=config,
            adapter=adapter,
            signals={s.name: s for s in signals},
            watch_task=None,
            write_lock=asyncio.Lock(),
            status=ConnectionStatusKind.OPEN,
            last_error=None,
            connected_at=time.monotonic(),
        )

        async with self.lock:
            # Re-check after lock re-acquire — another coroutine may have added it.
            if name in self._connections:
                await adapter.disconnect()
                raise ValueError(f"connection {name!r} already exists")
            self._connections[name] = slot

        # Spawn the watch task.
        task = asyncio.get_running_loop().create_task(
            self._watch_loop(slot), name=f"io_watch_{name}"
        )
        slot.watch_task = task

        self._publish(
            IoEvent(
                connection=name,
                kind="connection_changed",
                status=ConnectionStatusKind.OPEN.value,
                monotonic_s=time.monotonic(),
            )
        )
        return slot

    async def remove_connection(self, name: str) -> None:
        """Disconnect and remove a connection.

        Cancels the watch task, awaits it within 3 s, then disconnects.

        Raises
        ------
        KeyError
            If ``name`` is not a known connection.
        """
        async with self.lock:
            slot = self._connections.pop(name)  # raises KeyError if absent

        slot.status = ConnectionStatusKind.CLOSING

        if slot.watch_task is not None and not slot.watch_task.done():
            slot.watch_task.cancel()
            try:
                await asyncio.wait_for(
                    asyncio.shield(slot.watch_task), timeout=_REMOVE_TIMEOUT_S
                )
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass  # task is cancelled or timed out — move on

        try:
            await slot.adapter.disconnect()
        except Exception:
            pass

        # Clean up cached values.
        prefix = f"{name}."
        with self._values_lock:
            keys_to_remove = [k for k in self._last_values if k.startswith(prefix)]
            for k in keys_to_remove:
                del self._last_values[k]

        self._publish(
            IoEvent(
                connection=name,
                kind="connection_changed",
                status=ConnectionStatusKind.DISCONNECTED.value,
                monotonic_s=time.monotonic(),
            )
        )

    async def connect(self, name: str) -> _ConnectionSlot:
        """Connect an existing disconnected slot without destroying it.

        Calls ``adapter.connect()`` and sets ``status=open``.  If the slot is
        already open this is a no-op (returns the slot unchanged).  To replace
        the connection config entirely, use :meth:`remove_connection` followed
        by :meth:`add_connection`.

        Raises
        ------
        KeyError
            If ``name`` is not a known connection.
        IoConnectionError
            If the adapter fails to connect.
        """
        async with self.lock:
            slot = self._connections.get(name)
            if slot is None:
                raise KeyError(name)

        if slot.status == ConnectionStatusKind.OPEN:
            return slot

        timeout = getattr(slot.config, "timeout_s", _CONNECT_DEFAULT_TIMEOUT_S)
        try:
            await asyncio.wait_for(slot.adapter.connect(), timeout=timeout)
        except asyncio.TimeoutError as exc:
            raise IoConnectionError(
                f"Connection {name!r} timed out after {timeout} s"
            ) from exc

        async with self.lock:
            # Re-validate: another coroutine may have removed/replaced the slot.
            if self._connections.get(name) is not slot:
                return slot
            slot.status = ConnectionStatusKind.OPEN
            slot.connected_at = time.monotonic()
            old_task = slot.watch_task
            slot.watch_task = asyncio.get_running_loop().create_task(
                self._watch_loop(slot), name=f"io_watch_{name}"
            )

        # Cancel old watch task outside the lock.
        if old_task is not None and not old_task.done():
            old_task.cancel()
            try:
                await old_task
            except (asyncio.CancelledError, Exception):
                pass

        self._publish(
            IoEvent(
                connection=name,
                kind="connection_changed",
                status=ConnectionStatusKind.OPEN.value,
                monotonic_s=time.monotonic(),
            )
        )
        return slot

    async def disconnect(self, name: str) -> _ConnectionSlot:
        """Disconnect an existing slot without removing it.

        Calls ``adapter.disconnect()``, cancels the watch task, and sets
        ``status=disconnected``.  The slot remains in the registry so it can
        be reconnected later via :meth:`connect` or :meth:`reconnect`.

        Raises
        ------
        KeyError
            If ``name`` is not a known connection.
        """
        async with self.lock:
            slot = self._connections.get(name)
            if slot is None:
                raise KeyError(name)
            old_task = slot.watch_task
            slot.watch_task = None
            slot.status = ConnectionStatusKind.DISCONNECTED

        if old_task is not None and not old_task.done():
            old_task.cancel()
            try:
                await asyncio.wait_for(
                    asyncio.shield(old_task), timeout=_REMOVE_TIMEOUT_S
                )
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

        try:
            await slot.adapter.disconnect()
        except Exception:
            pass

        self._publish(
            IoEvent(
                connection=name,
                kind="connection_changed",
                status=ConnectionStatusKind.DISCONNECTED.value,
                monotonic_s=time.monotonic(),
            )
        )
        return slot

    async def reconnect(self, name: str) -> _ConnectionSlot:
        """Disconnect then reconnect an existing slot (same config and signal map).

        This is the operator-facing endpoint for recovering a dropped connection.
        It preserves the slot — config and signals are unchanged.

        Raises
        ------
        KeyError
            If ``name`` is not a known connection.
        IoConnectionError
            If the new connection fails.
        """
        async with self.lock:
            slot = self._connections.get(name)
            if slot is None:
                raise KeyError(name)

        await self.disconnect(name)

        async with self.lock:
            # Re-validate after disconnect: another coroutine could have removed the slot.
            if self._connections.get(name) is not slot:
                raise KeyError(name)

        return await self.connect(name)

    async def update_signals(
        self,
        name: str,
        signals: Sequence[SignalSpec],
    ) -> _ConnectionSlot:
        """Atomically replace the signal map for a connection.

        Tears down the watch task, updates the signal map, and restarts
        the watch task.  This satisfies risk #8 (signal-map drift).

        Raises
        ------
        KeyError
            If ``name`` is not a known connection.
        """
        async with self.lock:
            slot = self._connections.get(name)
            if slot is None:
                raise KeyError(name)
            # Snapshot the watch task and update signals while holding the lock.
            old_task = slot.watch_task
            slot.signals = {s.name: s for s in signals}

        # Cancel and await the old task OUTSIDE the lock to avoid blocking other connections.
        if old_task is not None and not old_task.done():
            old_task.cancel()
            try:
                await old_task
            except (asyncio.CancelledError, Exception):
                pass

        async with self.lock:
            # Re-validate: connection may have been removed/replaced during the gap.
            if self._connections.get(name) is not slot:
                return slot
            slot.watch_task = asyncio.get_running_loop().create_task(
                self._watch_loop(slot), name=f"io_watch_{name}"
            )

        self._publish(
            IoEvent(
                connection=name,
                kind="connection_changed",
                status=slot.status.value,
                monotonic_s=time.monotonic(),
            )
        )
        return slot

    async def stop(self) -> None:
        """Cancel all watch tasks and disconnect all adapters.

        Awaits task completion within 5 s (returns_exceptions=True).
        Called during server lifespan teardown.
        """
        async with self.lock:
            slots = list(self._connections.values())
            self._connections.clear()

        tasks = []
        for slot in slots:
            if slot.watch_task is not None and not slot.watch_task.done():
                slot.watch_task.cancel()
                tasks.append(slot.watch_task)

        if tasks:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=_STOP_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                pass

        for slot in slots:
            try:
                await slot.adapter.disconnect()
            except Exception:
                pass

        with self._values_lock:
            self._last_values.clear()

    # ------------------------------------------------------------------
    # Reads and writes
    # ------------------------------------------------------------------

    async def read(self, connection: str, signal: str) -> IoEvent:
        """Read one signal from a connection.

        Raises
        ------
        KeyError
            If ``connection`` is not known (maps to ``IO_CONNECTION_UNKNOWN``).
        IoUnknownSignal
            If ``signal`` is not in the connection's signal map.
        IoNotConnected
            If the connection is not ``open``.
        IoTimeout
            If the adapter call times out.
        IoProtocolError
            On a protocol-level fault.
        """
        slot = self._connections.get(connection)
        if slot is None:
            raise KeyError(connection)
        if slot.status != ConnectionStatusKind.OPEN:
            raise IoNotConnected(
                f"Connection {connection!r} is not open (status: {slot.status.value})"
            )
        sig = slot.signals.get(signal)
        if sig is None:
            raise IoUnknownSignal(f"Signal {signal!r} not found in connection {connection!r}")

        event = await slot.adapter.read(sig)
        # Normalise connection name to the slot name (adapter uses its own internal id).
        return IoEvent(
            connection=connection,
            kind=event.kind,
            signal=event.signal,
            value=event.value,
            status=event.status,
            monotonic_s=event.monotonic_s,
        )

    async def write(
        self,
        connection: str,
        signal: str,
        value: bool | int | float,
    ) -> IoEvent:
        """Write a value to a signal.

        Acquires the per-connection write lock before dispatching to the
        adapter, ensuring concurrent writes serialise (risk #7).

        Raises
        ------
        KeyError
            If ``connection`` is not known.
        IoUnknownSignal
            If ``signal`` is not in the connection's signal map.
        IoNotConnected
            If the connection is not ``open``.
        IoSignalKindMismatch
            If the value type doesn't match the signal kind (risk #11).
        IoTimeout
            If the adapter call times out.
        IoProtocolError
            On a protocol-level fault.
        """
        slot = self._connections.get(connection)
        if slot is None:
            raise KeyError(connection)
        # Check status before acquiring lock (risk #20).
        if slot.status != ConnectionStatusKind.OPEN:
            raise IoNotConnected(
                f"Connection {connection!r} is not open (status: {slot.status.value})"
            )
        sig = slot.signals.get(signal)
        if sig is None:
            raise IoUnknownSignal(f"Signal {signal!r} not found in connection {connection!r}")

        # Kind-mismatch check (risk #11).
        _check_kind_match(sig, value)

        async with slot.write_lock:
            # Re-check status inside lock — may have changed while waiting.
            if slot.status != ConnectionStatusKind.OPEN:
                raise IoNotConnected(
                    f"Connection {connection!r} closed while waiting for write lock"
                )
            event = await slot.adapter.write(sig, value)

        # Use the adapter's reported wire value (not the caller's input) for the ack.
        ack = IoEvent(
            connection=connection,
            kind="write_ack",
            signal=signal,
            value=event.value,
            monotonic_s=event.monotonic_s,
        )
        self._publish(ack)
        return ack

    async def wait_for_signal(
        self,
        connection: str,
        signal: str,
        predicate: Callable[[bool | int | float], bool],
        timeout_s: float | None = None,
    ) -> IoEvent:
        """Block until ``predicate(value)`` is true for ``signal``.

        Checks the cached last value first; if unsatisfied, polls the adapter
        at the signal's configured poll interval until the predicate passes or
        the timeout is reached.

        Raises
        ------
        KeyError
            If ``connection`` is not known.
        IoUnknownSignal
            If ``signal`` is not in the signal map.
        IoNotConnected
            If the connection is not ``open``.
        IoTimeout
            If ``timeout_s`` elapses before the predicate is satisfied.
        """
        slot = self._connections.get(connection)
        if slot is None:
            raise KeyError(connection)
        if slot.status != ConnectionStatusKind.OPEN:
            raise IoNotConnected(
                f"Connection {connection!r} is not open (status: {slot.status.value})"
            )
        sig = slot.signals.get(signal)
        if sig is None:
            raise IoUnknownSignal(f"Signal {signal!r} not found in connection {connection!r}")

        async def _poll() -> IoEvent:
            while True:
                # Check the live adapter value.
                event = await slot.adapter.read(sig)
                if event.value is not None and predicate(event.value):
                    return IoEvent(
                        connection=connection,
                        kind="value_changed",
                        signal=signal,
                        value=event.value,
                        monotonic_s=event.monotonic_s,
                    )
                poll_s = sig.poll_interval_s if sig.poll_interval_s is not None else 0.2
                await asyncio.sleep(poll_s)

        try:
            if timeout_s is not None:
                return await asyncio.wait_for(_poll(), timeout=timeout_s)
            return await _poll()
        except asyncio.TimeoutError as exc:
            raise IoTimeout(
                f"wait_for_signal({connection!r}, {signal!r}) timed out after {timeout_s} s"
            ) from exc

    # ------------------------------------------------------------------
    # Observation
    # ------------------------------------------------------------------

    def list_connections(self) -> list[_ConnectionSlot]:
        """Return a snapshot of all connection slots."""
        return list(self._connections.values())

    def get_connection(self, name: str) -> _ConnectionSlot:
        """Return the slot for ``name``.

        Raises
        ------
        KeyError
            If ``name`` is not a known connection.
        """
        if name not in self._connections:
            raise KeyError(name)
        return self._connections[name]

    def last_values(self) -> list[IoEvent]:
        """Return a snapshot of all cached last values."""
        with self._values_lock:
            return list(self._last_values.values())

    def last_values_for(self, connection: str) -> list[IoEvent]:
        """Return cached last values for one connection."""
        prefix = f"{connection}."
        with self._values_lock:
            return [v for k, v in self._last_values.items() if k.startswith(prefix)]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _check_kind_match(sig: SignalSpec, value: bool | int | float) -> None:
    """Raise :class:`IoSignalKindMismatch` if ``value`` is wrong for ``sig.kind``.

    Rules
    -----
    * Digital signals accept only ``bool`` (or ``int`` 0/1 as a bool alias).
    * Analog signals accept ``int`` or ``float``; ``bool`` is rejected because
      it is a subtype of ``int`` but signals incompatible intent.
    * ``digital_in`` and ``analog_in`` are read-only — writing to them is always
      a kind mismatch.
    """
    if sig.kind in (SignalKind.DIGITAL_IN, SignalKind.ANALOG_IN):
        raise IoSignalKindMismatch(
            f"Signal {sig.name!r} is read-only (kind={sig.kind.value}); cannot write"
        )
    if sig.kind == SignalKind.DIGITAL_OUT:
        if not isinstance(value, (bool, int)) or isinstance(value, float):
            raise IoSignalKindMismatch(
                f"Signal {sig.name!r} is digital_out; expected bool or int, "
                f"got {type(value).__name__!r}"
            )
    elif sig.kind == SignalKind.ANALOG_OUT:
        if isinstance(value, bool):
            raise IoSignalKindMismatch(
                f"Signal {sig.name!r} is analog_out; expected int or float, "
                f"got bool"
            )
        if not isinstance(value, (int, float)):
            raise IoSignalKindMismatch(
                f"Signal {sig.name!r} is analog_out; expected int or float, "
                f"got {type(value).__name__!r}"
            )
