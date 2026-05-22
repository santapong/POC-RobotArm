"""Short-name → adapter class mapping and factory function.

``build_adapter(config)`` is the single entry point for creating an
:class:`~src.io.adapter.IoAdapter` from a :class:`~src.io.types.ConnectionConfig`
discriminated union.

Notes
-----
* The registry imports concrete adapter classes lazily inside
  ``build_adapter`` so ``import src.io.registry`` succeeds without the
  ``[io]`` extra installed.
* If the underlying library is missing, the concrete adapter's ``__init__``
  raises :class:`~src.io.errors.IoUnavailable` — this propagates to the caller.
* Unknown config types raise :class:`ValueError` immediately (not
  :class:`~src.io.errors.IoError`) because they indicate a programming error,
  not an operator error.
"""

from __future__ import annotations

from src.io.adapter import IoAdapter
from src.io.types import (
    ConnectionConfig,
    ModbusRtuConfig,
    ModbusTcpConfig,
    MqttConfig,
    OpcUaConfig,
)

__all__ = ["build_adapter"]


def build_adapter(config: ConnectionConfig) -> IoAdapter:
    """Create and return an :class:`IoAdapter` for the given ``config``.

    Parameters
    ----------
    config:
        A :class:`~src.io.types.ConnectionConfig` instance (one of
        :class:`ModbusTcpConfig`, :class:`ModbusRtuConfig`,
        :class:`OpcUaConfig`, :class:`MqttConfig`).

    Returns
    -------
    IoAdapter
        A concrete adapter ready to be connected.

    Raises
    ------
    IoUnavailable
        If the required library for the protocol is not installed.
    ValueError
        If ``config`` is not a recognised :class:`ConnectionConfig` type.

    Examples
    --------
    >>> from src.io.types import ModbusTcpConfig
    >>> from src.io.registry import build_adapter
    >>> adapter = build_adapter(ModbusTcpConfig(host="127.0.0.1", port=502))
    """
    if isinstance(config, ModbusTcpConfig):
        from src.io.adapters.modbus_tcp import ModbusTcpAdapter

        return ModbusTcpAdapter(config)

    if isinstance(config, ModbusRtuConfig):
        from src.io.adapters.modbus_rtu import ModbusRtuAdapter

        return ModbusRtuAdapter(config)

    if isinstance(config, OpcUaConfig):
        from src.io.adapters.opcua import OpcUaAdapter

        return OpcUaAdapter(config)

    if isinstance(config, MqttConfig):
        from src.io.adapters.mqtt import MqttAdapter

        return MqttAdapter(config)

    raise ValueError(
        f"Unknown connection config type: {type(config).__name__!r}. "
        "Expected one of ModbusTcpConfig, ModbusRtuConfig, OpcUaConfig, MqttConfig."
    )
