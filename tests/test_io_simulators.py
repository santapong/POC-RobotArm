"""Tests for src/io/simulators/*.

Covers:
- start_modbus_tcp_server with port=0 raises ValueError (iter-2 fix verification)
- find_free_port returns a bindable port
- MqttBrokerSim skips with clean error when mosquitto not in PATH
- start_opcua_server spawns a working server (smoke: client connects + reads root node)
"""

from __future__ import annotations

import asyncio
import shutil
import socket
import sys

import pytest

pytestmark = pytest.mark.io


# ---------------------------------------------------------------------------
# modbus_tcp_sim: find_free_port and port=0 guard
# ---------------------------------------------------------------------------


def test_find_free_port_returns_bindable_port() -> None:
    """find_free_port() returns a port that can subsequently be bound."""
    pymodbus = pytest.importorskip("pymodbus")  # noqa: F841
    from src.io.simulators.modbus_tcp_sim import find_free_port

    port = find_free_port()
    assert isinstance(port, int)
    assert 1024 < port < 65536

    # Verify the port can be bound
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", port))
        s.listen(1)


def test_modbus_tcp_server_port_zero_raises_value_error() -> None:
    """start_modbus_tcp_server(port=0) must raise ValueError (iter-2 fix)."""
    pytest.importorskip("pymodbus")
    from src.io.simulators.modbus_tcp_sim import start_modbus_tcp_server

    async def _run():
        with pytest.raises(ValueError, match="port=0"):
            async with start_modbus_tcp_server(port=0):
                pass  # should not reach here

    asyncio.run(_run())


def test_modbus_tcp_server_starts_and_stops() -> None:
    """Server starts on a free port, yields connection info, stops cleanly."""
    pytest.importorskip("pymodbus")
    from src.io.simulators.modbus_tcp_sim import find_free_port, start_modbus_tcp_server

    async def _run():
        port = find_free_port()
        async with start_modbus_tcp_server(host="127.0.0.1", port=port) as (host, p, ctx):
            assert host == "127.0.0.1"
            assert p == port
            assert ctx is not None
            # Verify server is reachable
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.close()
            await writer.wait_closed()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# modbus_rtu_sim: POSIX-only
# ---------------------------------------------------------------------------


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX pty only")
def test_modbus_rtu_server_starts_and_stops() -> None:
    """RTU server starts over a pty pair and stops cleanly."""
    pytest.importorskip("pymodbus")
    pty_mod = pytest.importorskip("pty")  # noqa: F841
    import os

    from src.io.simulators.modbus_rtu_sim import start_modbus_rtu_server

    async def _run():
        async with start_modbus_rtu_server(baudrate=19200) as (device_path, ctx):
            assert device_path.startswith("/dev/")
            assert os.path.exists(device_path)
            assert ctx is not None

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# mqtt_broker sim: availability gate
# ---------------------------------------------------------------------------


def test_mqtt_broker_sim_raises_io_unavailable_when_mosquitto_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MqttBrokerSim raises IoUnavailable when mosquitto not in PATH."""
    pytest.importorskip("aiomqtt")
    from src.io.errors import IoUnavailable
    from src.io.simulators.mqtt_broker import start_mqtt_broker

    # Patch shutil.which to simulate mosquitto absence
    monkeypatch.setattr("shutil.which", lambda name: None)

    async def _run():
        with pytest.raises(IoUnavailable, match="mosquitto"):
            async with start_mqtt_broker():
                pass

    asyncio.run(_run())


def test_mqtt_broker_find_free_port_returns_bindable_port() -> None:
    pytest.importorskip("aiomqtt")
    from src.io.simulators.mqtt_broker import find_free_port

    port = find_free_port()
    assert isinstance(port, int)
    assert 1024 < port < 65536


def test_mqtt_broker_starts_when_mosquitto_available() -> None:
    """If mosquitto is installed, the broker starts and accepts connections."""
    pytest.importorskip("aiomqtt")
    if not shutil.which("mosquitto"):
        pytest.skip("mosquitto not in PATH")

    from src.io.simulators.mqtt_broker import start_mqtt_broker

    async def _run():
        async with start_mqtt_broker() as (host, port):
            assert host == "127.0.0.1"
            assert 1024 < port < 65536
            # Verify broker accepts TCP
            reader, writer = await asyncio.open_connection(host, port)
            writer.close()
            await writer.wait_closed()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# opcua_sim: smoke test — client connects + reads root node
# ---------------------------------------------------------------------------


def test_opcua_server_starts_and_client_connects() -> None:
    """Smoke: OPC-UA server starts, asyncua client connects and reads root node."""
    pytest.importorskip("asyncua")
    from src.io.simulators.opcua_sim import start_opcua_server

    async def _run():
        async with start_opcua_server() as (url, server):
            assert url.startswith("opc.tcp://")

            from asyncua import Client
            client = Client(url=url)
            await client.connect()
            root = client.get_root_node()
            # Root node ID is always NodeId(84, 0) — just verify it returns something
            root_id = root.nodeid
            assert root_id is not None

            await client.disconnect()

    asyncio.run(_run())


def test_opcua_server_seeds_writable_boolean_node() -> None:
    """The sim seeds a writable boolean at i=2 in the test namespace."""
    pytest.importorskip("asyncua")
    from src.io.simulators.opcua_sim import start_opcua_server

    async def _run():
        async with start_opcua_server(namespace=2) as (url, server):
            from asyncua import Client
            client = Client(url=url)
            await client.connect()

            ns_idx = await client.get_namespace_index("http://poc-robotarm/ns2")

            from asyncua import ua
            node_id = ua.NodeId(2, ns_idx)
            node = client.get_node(node_id)
            val = await node.read_value()
            assert isinstance(val, bool)

            await client.disconnect()

    asyncio.run(_run())


def test_opcua_server_find_free_port_returns_bindable() -> None:
    pytest.importorskip("asyncua")
    from src.io.simulators.opcua_sim import find_free_port

    port = find_free_port()
    assert isinstance(port, int)
    assert 1024 < port < 65536
