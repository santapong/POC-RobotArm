"""Modbus TCP server simulator for test fixtures.

Wraps ``pymodbus.server.StartAsyncTcpServer`` to start an in-process server
on a caller-supplied port.  Yields ``(host, port, context)`` where ``context``
is the :class:`pymodbus.datastore.ModbusServerContext` the test can mutate
to inject server-side value changes.

Usage
-----
::

    port = find_free_port()
    async with start_modbus_tcp_server(host="127.0.0.1", port=port) as (host, port, ctx):
        # ctx.slaves()[1].setValues(1, 0, [True])  # flip coil:0
        adapter = ModbusTcpAdapter(ModbusTcpConfig(host=host, port=port))
        await adapter.connect()
        ...

Notes
-----
* ``port=0`` is rejected — use :func:`find_free_port` to discover an ephemeral
  port before calling this function and pass it explicitly.  Attempting to use
  port 0 would bind a fresh socket (unrelated to pymodbus) and yield a port
  that points to nothing, so it is an error.

  .. note::
     There is an inherent ~100 ms TOCTOU race between :func:`find_free_port`
     releasing the socket and pymodbus binding it.  This is acceptable for
     test fixtures but should not be used in production code.

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
    port: int = 502,
) -> AsyncIterator[tuple[str, int, object]]:
    """Async context manager that starts a Modbus TCP server and yields connection info.

    Parameters
    ----------
    host:
        Bind address (default ``"127.0.0.1"``).
    port:
        Bind port.  Must be a positive integer.  Use :func:`find_free_port` to
        obtain an ephemeral port before calling this function.  Passing ``0``
        is an error because the OS-assigned port cannot be reliably discovered
        from pymodbus 3.x internals.

    Yields
    ------
    (host, port, context)
        * ``host`` — the bound host string.
        * ``port`` — the port the server was told to bind (same as input).
        * ``context`` — the :class:`pymodbus.datastore.ModbusServerContext`
          that tests can mutate to inject server-side value changes.

    Raises
    ------
    ValueError
        If ``port=0`` is passed.
    """
    if port == 0:
        raise ValueError(
            "modbus_tcp_sim does not support port=0; "
            "use the find_free_port() helper to discover a free port and pass it explicitly"
        )

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
    # There is an inherent ~100 ms race before the port becomes accessible —
    # see module-level Notes.
    await asyncio.sleep(0.1)

    if server_exception:
        task.cancel()
        raise server_exception[0]

    try:
        yield host, port, context
    finally:
        task.cancel()
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass


def find_free_port(host: str = "127.0.0.1") -> int:
    """Return a free TCP port on ``host`` (binds then releases immediately).

    This is the **only** supported way to obtain an ephemeral port for
    :func:`start_modbus_tcp_server`.  Discover the port with this helper,
    then pass it explicitly::

        port = find_free_port()
        async with start_modbus_tcp_server(host="127.0.0.1", port=port) as (h, p, ctx):
            ...

    .. warning::
       There is a TOCTOU race between this function releasing the socket and
       pymodbus binding it (~100 ms window).  This is acceptable for test
       fixtures but not for production use.
    """
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, 0))
        return s.getsockname()[1]
