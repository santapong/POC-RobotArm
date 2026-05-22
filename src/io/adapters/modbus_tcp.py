"""Modbus TCP adapter backed by ``pymodbus.client.AsyncModbusTcpClient``.

All pymodbus imports are deferred to method bodies so this module is
importable without the ``[io]`` extra installed.

Notes
-----
* ``AsyncModbusTcpClient.__init__`` requires a running event loop — it is
  therefore instantiated inside ``connect()``, not in ``__init__``.
* Address format: ``"coil:<n>"``, ``"discrete:<n>"``, ``"holding:<n>"``,
  ``"input:<n>"`` where ``<n>`` is a zero-based integer register index.
* Analog signals use holding / input registers (16-bit unsigned, 0-65535);
  scale and offset from :class:`SignalSpec` are applied on read.
* Digital signals use coil / discrete-input registers (bit values 0 / 1).
* Default poll interval: 1 s for digital, 0.5 s for analog.
"""

from __future__ import annotations

import asyncio
import time
from typing import AsyncIterator, Sequence

from src.io.adapter import AdapterCapabilities, IoAdapter
from src.io.errors import (
    IoConnectionError,
    IoNotConnected,
    IoProtocolError,
    IoTimeout,
    IoUnavailable,
)
from src.io.types import IoEvent, ModbusTcpConfig, SignalKind, SignalSpec

__all__ = ["ModbusTcpAdapter"]

_DEFAULT_POLL_DIGITAL_S = 1.0
_DEFAULT_POLL_ANALOG_S = 0.5


def _parse_address(address: str) -> tuple[str, int]:
    """Parse a Modbus address string like ``"coil:5"`` into ``("coil", 5)``."""
    parts = address.split(":", 1)
    if len(parts) != 2:
        raise ValueError(
            f"Modbus address must be '<type>:<n>', got {address!r}. "
            "Examples: 'coil:0', 'holding:3', 'discrete:1', 'input:2'"
        )
    reg_type = parts[0].lower()
    if reg_type not in ("coil", "discrete", "holding", "input"):
        raise ValueError(
            f"Modbus register type must be coil/discrete/holding/input, got {reg_type!r}"
        )
    try:
        index = int(parts[1])
    except ValueError:
        raise ValueError(f"Modbus register index must be an integer, got {parts[1]!r}")
    if index < 0:
        raise ValueError(f"Modbus register index must be >= 0, got {index}")
    return reg_type, index


class ModbusTcpAdapter(IoAdapter):
    """Modbus TCP client adapter.

    Parameters
    ----------
    config:
        :class:`~src.io.types.ModbusTcpConfig` for this connection.
    """

    def __init__(self, config: ModbusTcpConfig) -> None:
        # Validate the library is available at construction time (not at import).
        try:
            import pymodbus  # noqa: F401
        except ImportError as exc:
            raise IoUnavailable(
                "pymodbus is not installed; run: pip install 'pymodbus>=3.7,<4'"
            ) from exc
        self._config = config
        self._client: object | None = None  # AsyncModbusTcpClient, typed as object for lazy import
        self._connected = False

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            supports_subscribe=False,  # Modbus is poll-only
            supports_write=True,
            supports_analog=True,
        )

    async def connect(self) -> None:
        """Open the Modbus TCP connection."""
        from pymodbus.client import AsyncModbusTcpClient
        from pymodbus.exceptions import ConnectionException

        self._client = AsyncModbusTcpClient(
            host=self._config.host,
            port=self._config.port,
            timeout=self._config.timeout_s,
        )
        try:
            connected = await self._client.connect()  # type: ignore[union-attr]
        except (ConnectionException, OSError) as exc:
            self._client = None
            raise IoConnectionError(
                f"Modbus TCP connect to {self._config.host}:{self._config.port} failed: {exc}"
            ) from exc
        if not connected:
            self._client = None
            raise IoConnectionError(
                f"Modbus TCP connect to {self._config.host}:{self._config.port} failed: "
                "client.connect() returned False"
            )
        self._connected = True

    async def disconnect(self) -> None:
        """Close the Modbus TCP connection (idempotent)."""
        self._connected = False
        if self._client is not None:
            try:
                self._client.close()  # type: ignore[union-attr]
            except Exception:
                pass
            self._client = None

    async def read(self, signal: SignalSpec) -> IoEvent:
        """Read one signal value from the Modbus device."""
        if not self._connected or self._client is None:
            raise IoNotConnected(
                f"Modbus TCP not connected to {self._config.host}:{self._config.port}"
            )
        from pymodbus.exceptions import ConnectionException, ModbusException

        reg_type, index = _parse_address(signal.address)
        try:
            value = await asyncio.wait_for(
                self._read_register(reg_type, index, signal),
                timeout=self._config.timeout_s,
            )
        except asyncio.TimeoutError as exc:
            raise IoTimeout(
                f"Modbus TCP read of {signal.address} timed out after {self._config.timeout_s} s"
            ) from exc
        except (ConnectionException, ModbusException, OSError) as exc:
            raise IoProtocolError(f"Modbus TCP read of {signal.address} failed: {exc}") from exc

        return IoEvent(
            connection=self._config.host,
            kind="value_changed",
            signal=signal.name,
            value=value,
            monotonic_s=time.monotonic(),
        )

    async def _read_register(
        self, reg_type: str, index: int, signal: SignalSpec
    ) -> bool | int | float:
        """Internal: issue the Modbus read and coerce the raw value."""
        from pymodbus.exceptions import ModbusIOException

        client = self._client  # type: ignore[assignment]

        if reg_type == "coil":
            rr = await client.read_coils(index, count=1, slave=self._config.unit_id)
        elif reg_type == "discrete":
            rr = await client.read_discrete_inputs(index, count=1, slave=self._config.unit_id)
        elif reg_type == "holding":
            rr = await client.read_holding_registers(index, count=1, slave=self._config.unit_id)
        else:  # input
            rr = await client.read_input_registers(index, count=1, slave=self._config.unit_id)

        if rr.isError():
            raise ModbusIOException(f"Modbus error response: {rr}")

        if reg_type in ("coil", "discrete"):
            return bool(rr.bits[0])

        raw = rr.registers[0]
        if signal.kind in (SignalKind.ANALOG_IN, SignalKind.ANALOG_OUT):
            return raw * signal.scale + signal.offset
        return raw

    async def write(self, signal: SignalSpec, value: bool | int | float) -> IoEvent:
        """Write one signal value to the Modbus device."""
        if not self._connected or self._client is None:
            raise IoNotConnected(
                f"Modbus TCP not connected to {self._config.host}:{self._config.port}"
            )
        from pymodbus.exceptions import ConnectionException, ModbusException

        reg_type, index = _parse_address(signal.address)
        try:
            await asyncio.wait_for(
                self._write_register(reg_type, index, signal, value),
                timeout=self._config.timeout_s,
            )
        except asyncio.TimeoutError as exc:
            raise IoTimeout(
                f"Modbus TCP write to {signal.address} timed out after {self._config.timeout_s} s"
            ) from exc
        except (ConnectionException, ModbusException, OSError) as exc:
            raise IoProtocolError(f"Modbus TCP write to {signal.address} failed: {exc}") from exc

        return IoEvent(
            connection=self._config.host,
            kind="write_ack",
            signal=signal.name,
            value=value,
            monotonic_s=time.monotonic(),
        )

    async def _write_register(
        self, reg_type: str, index: int, signal: SignalSpec, value: bool | int | float
    ) -> None:
        """Internal: issue the Modbus write."""
        from pymodbus.exceptions import ModbusIOException

        client = self._client  # type: ignore[assignment]

        if reg_type == "coil":
            rr = await client.write_coil(index, bool(value), slave=self._config.unit_id)
        elif reg_type == "holding":
            rr = await client.write_register(index, int(value), slave=self._config.unit_id)
        else:
            raise IoProtocolError(
                f"Cannot write to register type {reg_type!r}; "
                "only 'coil' and 'holding' are writable"
            )
        if rr.isError():
            raise ModbusIOException(f"Modbus write error response: {rr}")

    async def watch(self, signals: Sequence[SignalSpec]) -> AsyncIterator[IoEvent]:  # type: ignore[override]
        """Poll all signals and yield value-changed events indefinitely.

        Polls each signal at ``signal.poll_interval_s`` (or the default) and
        yields an :class:`IoEvent` whenever the value differs from the cached
        last value.  Uses ``asyncio.sleep`` for pacing — never ``time.sleep``.
        """
        if not signals:
            # Nothing to watch; yield nothing and wait for cancellation.
            while True:
                await asyncio.sleep(1.0)

        last_values: dict[str, bool | int | float | None] = {s.name: None for s in signals}

        while True:
            for sig in signals:
                try:
                    event = await self.read(sig)
                except Exception:
                    # Transient read failure — skip this tick rather than killing the loop.
                    continue

                if last_values[sig.name] != event.value:
                    last_values[sig.name] = event.value
                    yield event

            # Sleep for the shortest poll interval among the signals.
            min_interval = min(
                (
                    s.poll_interval_s
                    if s.poll_interval_s is not None
                    else (
                        _DEFAULT_POLL_DIGITAL_S
                        if s.kind in (SignalKind.DIGITAL_IN, SignalKind.DIGITAL_OUT)
                        else _DEFAULT_POLL_ANALOG_S
                    )
                )
                for s in signals
            )
            await asyncio.sleep(min_interval)
