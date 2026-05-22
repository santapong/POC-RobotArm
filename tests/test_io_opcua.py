"""Tests for OpcUaAdapter + opcua_sim.

Gates: pytest.importorskip("asyncua")

Covers:
- connect + write + read node round-trip
- _parse_opcua_address for all 4 address formats
- write to read-only node yields IoProtocolError (risk #5)
- watch yields value_changed events via subscription
"""

from __future__ import annotations

import asyncio
import time

import pytest

asyncua = pytest.importorskip("asyncua")

pytestmark = pytest.mark.io

from src.io.adapters.opcua import OpcUaAdapter  # noqa: E402
from src.io.errors import IoConnectionError, IoNotConnected, IoProtocolError  # noqa: E402
from src.io.simulators.opcua_sim import find_free_port, start_opcua_server  # noqa: E402
from src.io.types import OpcUaConfig, SignalKind, SignalSpec  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bool_signal(name: str = "part_present", addr: str = "i=2") -> SignalSpec:
    return SignalSpec(name=name, kind=SignalKind.DIGITAL_IN, address=addr)


def _bool_out(name: str = "relay", addr: str = "i=2") -> SignalSpec:
    return SignalSpec(name=name, kind=SignalKind.DIGITAL_OUT, address=addr)


# ---------------------------------------------------------------------------
# _parse_opcua_address — all 4 formats
# ---------------------------------------------------------------------------


def test_parse_opcua_address_numeric() -> None:
    cfg = OpcUaConfig(url="opc.tcp://localhost:4840", namespace=2)
    adapter = OpcUaAdapter(cfg)
    ns, ident = adapter._parse_opcua_address("i=42")
    assert ns == 2
    assert ident == 42


def test_parse_opcua_address_ns_numeric() -> None:
    cfg = OpcUaConfig(url="opc.tcp://localhost:4840", namespace=2)
    adapter = OpcUaAdapter(cfg)
    ns, ident = adapter._parse_opcua_address("ns=3;i=7")
    assert ns == 3
    assert ident == 7


def test_parse_opcua_address_string() -> None:
    cfg = OpcUaConfig(url="opc.tcp://localhost:4840", namespace=2)
    adapter = OpcUaAdapter(cfg)
    ns, ident = adapter._parse_opcua_address("s=MyVar")
    assert ns == 2
    assert ident == "MyVar"


def test_parse_opcua_address_ns_string() -> None:
    cfg = OpcUaConfig(url="opc.tcp://localhost:4840", namespace=2)
    adapter = OpcUaAdapter(cfg)
    ns, ident = adapter._parse_opcua_address("ns=5;s=SomeTag")
    assert ns == 5
    assert ident == "SomeTag"


def test_parse_opcua_address_missing_equals_raises() -> None:
    cfg = OpcUaConfig(url="opc.tcp://localhost:4840")
    adapter = OpcUaAdapter(cfg)
    with pytest.raises(ValueError, match="'i=' or 's='"):
        adapter._parse_opcua_address("nope")


def test_parse_opcua_address_unknown_kind_raises() -> None:
    cfg = OpcUaConfig(url="opc.tcp://localhost:4840")
    adapter = OpcUaAdapter(cfg)
    with pytest.raises(ValueError, match="kind must be 'i'"):
        adapter._parse_opcua_address("x=5")


# ---------------------------------------------------------------------------
# connect + write + read node round-trip
# ---------------------------------------------------------------------------


def test_opcua_connect_write_read_round_trip() -> None:
    async def _run():
        async with start_opcua_server() as (url, server):
            # The sim seeds a writable boolean node at ns=idx, numeric id=2
            # Discover the actual namespace index
            ns_idx = await server.get_namespace_index("http://poc-robotarm/ns2")
            cfg = OpcUaConfig(url=url, namespace=ns_idx, timeout_s=10.0)
            adapter = OpcUaAdapter(cfg)
            await adapter.connect()

            sig = SignalSpec(name="part_present", kind=SignalKind.DIGITAL_OUT, address="i=2")
            ev = await adapter.write(sig, True)
            assert ev.kind == "write_ack"
            assert ev.signal == "part_present"

            read_sig = SignalSpec(name="part_present", kind=SignalKind.DIGITAL_IN, address="i=2")
            ev2 = await adapter.read(read_sig)
            assert ev2.kind == "value_changed"
            assert ev2.value is True

            await adapter.disconnect()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Risk #5 — write to read-only node yields IoProtocolError
# ---------------------------------------------------------------------------


def test_write_readonly_node_yields_protocol_error() -> None:
    """Writing to a read-only node raises IoProtocolError (risk #5)."""

    async def _run():
        async with start_opcua_server() as (url, server):
            ns_idx = await server.get_namespace_index("http://poc-robotarm/ns2")

            # Add a read-only variable (not set_writable)
            objects = server.get_objects_node()
            readonly_node = await objects.add_variable(
                ns_idx, "readonly_flag", False
            )
            # Do NOT call set_writable() — default is read-only in asyncua

            cfg = OpcUaConfig(url=url, namespace=ns_idx, timeout_s=10.0)
            adapter = OpcUaAdapter(cfg)
            await adapter.connect()

            node_id = readonly_node.nodeid
            addr = f"i={node_id.Identifier}"
            sig = SignalSpec(name="readonly_flag", kind=SignalKind.DIGITAL_OUT, address=addr)

            with pytest.raises(IoProtocolError):
                await adapter.write(sig, True)

            await adapter.disconnect()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Connect to wrong URL raises IoConnectionError
# ---------------------------------------------------------------------------


def test_opcua_connect_wrong_url_raises_connection_error() -> None:
    async def _run():
        port = find_free_port()
        cfg = OpcUaConfig(url=f"opc.tcp://127.0.0.1:{port}/nothing/", timeout_s=3.0)
        adapter = OpcUaAdapter(cfg)
        t0 = time.monotonic()
        with pytest.raises(IoConnectionError):
            await adapter.connect()
        elapsed = time.monotonic() - t0
        # Should fail within 10 s (OPC-UA handshake can be slow)
        assert elapsed < 10.0

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# read / write not connected
# ---------------------------------------------------------------------------


def test_opcua_read_not_connected_raises() -> None:
    async def _run():
        cfg = OpcUaConfig(url="opc.tcp://localhost:4840")
        adapter = OpcUaAdapter(cfg)
        sig = _bool_signal()
        with pytest.raises(IoNotConnected):
            await adapter.read(sig)

    asyncio.run(_run())


def test_opcua_write_not_connected_raises() -> None:
    async def _run():
        cfg = OpcUaConfig(url="opc.tcp://localhost:4840")
        adapter = OpcUaAdapter(cfg)
        sig = _bool_out()
        with pytest.raises(IoNotConnected):
            await adapter.write(sig, True)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


def test_opcua_capabilities() -> None:
    cfg = OpcUaConfig(url="opc.tcp://localhost:4840")
    adapter = OpcUaAdapter(cfg)
    caps = adapter.capabilities
    assert caps.supports_subscribe is True
    assert caps.supports_write is True
    assert caps.supports_analog is True


# ---------------------------------------------------------------------------
# watch() yields value_changed events via subscription
# ---------------------------------------------------------------------------


def test_opcua_watch_yields_event_on_node_change() -> None:
    async def _run():
        async with start_opcua_server() as (url, server):
            ns_idx = await server.get_namespace_index("http://poc-robotarm/ns2")
            cfg = OpcUaConfig(url=url, namespace=ns_idx, timeout_s=10.0)
            adapter = OpcUaAdapter(cfg)
            await adapter.connect()

            sig = SignalSpec(
                name="part_present",
                kind=SignalKind.DIGITAL_IN,
                address="i=2",
            )

            events: list = []

            async def _watch():
                async for ev in adapter.watch([sig]):
                    events.append(ev)
                    return  # stop after first event

            watch_task = asyncio.create_task(_watch())

            # Allow subscription to establish
            await asyncio.sleep(0.5)

            # Write server-side to trigger the subscription callback
            objects = server.get_objects_node()
            children = await objects.get_children()
            for child in children:
                bn = await child.read_browse_name()
                if bn.Name == "part_present":
                    await child.write_value(True)
                    break

            deadline = time.monotonic() + 5.0
            while not events and time.monotonic() < deadline:
                await asyncio.sleep(0.05)

            watch_task.cancel()
            try:
                await watch_task
            except (asyncio.CancelledError, Exception):
                pass

            assert events, "watch() did not yield a value_changed event after node write"
            assert events[0].kind == "value_changed"

            await adapter.disconnect()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Extra coverage: disconnect is idempotent
# ---------------------------------------------------------------------------


# Extra coverage: double disconnect must not raise
def test_opcua_disconnect_idempotent() -> None:
    async def _run():
        cfg = OpcUaConfig(url="opc.tcp://localhost:4840")
        adapter = OpcUaAdapter(cfg)
        await adapter.disconnect()
        await adapter.disconnect()

    asyncio.run(_run())
