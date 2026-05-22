"""Tests for ModbusTcpAdapter + modbus_tcp_sim.

Gates: pytest.importorskip("pymodbus").

Covers:
- pymodbus version assertion (risk #1)
- connect + write + read coil round-trip
- watch() yields value_changed event after server-side coil change
- Connect to wrong port raises IoConnectionError in < 2 s (risk #12)
- Write analog (float) to digital_out raises IoSignalKindMismatch (risk #11)
"""

from __future__ import annotations

import asyncio
import time

import pytest

pymodbus = pytest.importorskip("pymodbus")

from src.io.adapters.modbus_tcp import ModbusTcpAdapter  # noqa: E402
from src.io.errors import IoConnectionError, IoNotConnected, IoSignalKindMismatch  # noqa: E402
from src.io.simulators.modbus_tcp_sim import find_free_port, start_modbus_tcp_server  # noqa: E402
from src.io.types import IoEvent, ModbusTcpConfig, SignalKind, SignalSpec  # noqa: E402

pytestmark = pytest.mark.io


# ---------------------------------------------------------------------------
# Risk #1 — pymodbus version
# ---------------------------------------------------------------------------


def test_pymodbus_version() -> None:
    """pymodbus must be >= 3.7 (risk #1)."""
    ver = pymodbus.__version__
    # Accept 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 3.13 — but not 4.x
    major, minor = (int(x) for x in ver.split(".")[:2])
    assert major == 3 and minor >= 7, (
        f"pymodbus version {ver!r} does not satisfy >=3.7,<4. "
        "Risk #1: API breakage between major versions."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _digital_out(name: str = "do0", addr: str = "coil:0") -> SignalSpec:
    return SignalSpec(name=name, kind=SignalKind.DIGITAL_OUT, address=addr)


def _analog_out(name: str = "ao0", addr: str = "holding:0") -> SignalSpec:
    return SignalSpec(name=name, kind=SignalKind.ANALOG_OUT, address=addr)


def _digital_in(name: str = "di0", addr: str = "discrete:0") -> SignalSpec:
    return SignalSpec(name=name, kind=SignalKind.DIGITAL_IN, address=addr)


# ---------------------------------------------------------------------------
# Connect + write + read round-trip
# ---------------------------------------------------------------------------


def test_connect_write_read_coil_round_trip() -> None:
    async def _run():
        port = find_free_port()
        async with start_modbus_tcp_server(host="127.0.0.1", port=port) as (host, p, ctx):
            cfg = ModbusTcpConfig(host=host, port=p, timeout_s=5.0)
            adapter = ModbusTcpAdapter(cfg)
            await adapter.connect()

            sig = _digital_out("do0", "coil:0")
            # Write True to coil 0
            ev = await adapter.write(sig, True)
            assert ev.kind == "write_ack"
            assert ev.signal == "do0"

            # Read it back — should be True (coil written = True)
            # Use holding register path for a read round-trip separately
            coil_sig = SignalSpec(name="do0", kind=SignalKind.DIGITAL_IN, address="coil:0")
            ev2 = await adapter.read(coil_sig)
            assert ev2.kind == "value_changed"
            assert ev2.value is True

            await adapter.disconnect()

    asyncio.run(_run())


def test_connect_write_holding_register_round_trip() -> None:
    async def _run():
        port = find_free_port()
        async with start_modbus_tcp_server(host="127.0.0.1", port=port) as (host, p, ctx):
            cfg = ModbusTcpConfig(host=host, port=p, timeout_s=5.0)
            adapter = ModbusTcpAdapter(cfg)
            await adapter.connect()

            # Write to holding register 0
            sig = _analog_out("ao0", "holding:0")
            await adapter.write(sig, 1234)

            # Read back via input register (not available from holding in pymodbus sim)
            # Instead verify via holding read
            hold_sig = SignalSpec(name="ao0", kind=SignalKind.ANALOG_OUT, address="holding:0")
            ev = await adapter.read(hold_sig)
            assert ev.kind == "value_changed"
            assert ev.value == 1234

            await adapter.disconnect()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# watch() yields value_changed event after server-side coil change
# ---------------------------------------------------------------------------


def test_watch_yields_value_changed_on_coil_flip() -> None:
    async def _run():
        port = find_free_port()
        async with start_modbus_tcp_server(host="127.0.0.1", port=port) as (host, p, ctx):
            cfg = ModbusTcpConfig(host=host, port=p, timeout_s=5.0)
            adapter = ModbusTcpAdapter(cfg)
            await adapter.connect()

            sig = SignalSpec(name="di0", kind=SignalKind.DIGITAL_IN, address="coil:0",
                             poll_interval_s=0.1)

            events: list[IoEvent] = []
            watch_task: asyncio.Task | None = None

            async def _watch():
                async for ev in adapter.watch([sig]):
                    events.append(ev)
                    if len(events) >= 1:
                        return

            watch_task = asyncio.create_task(_watch())

            # Flip the coil on the server side
            await asyncio.sleep(0.15)
            ctx.slaves().setValues(1, 0, [True])  # function code 1 = coils

            # Wait up to 3 s for a value_changed event
            deadline = time.monotonic() + 3.0
            while not events and time.monotonic() < deadline:
                await asyncio.sleep(0.05)

            watch_task.cancel()
            try:
                await watch_task
            except (asyncio.CancelledError, Exception):
                pass

            assert events, "No value_changed event received from watch()"
            assert events[0].kind == "value_changed"

            await adapter.disconnect()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Risk #12 — connect to wrong port raises IoConnectionError in < 2 s
# ---------------------------------------------------------------------------


def test_connect_wrong_port_raises_connection_error_in_under_2s() -> None:
    """Connecting to a non-listening port must raise IoConnectionError quickly (risk #12)."""

    async def _run():
        # Use a port nothing is listening on (find a free port then don't bind it)
        port = find_free_port()
        cfg = ModbusTcpConfig(host="127.0.0.1", port=port, timeout_s=1.5)
        adapter = ModbusTcpAdapter(cfg)

        t0 = time.monotonic()
        with pytest.raises(IoConnectionError):
            await adapter.connect()
        elapsed = time.monotonic() - t0

        assert elapsed < 2.0, (
            f"connect() to wrong port took {elapsed:.2f} s; expected < 2 s (risk #12)"
        )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Risk #11 — write analog value to digital_out raises IoSignalKindMismatch
# (tested at the adapter level using _check_kind_match indirectly via runtime,
#  and at the direct adapter level which does NOT check kind — IoRuntime does;
#  so we test via IoRuntime here too for completeness)
# ---------------------------------------------------------------------------


def test_write_analog_to_digital_via_runtime_raises_kind_mismatch() -> None:
    """Full-path test: IoRuntime.write float to digital_out raises IoSignalKindMismatch."""
    import src.io.runtime as _runtime_mod
    from src.io.runtime import IoRuntime

    async def _run():
        port = find_free_port()
        async with start_modbus_tcp_server(host="127.0.0.1", port=port) as (host, p, ctx):
            cfg = ModbusTcpConfig(host=host, port=p, timeout_s=5.0)
            rt = IoRuntime()
            original = _runtime_mod.build_adapter

            def _patched(c):
                return ModbusTcpAdapter(cfg)

            _runtime_mod.build_adapter = _patched  # type: ignore[assignment]
            try:
                sigs = [SignalSpec(name="do0", kind=SignalKind.DIGITAL_OUT, address="coil:0")]
                await rt.add_connection("c", cfg, sigs)
                with pytest.raises(IoSignalKindMismatch):
                    await rt.write("c", "do0", 1.5)
            finally:
                _runtime_mod.build_adapter = original  # type: ignore[assignment]
                await rt.stop()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# read / write when not connected
# ---------------------------------------------------------------------------


def test_read_when_not_connected_raises() -> None:
    async def _run():
        cfg = ModbusTcpConfig(host="127.0.0.1", port=502)
        adapter = ModbusTcpAdapter(cfg)
        sig = _digital_out()
        with pytest.raises(IoNotConnected):
            await adapter.read(sig)

    asyncio.run(_run())


def test_write_when_not_connected_raises() -> None:
    async def _run():
        cfg = ModbusTcpConfig(host="127.0.0.1", port=502)
        adapter = ModbusTcpAdapter(cfg)
        sig = _digital_out()
        with pytest.raises(IoNotConnected):
            await adapter.write(sig, True)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


def test_modbus_tcp_capabilities() -> None:
    cfg = ModbusTcpConfig(host="127.0.0.1")
    adapter = ModbusTcpAdapter(cfg)
    caps = adapter.capabilities
    assert caps.supports_subscribe is False  # Modbus is poll-only
    assert caps.supports_write is True
    assert caps.supports_analog is True


# ---------------------------------------------------------------------------
# Extra coverage: _parse_address validation
# ---------------------------------------------------------------------------


# Extra coverage: ensure _parse_address rejects bad formats
def test_parse_address_bad_format_raises() -> None:
    from src.io.adapters.modbus_tcp import _parse_address

    with pytest.raises(ValueError, match="Modbus address must be"):
        _parse_address("no_colon")


def test_parse_address_unknown_register_type_raises() -> None:
    from src.io.adapters.modbus_tcp import _parse_address

    with pytest.raises(ValueError, match="register type must be"):
        _parse_address("gpio:0")


def test_parse_address_negative_index_raises() -> None:
    from src.io.adapters.modbus_tcp import _parse_address

    with pytest.raises(ValueError, match="register index must be >= 0"):
        _parse_address("coil:-1")
