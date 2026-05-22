"""Modbus RTU server simulator using a pty pair (POSIX-only).

Uses ``pty.openpty()`` to create a pseudo-terminal pair: the server binds to
the master fd, and the client connects via the slave device path (e.g.
``/dev/pts/4``).

Usage
-----
::

    # Skip on Windows — pty is POSIX-only.
    import sys, pytest
    if sys.platform == "win32":
        pytest.skip("RTU simulator requires POSIX pty")

    async with start_modbus_rtu_server() as (device_path, ctx):
        adapter = ModbusRtuAdapter(ModbusRtuConfig(device=device_path, ...))
        await adapter.connect()
        ...

Notes
-----
* The master fd is kept alive for the lifetime of the context so the slave
  device remains valid.
* ``pty`` is a POSIX-only stdlib module.  The ``pty.openpty()`` call is
  inside the async context manager body so the module is importable on all
  platforms; import-time failures are avoided.
* The RTU server task is cancelled cleanly on ``__aexit__``.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
from typing import AsyncIterator


@contextlib.asynccontextmanager
async def start_modbus_rtu_server(
    baudrate: int = 19200,
) -> AsyncIterator[tuple[str, object]]:
    """Async context manager that starts a Modbus RTU server over a pty pair.

    Parameters
    ----------
    baudrate:
        Serial baud rate passed to the pymodbus server (default 19200).

    Yields
    ------
    (device_path, context)
        * ``device_path`` — slave-side pty device path (e.g. ``"/dev/pts/4"``).
        * ``context`` — :class:`pymodbus.datastore.ModbusServerContext`.

    Raises
    ------
    ImportError
        If ``pty`` is not available (Windows).
    """
    if sys.platform == "win32":
        raise ImportError("pty.openpty() is not available on Windows")

    import pty  # POSIX-only stdlib module

    from pymodbus.datastore import ModbusServerContext, ModbusSlaveContext, ModbusSparseDataBlock
    from pymodbus.server import StartAsyncSerialServer

    master_fd, slave_fd = pty.openpty()
    device_path = os.ttyname(slave_fd)
    # Close the slave fd — pymodbus will reopen it via pyserial.
    os.close(slave_fd)

    store = ModbusSlaveContext(
        di=ModbusSparseDataBlock({i: 0 for i in range(100)}),
        co=ModbusSparseDataBlock({i: 0 for i in range(100)}),
        hr=ModbusSparseDataBlock({i: 0 for i in range(100)}),
        ir=ModbusSparseDataBlock({i: 0 for i in range(100)}),
    )
    context = ModbusServerContext(slaves=store, single=True)

    server_task: asyncio.Task | None = None
    try:
        async def _run() -> None:
            await StartAsyncSerialServer(
                context=context,
                port=device_path,
                baudrate=baudrate,
                timeout=1,
            )

        server_task = asyncio.get_running_loop().create_task(_run())
        # Give pymodbus a moment to open the port.
        await asyncio.sleep(0.15)

        yield device_path, context
    finally:
        if server_task is not None and not server_task.done():
            server_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(server_task), timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
        # Release the master fd — this signals EOF to anything still reading.
        try:
            os.close(master_fd)
        except OSError:
            pass
