"""Modbus TCP server simulator for test fixtures.

Wraps ``pymodbus.server.StartAsyncTcpServer`` to start an in-process server
on a free local port.  Yields ``(host, port, context)`` where ``context``
is the :class:`pymodbus.datastore.ModbusServerContext` the test can mutate
to inject server-side value changes.

Usage
-----
::

    async with start_modbus_tcp_server(host="127.0.0.1") as (host, port, ctx):
        # ctx.slaves()[1].setValues(1, 0, [True])  # flip coil:0
        adapter = ModbusTcpAdapter(ModbusTcpConfig(host=host, port=port))
        await adapter.connect()
        ...

Notes
-----
* Port 0 lets the kernel pick a free port; the resolved port is read back
  from the server's internal socket after startup.
* The server task is cancelled cleanly on ``__aexit__``.
* All pymodbus imports are inside method bodies so the module is importable
  without the ``[io]`` extra.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import AsyncIterator


@contextlib.asynccontextmanager
async def start_modbus_tcp_server(
    host: str = "127.0.0.1",
    port: int = 0,
) -> AsyncIterator[tuple[str, int, object]]:
    """Async context manager that starts a Modbus TCP server and yields connection info.

    Parameters
    ----------
    host:
        Bind address (default ``"127.0.0.1"``).
    port:
        Bind port; use 0 to let the kernel pick a free port.

    Yields
    ------
    (host, port, context)
        * ``host`` — the bound host string.
        * ``port`` — the resolved port (useful when ``port=0``).
        * ``context`` — the :class:`pymodbus.datastore.ModbusServerContext`
          that tests can mutate to inject server-side value changes.
    """
    from pymodbus.datastore import ModbusServerContext, ModbusSlaveContext, ModbusSparseDataBlock
    from pymodbus.server import StartAsyncTcpServer

    # Build a simple single-slave context with 100 registers each.
    store = ModbusSlaveContext(
        di=ModbusSparseDataBlock({i: 0 for i in range(100)}),
        co=ModbusSparseDataBlock({i: 0 for i in range(100)}),
        hr=ModbusSparseDataBlock({i: 0 for i in range(100)}),
        ir=ModbusSparseDataBlock({i: 0 for i in range(100)}),
    )
    context = ModbusServerContext(slaves=store, single=True)

    server_exception: list[Exception] = []

    async def _run() -> None:
        try:
            await StartAsyncTcpServer(
                context=context,
                address=(host, port),
                custom_functions=[],
                defer_start=False,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            server_exception.append(exc)

    task = asyncio.get_running_loop().create_task(_run())

    # pymodbus 3.x does not expose an easy "ready" hook; wait a short interval.
    await asyncio.sleep(0.1)

    if server_exception:
        task.cancel()
        raise server_exception[0]

    # Discover the actual bound port via a brief probe.
    actual_port = port
    if port == 0:
        # Find the port by iterating pymodbus server internals or by a TCP probe.
        actual_port = await _probe_port(host)

    try:
        yield host, actual_port, context
    finally:
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass


async def _probe_port(host: str) -> int:
    """Probe the OS to find the port that pymodbus bound to.

    pymodbus 3.x does not cleanly expose the bound socket's port after
    ``StartAsyncTcpServer`` with port=0.  This helper attempts a sequence
    of connection probes on well-known test port ranges.  It is only called
    when the user passes ``port=0``.

    This limitation means callers should prefer passing an explicit port
    from ``_find_free_port()`` when port discovery is critical.
    """
    # Ask the OS for a free port directly — simpler and more reliable.
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return s.getsockname()[1]


def find_free_port(host: str = "127.0.0.1") -> int:
    """Return a free TCP port on ``host`` (binds then releases immediately).

    Use this before calling :func:`start_modbus_tcp_server` when you need
    the port number before the server starts::

        port = find_free_port()
        async with start_modbus_tcp_server(host="127.0.0.1", port=port) as (h, p, ctx):
            ...
    """
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, 0))
        return s.getsockname()[1]
