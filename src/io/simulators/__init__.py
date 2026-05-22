"""I/O simulator harnesses for test fixtures.

Each simulator in this sub-package is self-contained and exposes an async
context manager that starts a server on a free port and yields the
connection information the test client needs.

Notes
-----
* Simulators are **not** re-exported at package root (``src.io``).
* All simulators require the ``[io]`` extra (pymodbus / asyncua / aiomqtt)
  and/or system binaries (mosquitto).  Tests gate on library availability
  via ``pytest.importorskip`` or ``shutil.which``.
* The Modbus RTU simulator uses ``pty.openpty()`` (POSIX-only).
"""

from __future__ import annotations
