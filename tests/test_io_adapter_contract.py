"""Tests for IoAdapter ABC contract (risk #18).

Verifies that:
- IoAdapter.__abstractmethods__ enumerates exactly the expected set.
- Each concrete adapter class (ModbusTcpAdapter, etc.) has no leftover
  abstract methods — i.e. the class is fully implemented.
- A minimal FakeAdapter subclass satisfies the ABC and can be instantiated.
- AdapterCapabilities has correct slots.

Does NOT import heavy libs at module top — uses pytest.importorskip per
protocol so the file collects cleanly when extras are absent.
"""

from __future__ import annotations

import abc

import pytest

from src.io.adapter import AdapterCapabilities, IoAdapter
from src.io.types import IoEvent, SignalSpec

pytestmark = pytest.mark.io


# ---------------------------------------------------------------------------
# Minimal concrete adapter used to verify the ABC itself is satisfiable
# ---------------------------------------------------------------------------


class _FakeAdapter(IoAdapter):
    """Minimal adapter for contract testing — does not touch any protocol lib."""

    def __init__(self) -> None:
        self._connected = False

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            supports_subscribe=False,
            supports_write=True,
            supports_analog=False,
        )

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def read(self, signal: SignalSpec) -> IoEvent:
        return IoEvent(connection="fake", kind="value_changed", signal=signal.name, value=False)

    async def write(self, signal: SignalSpec, value: bool | int | float) -> IoEvent:
        return IoEvent(connection="fake", kind="write_ack", signal=signal.name, value=value)

    async def watch(self, signals):  # type: ignore[override]
        # Minimal async generator — yields nothing but satisfies type.
        while False:
            yield IoEvent(connection="fake", kind="value_changed")


# ---------------------------------------------------------------------------
# Abstract method set (risk #18)
# ---------------------------------------------------------------------------


_EXPECTED_ABSTRACT_METHODS = {"connect", "disconnect", "read", "write", "watch", "capabilities"}


def test_all_adapters_implement_abstract_methods() -> None:
    """IoAdapter.__abstractmethods__ must equal the expected set (risk #18)."""
    actual = set(IoAdapter.__abstractmethods__)
    assert actual == _EXPECTED_ABSTRACT_METHODS, (
        f"Abstract method set changed.\n"
        f"  Expected: {sorted(_EXPECTED_ABSTRACT_METHODS)}\n"
        f"  Got:      {sorted(actual)}"
    )


def test_fake_adapter_satisfies_abc() -> None:
    """A properly implemented subclass is instantiable (no TypeError)."""
    adapter = _FakeAdapter()
    assert isinstance(adapter, IoAdapter)


def test_io_adapter_is_abstract() -> None:
    """IoAdapter cannot be instantiated directly."""
    with pytest.raises(TypeError):
        IoAdapter()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# Check each concrete adapter for leftover abstract methods
# (importorskip makes these tests skip when the extras are absent)
# ---------------------------------------------------------------------------


def test_modbus_tcp_adapter_is_fully_implemented() -> None:
    pytest.importorskip("pymodbus")
    from src.io.adapters.modbus_tcp import ModbusTcpAdapter

    leftover = getattr(ModbusTcpAdapter, "__abstractmethods__", frozenset())
    assert not leftover, (
        f"ModbusTcpAdapter still has abstract methods: {leftover}"
    )


def test_modbus_rtu_adapter_is_fully_implemented() -> None:
    pytest.importorskip("pymodbus")
    from src.io.adapters.modbus_rtu import ModbusRtuAdapter

    leftover = getattr(ModbusRtuAdapter, "__abstractmethods__", frozenset())
    assert not leftover, (
        f"ModbusRtuAdapter still has abstract methods: {leftover}"
    )


def test_opcua_adapter_is_fully_implemented() -> None:
    pytest.importorskip("asyncua")
    from src.io.adapters.opcua import OpcUaAdapter

    leftover = getattr(OpcUaAdapter, "__abstractmethods__", frozenset())
    assert not leftover, (
        f"OpcUaAdapter still has abstract methods: {leftover}"
    )


def test_mqtt_adapter_is_fully_implemented() -> None:
    pytest.importorskip("aiomqtt")
    from src.io.adapters.mqtt import MqttAdapter

    leftover = getattr(MqttAdapter, "__abstractmethods__", frozenset())
    assert not leftover, (
        f"MqttAdapter still has abstract methods: {leftover}"
    )


# ---------------------------------------------------------------------------
# AdapterCapabilities
# ---------------------------------------------------------------------------


def test_adapter_capabilities_slots() -> None:
    caps = AdapterCapabilities(
        supports_subscribe=True,
        supports_write=False,
        supports_analog=True,
    )
    assert caps.supports_subscribe is True
    assert caps.supports_write is False
    assert caps.supports_analog is True


def test_adapter_capabilities_repr() -> None:
    caps = AdapterCapabilities(
        supports_subscribe=True, supports_write=True, supports_analog=False
    )
    r = repr(caps)
    assert "subscribe=True" in r
    assert "write=True" in r
    assert "analog=False" in r


def test_fake_adapter_capabilities_returns_instance() -> None:
    adapter = _FakeAdapter()
    caps = adapter.capabilities
    assert isinstance(caps, AdapterCapabilities)


# ---------------------------------------------------------------------------
# Extra coverage: ensure IoAdapter subclass hook is preserved
# ---------------------------------------------------------------------------


# Extra coverage: verify abc.ABC inheritance is intact
def test_io_adapter_is_abc_subclass() -> None:
    assert issubclass(IoAdapter, abc.ABC)
