"""MQTT broker simulator using a mosquitto subprocess.

Spawns ``mosquitto -p <port> -v`` as a subprocess and polls until it accepts
TCP connections before yielding control to the test.  On exit, sends SIGTERM
then SIGKILL if the process does not stop within 1 s.

Usage
-----
::

    async with start_mqtt_broker() as (host, port):
        adapter = MqttAdapter(MqttConfig(host=host, port=port, client_id="test"))
        await adapter.connect()
        ...

Notes
-----
* Requires the ``mosquitto`` binary to be in ``PATH``.  The context manager
  raises :class:`~src.io.errors.IoUnavailable` if ``mosquitto`` is absent.
* The subprocess is started with ``stderr=subprocess.PIPE`` so verbose logs
  don't pollute test output.  Stdout is also captured.
* This uses ``subprocess.Popen`` (not asyncio subprocess) because the broker
  is a long-running background process and we do not read its output in the
  hot path.  This is the only acceptable non-asyncio threading use in the
  I/O layer (per design §C).
* Port availability is polled via ``asyncio.open_connection`` with 50 ms
  backoff for up to 3 s before raising ``TimeoutError``.
"""

from __future__ import annotations

import asyncio
import contextlib
import shutil
import signal
import socket
import subprocess
from typing import AsyncIterator

from src.io.errors import IoUnavailable

__all__ = ["start_mqtt_broker", "find_free_port"]


def find_free_port(host: str = "127.0.0.1") -> int:
    """Return a free TCP port on ``host``."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind((host, 0))
        return s.getsockname()[1]


async def _wait_for_port(host: str, port: int, timeout_s: float = 3.0) -> None:
    """Poll ``(host, port)`` with 50 ms backoff until it accepts connections."""
    deadline = asyncio.get_running_loop().time() + timeout_s
    while asyncio.get_running_loop().time() < deadline:
        try:
            reader, writer = await asyncio.open_connection(host, port)
            writer.close()
            await writer.wait_closed()
            return
        except (ConnectionRefusedError, OSError):
            await asyncio.sleep(0.05)
    raise TimeoutError(
        f"mosquitto did not accept connections on {host}:{port} within {timeout_s} s"
    )


@contextlib.asynccontextmanager
async def start_mqtt_broker(
    host: str = "127.0.0.1",
    port: int | None = None,
) -> AsyncIterator[tuple[str, int]]:
    """Async context manager that spawns a mosquitto broker and yields ``(host, port)``.

    Parameters
    ----------
    host:
        Bind address (default ``"127.0.0.1"``).
    port:
        Port to bind.  If ``None``, a free port is chosen automatically.

    Yields
    ------
    (host, port)
        The host and port the broker is listening on.

    Raises
    ------
    IoUnavailable
        If ``mosquitto`` is not found in ``PATH``.
    TimeoutError
        If the broker does not become available within 3 s.
    """
    mosquitto = shutil.which("mosquitto")
    if mosquitto is None:
        raise IoUnavailable(
            "mosquitto binary not in PATH; install via apt-get install mosquitto"
        )

    actual_port = port if port is not None else find_free_port(host)

    # Config: bind to localhost only, allow anonymous clients.
    config_lines = [
        f"listener {actual_port} {host}",
        "allow_anonymous true",
    ]
    config_text = "\n".join(config_lines) + "\n"

    proc = subprocess.Popen(
        [mosquitto, "-v", "--config-file", "/dev/stdin"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Write the config via stdin then close it.
    try:
        proc.stdin.write(config_text.encode())  # type: ignore[union-attr]
        proc.stdin.close()  # type: ignore[union-attr]
    except BrokenPipeError:
        pass  # process may have exited immediately on bad config

    try:
        await _wait_for_port(host, actual_port)
        yield host, actual_port
    finally:
        if proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
            loop = asyncio.get_running_loop()
            try:
                # proc.wait() is a blocking call; run it in an executor to avoid
                # stalling the event loop during teardown.
                await loop.run_in_executor(None, proc.wait, 1.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                await loop.run_in_executor(None, proc.wait)
