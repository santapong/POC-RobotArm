"""Concrete I/O protocol adapter implementations.

Each adapter module imports its heavy library (pymodbus, asyncua, aiomqtt)
lazily inside method bodies so ``import src.io.adapters`` succeeds without the
``[io]`` extra installed.
"""

from __future__ import annotations
