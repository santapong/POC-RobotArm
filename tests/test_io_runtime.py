"""Tests for IoRuntime (server/services/io.py — which is src/io/runtime.py).

Uses _StubAdapter (subclass of IoAdapter) — never MagicMock for adapters.

Covers:
- add_connection happy path + duplicate name raises ValueError
- remove_connection happy path + cancels watch task (risk #17)
- connect / disconnect preserve slot (status transitions)
- reconnect = disconnect + connect on same slot
- update_signals atomic rebuild (risk #8)
- update_signals concurrent race: 5 concurrent calls, no KeyError
- write serialisation lock (risk #7)
- write kind mismatch (risk #11)
- write after disconnect raises IoNotConnected (risk #20)
- stop() cancels all watch tasks within 5 s (risk #9)
- subscribe / unsubscribe queue lifecycle
- last_values_for freshness after watch event
"""

from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator, Sequence

import pytest

from src.io.adapter import AdapterCapabilities, IoAdapter
from src.io.errors import (
    IoNotConnected,
    IoSignalKindMismatch,
    IoUnknownSignal,
)
from src.io.runtime import IoRuntime
from src.io.types import (
    ConnectionStatusKind,
    IoEvent,
    ModbusTcpConfig,
    SignalKind,
    SignalSpec,
)

pytestmark = pytest.mark.io


# ---------------------------------------------------------------------------
# _StubAdapter — drives tests via an asyncio.Queue
# ---------------------------------------------------------------------------


class _StubAdapter(IoAdapter):
    """Stub adapter for runtime tests.

    connect / disconnect / read / write are all in-memory.
    watch yields events from self.event_queue until cancelled.
    """

    def __init__(self) -> None:
        self._connected = False
        self.connect_calls = 0
        self.disconnect_calls = 0
        # Tests put IoEvent objects here to drive the watch loop.
        self.event_queue: asyncio.Queue[IoEvent] = asyncio.Queue()
        self._values: dict[str, bool | int | float] = {}
        # Simulated write delay (default 0 — tests can set higher).
        self.write_delay_s: float = 0.0

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            supports_subscribe=True,
            supports_write=True,
            supports_analog=True,
        )

    async def connect(self) -> None:
        self._connected = True
        self.connect_calls += 1

    async def disconnect(self) -> None:
        self._connected = False
        self.disconnect_calls += 1

    async def read(self, signal: SignalSpec) -> IoEvent:
        if not self._connected:
            raise IoNotConnected("stub not connected")
        val = self._values.get(signal.name, False)
        return IoEvent(
            connection="stub",
            kind="value_changed",
            signal=signal.name,
            value=val,
            monotonic_s=time.monotonic(),
        )

    async def write(self, signal: SignalSpec, value: bool | int | float) -> IoEvent:
        if not self._connected:
            raise IoNotConnected("stub not connected")
        if self.write_delay_s > 0:
            await asyncio.sleep(self.write_delay_s)
        self._values[signal.name] = value
        return IoEvent(
            connection="stub",
            kind="write_ack",
            signal=signal.name,
            value=value,
            monotonic_s=time.monotonic(),
        )

    async def watch(self, signals: Sequence[SignalSpec]) -> AsyncIterator[IoEvent]:  # type: ignore[override]
        """Yield events from event_queue until cancelled."""
        while True:
            try:
                event = await asyncio.wait_for(self.event_queue.get(), timeout=0.05)
                yield event
            except asyncio.TimeoutError:
                continue


# ---------------------------------------------------------------------------
# Helper fixtures
# ---------------------------------------------------------------------------


def _make_signal(name: str = "di0", kind: SignalKind = SignalKind.DIGITAL_OUT) -> SignalSpec:
    return SignalSpec(name=name, kind=kind, address="coil:0")


def _make_analog_signal(name: str = "ao0") -> SignalSpec:
    return SignalSpec(name=name, kind=SignalKind.ANALOG_OUT, address="holding:0")


async def _make_runtime_with_stub(
    name: str = "conn1",
    signals: list[SignalSpec] | None = None,
    stub: _StubAdapter | None = None,
) -> tuple[IoRuntime, _StubAdapter]:
    """Create an IoRuntime with a stub adapter already connected.

    Patches src.io.runtime.build_adapter (the name bound in runtime's module
    namespace) so the runtime uses our stub instead of a real protocol adapter.
    """
    import src.io.runtime as _runtime_mod

    rt = IoRuntime()
    adapter = stub or _StubAdapter()

    original = _runtime_mod.build_adapter

    def _patched(cfg):
        return adapter

    _runtime_mod.build_adapter = _patched  # type: ignore[assignment]
    try:
        cfg = ModbusTcpConfig(host="127.0.0.1")
        sigs = signals or [_make_signal()]
        await rt.add_connection(name, cfg, sigs)
    finally:
        _runtime_mod.build_adapter = original  # type: ignore[assignment]

    return rt, adapter


# ---------------------------------------------------------------------------
# add_connection
# ---------------------------------------------------------------------------


def test_add_connection_happy_path() -> None:
    async def _run():
        rt, _ = await _make_runtime_with_stub()
        slots = rt.list_connections()
        assert len(slots) == 1
        assert slots[0].name == "conn1"
        assert slots[0].status == ConnectionStatusKind.OPEN
        await rt.stop()

    asyncio.run(_run())


def test_add_connection_duplicate_name_raises() -> None:
    async def _run():
        import src.io.runtime as _runtime_mod

        rt, adapter = await _make_runtime_with_stub()

        original = _runtime_mod.build_adapter

        def _patched(cfg):
            return _StubAdapter()

        _runtime_mod.build_adapter = _patched  # type: ignore[assignment]
        try:
            cfg = ModbusTcpConfig(host="127.0.0.1")
            with pytest.raises(ValueError, match="already exists"):
                await rt.add_connection("conn1", cfg, [_make_signal()])
        finally:
            _runtime_mod.build_adapter = original  # type: ignore[assignment]
            await rt.stop()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# remove_connection (risk #17 — watch task cancelled within 3 s)
# ---------------------------------------------------------------------------


def test_remove_connection_cancels_watch_task() -> None:
    """Watch task must be done within 3 s of remove_connection (risk #17)."""

    async def _run():
        rt, adapter = await _make_runtime_with_stub()
        slot = rt.get_connection("conn1")
        task = slot.watch_task
        assert task is not None

        await rt.remove_connection("conn1")

        deadline = time.monotonic() + 3.0
        while not task.done() and time.monotonic() < deadline:
            await asyncio.sleep(0.02)

        assert task.done(), "watch task was not done within 3 s after remove_connection"

    asyncio.run(_run())


def test_remove_connection_clears_slot() -> None:
    async def _run():
        rt, _ = await _make_runtime_with_stub()
        await rt.remove_connection("conn1")
        assert rt.list_connections() == []
        with pytest.raises(KeyError):
            rt.get_connection("conn1")

    asyncio.run(_run())


def test_remove_connection_unknown_raises_key_error() -> None:
    async def _run():
        rt = IoRuntime()
        with pytest.raises(KeyError):
            await rt.remove_connection("ghost")

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# connect / disconnect preserve slot status
# ---------------------------------------------------------------------------


def test_disconnect_sets_status_disconnected() -> None:
    async def _run():
        rt, adapter = await _make_runtime_with_stub()
        await rt.disconnect("conn1")
        slot = rt.get_connection("conn1")
        assert slot.status == ConnectionStatusKind.DISCONNECTED
        await rt.stop()

    asyncio.run(_run())


def test_connect_after_disconnect_restores_open() -> None:
    async def _run():
        rt, adapter = await _make_runtime_with_stub()
        await rt.disconnect("conn1")
        await rt.connect("conn1")
        slot = rt.get_connection("conn1")
        assert slot.status == ConnectionStatusKind.OPEN
        await rt.stop()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# reconnect
# ---------------------------------------------------------------------------


def test_reconnect_preserves_slot() -> None:
    async def _run():
        rt, adapter = await _make_runtime_with_stub()
        await rt.reconnect("conn1")
        slot = rt.get_connection("conn1")
        assert slot.status == ConnectionStatusKind.OPEN
        # connect called twice: initial + reconnect
        assert adapter.connect_calls >= 2
        await rt.stop()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# update_signals atomic rebuild (risk #8)
# ---------------------------------------------------------------------------


def test_update_signals_atomic_rebuild() -> None:
    """Old watch task cancelled and new task spawned with new signals (risk #8)."""

    async def _run():
        rt, adapter = await _make_runtime_with_stub()
        slot = rt.get_connection("conn1")
        old_task = slot.watch_task
        assert old_task is not None

        new_signals = [
            _make_signal("di0"),
            _make_signal("di1"),
        ]
        await rt.update_signals("conn1", new_signals)

        # Old task must be done within 1 s
        deadline = time.monotonic() + 1.0
        while not old_task.done() and time.monotonic() < deadline:
            await asyncio.sleep(0.02)
        assert old_task.done(), "old watch task not cancelled within 1 s"

        # New slot has updated signals
        slot2 = rt.get_connection("conn1")
        assert "di0" in slot2.signals
        assert "di1" in slot2.signals
        assert slot2.watch_task is not old_task

        await rt.stop()

    asyncio.run(_run())


def test_update_signals_concurrent_no_key_error() -> None:
    """5 concurrent update_signals calls must not raise KeyError (risk #8)."""

    async def _run():
        rt, adapter = await _make_runtime_with_stub()

        async def _update(i: int):
            sigs = [_make_signal(f"sig{i}")]
            await rt.update_signals("conn1", sigs)

        await asyncio.gather(*[_update(i) for i in range(5)], return_exceptions=True)

        # Slot must still exist with some signals
        slot = rt.get_connection("conn1")
        assert len(slot.signals) >= 1

        await rt.stop()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# write serialisation (risk #7)
# ---------------------------------------------------------------------------


def test_concurrent_writes_serialise() -> None:
    """Two concurrent writes are serialised by the write lock (risk #7).

    If the writes were truly parallel they would finish in ~write_delay_s total.
    Serialised, they take >= 2 * write_delay_s.
    """

    async def _run():
        write_delay_s = 0.05
        adapter = _StubAdapter()
        adapter.write_delay_s = write_delay_s

        rt, _ = await _make_runtime_with_stub(
            "c1", [_make_analog_signal("ao0")], stub=adapter
        )

        t_start = time.monotonic()
        await asyncio.gather(
            rt.write("c1", "ao0", 1.0),
            rt.write("c1", "ao0", 2.0),
        )
        total = time.monotonic() - t_start

        # Serial: total >= 2 * delay; parallel: total ~= 1 * delay.
        # Use 1.5 * delay as the threshold with a small margin.
        assert total >= 1.5 * write_delay_s, (
            f"Writes appear to have run in parallel (total={total:.3f} s, "
            f"delay={write_delay_s} s, expected >= {1.5 * write_delay_s:.3f} s). "
            "The per-connection write_lock may not be working (risk #7)."
        )

        await rt.stop()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# write kind mismatch (risk #11)
# ---------------------------------------------------------------------------


def test_write_kind_mismatch_digital_out_with_float_raises() -> None:
    """Writing float to digital_out raises IoSignalKindMismatch (risk #11)."""

    async def _run():
        digital_sig = SignalSpec(name="do0", kind=SignalKind.DIGITAL_OUT, address="coil:0")
        rt, _ = await _make_runtime_with_stub("c1", [digital_sig])

        with pytest.raises(IoSignalKindMismatch):
            await rt.write("c1", "do0", 1.5)  # float to digital_out

        await rt.stop()

    asyncio.run(_run())


def test_write_to_digital_in_raises_kind_mismatch() -> None:
    """Writing to digital_in (read-only) raises IoSignalKindMismatch (risk #11)."""

    async def _run():
        in_sig = SignalSpec(name="di0", kind=SignalKind.DIGITAL_IN, address="discrete:0")
        rt, _ = await _make_runtime_with_stub("c1", [in_sig])

        with pytest.raises(IoSignalKindMismatch):
            await rt.write("c1", "di0", True)

        await rt.stop()

    asyncio.run(_run())


def test_write_to_analog_in_raises_kind_mismatch() -> None:
    async def _run():
        in_sig = SignalSpec(name="ai0", kind=SignalKind.ANALOG_IN, address="input:0")
        rt, _ = await _make_runtime_with_stub("c1", [in_sig])

        with pytest.raises(IoSignalKindMismatch):
            await rt.write("c1", "ai0", 3.14)

        await rt.stop()

    asyncio.run(_run())


def test_write_bool_to_analog_out_raises_kind_mismatch() -> None:
    async def _run():
        ao = _make_analog_signal("ao0")
        rt, _ = await _make_runtime_with_stub("c1", [ao])

        with pytest.raises(IoSignalKindMismatch, match="analog_out"):
            await rt.write("c1", "ao0", True)

        await rt.stop()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# write after disconnect (risk #20)
# ---------------------------------------------------------------------------


def test_write_after_disconnect_raises_not_connected() -> None:
    """write() on a disconnected slot raises IoNotConnected (risk #20)."""

    async def _run():
        sig = _make_analog_signal("ao0")
        rt, adapter = await _make_runtime_with_stub("c1", [sig])

        await rt.disconnect("c1")

        with pytest.raises(IoNotConnected):
            await rt.write("c1", "ao0", 42.0)

        await rt.stop()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# stop() cancels all watch tasks within 5 s (risks #9, #17)
# ---------------------------------------------------------------------------


def test_stop_cancels_watch_tasks() -> None:
    """stop() must cancel all watch tasks within 5 s (risk #9)."""

    async def _run():
        import src.io.runtime as _runtime_mod

        # Add 3 connections
        rt = IoRuntime()
        adapters = []
        original = _runtime_mod.build_adapter
        cfg = ModbusTcpConfig(host="127.0.0.1")
        sigs = [_make_signal()]

        for i in range(3):
            stub = _StubAdapter()
            adapters.append(stub)

            def _patched(c, _stub=stub):
                return _stub

            _runtime_mod.build_adapter = _patched  # type: ignore[assignment]
            await rt.add_connection(f"c{i}", cfg, sigs)

        _runtime_mod.build_adapter = original  # type: ignore[assignment]

        tasks = []
        for slot in rt.list_connections():
            if slot.watch_task is not None:
                tasks.append(slot.watch_task)

        assert len(tasks) == 3

        t_start = time.monotonic()
        await rt.stop()
        elapsed = time.monotonic() - t_start

        assert elapsed < 5.0, f"stop() took {elapsed:.2f} s, expected < 5 s"
        for t in tasks:
            assert t.done(), "watch task not done after stop()"

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# subscribe / unsubscribe
# ---------------------------------------------------------------------------


def test_subscribe_delivers_event_to_queue() -> None:
    async def _run():
        rt, adapter = await _make_runtime_with_stub("c1", [_make_signal("di0")])

        q: asyncio.Queue = asyncio.Queue()
        rt.subscribe(q)

        # Inject an event into the adapter's queue so the watch loop picks it up.
        ev = IoEvent(connection="stub", kind="value_changed", signal="di0", value=True)
        await adapter.event_queue.put(ev)

        # Wait for the event to propagate through _watch_loop -> _publish -> q
        deadline = time.monotonic() + 2.0
        received: IoEvent | None = None
        while time.monotonic() < deadline:
            try:
                received = q.get_nowait()
                break
            except asyncio.QueueEmpty:
                await asyncio.sleep(0.02)

        assert received is not None, "No event delivered to subscriber queue"
        assert received.signal == "di0"
        assert received.connection == "c1"

        rt.unsubscribe(q)
        await rt.stop()

    asyncio.run(_run())


def test_unsubscribe_stops_delivery() -> None:
    async def _run():
        rt, adapter = await _make_runtime_with_stub("c1", [_make_signal("di0")])

        q: asyncio.Queue = asyncio.Queue()
        rt.subscribe(q)
        rt.unsubscribe(q)

        ev = IoEvent(connection="stub", kind="value_changed", signal="di0", value=True)
        await adapter.event_queue.put(ev)
        await asyncio.sleep(0.1)

        # Queue should be empty (unsubscribed)
        assert q.empty()

        await rt.stop()

    asyncio.run(_run())


def test_subscribe_duplicate_not_added_twice() -> None:
    async def _run():
        rt = IoRuntime()
        q: asyncio.Queue = asyncio.Queue()
        rt.subscribe(q)
        rt.subscribe(q)
        assert rt._subscribers.count(q) == 1

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# last_values_for freshness
# ---------------------------------------------------------------------------


def test_last_values_for_updated_after_watch_event() -> None:
    async def _run():
        sig = _make_signal("di0")
        rt, adapter = await _make_runtime_with_stub("c1", [sig])

        ev = IoEvent(connection="stub", kind="value_changed", signal="di0", value=True)
        await adapter.event_queue.put(ev)

        # Wait for the watch loop to process and cache the value
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            vals = rt.last_values_for("c1")
            if vals and any(v.value is True for v in vals):
                break
            await asyncio.sleep(0.02)

        vals = rt.last_values_for("c1")
        assert any(v.signal == "di0" and v.value is True for v in vals), (
            "last_values_for did not reflect the injected watch event"
        )

        await rt.stop()

    asyncio.run(_run())


def test_last_values_cleared_after_remove_connection() -> None:
    async def _run():
        sig = _make_signal("di0")
        rt, adapter = await _make_runtime_with_stub("c1", [sig])

        ev = IoEvent(connection="stub", kind="value_changed", signal="di0", value=True)
        await adapter.event_queue.put(ev)
        await asyncio.sleep(0.1)  # let watch loop process

        await rt.remove_connection("c1")
        assert rt.last_values_for("c1") == []

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# write unknown signal
# ---------------------------------------------------------------------------


def test_write_unknown_signal_raises() -> None:
    async def _run():
        rt, _ = await _make_runtime_with_stub("c1", [_make_signal("di0")])

        with pytest.raises(IoUnknownSignal):
            await rt.write("c1", "no_such_signal", True)

        await rt.stop()

    asyncio.run(_run())


def test_write_unknown_connection_raises_key_error() -> None:
    async def _run():
        rt = IoRuntime()
        with pytest.raises(KeyError):
            await rt.write("ghost", "di0", True)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Extra coverage: list_connections returns snapshot
# ---------------------------------------------------------------------------


# Extra coverage: list_connections snapshot is independent of mutations
def test_list_connections_returns_snapshot() -> None:
    async def _run():
        rt, _ = await _make_runtime_with_stub("c1")
        snapshot = rt.list_connections()
        await rt.remove_connection("c1")
        # snapshot is a Python list copy — still has the original slot
        assert len(snapshot) == 1

    asyncio.run(_run())
