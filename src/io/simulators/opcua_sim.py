"""OPC-UA server simulator for test fixtures.

Wraps ``asyncua.Server`` to start an in-process OPC-UA server on a free
local port and seed it with a default node tree.

Usage
-----
::

    async with start_opcua_server() as (url, server):
        # server is the asyncua.Server instance — tests can add/modify nodes.
        adapter = OpcUaAdapter(OpcUaConfig(url=url, namespace=2))
        await adapter.connect()
        ...

Notes
-----
* The endpoint ``opc.tcp://127.0.0.1:0/freeopcua/server/`` with port 0 is
  not directly supported by asyncua — the port must be chosen before the
  call to ``server.start()``.  Use :func:`find_free_port` to select an
  available port first.
* The default node tree adds one writable boolean node at namespace 2,
  numeric id 2 (``"i=2;ns=2"`` in address form), matching the Phase 4
  exit-gate demo scenario.
* All asyncua imports are inside method bodies.
"""

from __future__ import annotations

import contextlib
import socket
from typing import AsyncIterator


def find_free_port(host: str = "127.0.0.1") -> int:
    """Return a free TCP port on ``host``."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, 0))
        return s.getsockname()[1]


@contextlib.asynccontextmanager
async def start_opcua_server(
    host: str = "127.0.0.1",
    port: int | None = None,
    namespace: int = 2,
) -> AsyncIterator[tuple[str, object]]:
    """Async context manager that starts an OPC-UA server and yields connection info.

    Parameters
    ----------
    host:
        Bind host (default ``"127.0.0.1"``).
    port:
        Port to bind.  If ``None``, a free port is chosen automatically.
    namespace:
        OPC-UA namespace index for the default nodes.

    Yields
    ------
    (url, server)
        * ``url`` — the endpoint URL string (e.g. ``"opc.tcp://127.0.0.1:4840/..."``)
        * ``server`` — the ``asyncua.Server`` instance.

    Notes
    -----
    The server adds one namespace (index ``namespace``), and one writable
    boolean variable node at ``i=2`` in that namespace, i.e. address
    ``"i=2"`` with the :class:`OpcUaConfig` ``namespace`` set to the same
    value.
    """
    from asyncua import Server

    actual_port = port if port is not None else find_free_port(host)
    endpoint = f"opc.tcp://{host}:{actual_port}/freeopcua/server/"

    server = Server()
    await server.init()
    server.set_endpoint(endpoint)

    # Register the test namespace.
    idx = await server.register_namespace(f"http://poc-robotarm/ns{namespace}")

    # Seed a writable boolean node at numeric id 2.
    objects = server.get_objects_node()
    part_present = await objects.add_variable(idx, "part_present", False)
    await part_present.set_writable()

    await server.start()
    try:
        yield endpoint, server
    finally:
        await server.stop()
