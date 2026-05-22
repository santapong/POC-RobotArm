"""Tests for src.io.types and src.io.errors.

Covers:
- SignalKind 4-state enum + string coercion
- SignalSpec validators (empty name/address, negative poll_interval_s)
- All 4 Config classes: happy path + 2+ negative cases each
- IoEvent __post_init__ and monotonic_s sentinel resolution
- IoEvent.kind literal values
- JSON round-trip via to_dict / from_dict for every public dataclass
- bool-vs-int type preservation in IoEvent.value (risk #16)
- Error hierarchy instantiation and __str__
- build_adapter / registry (stdlib-only paths only)

No pymodbus / asyncua / aiomqtt / simulator imports.
"""

from __future__ import annotations

import time

import pytest

from src.io.errors import (
    IoConnectionError,
    IoError,
    IoNotConnected,
    IoProtocolError,
    IoSignalKindMismatch,
    IoTimeout,
    IoUnavailable,
    IoUnknownSignal,
)
from src.io.types import (
    ConnectionProtocol,
    ConnectionStatusKind,
    IoEvent,
    ModbusRtuConfig,
    ModbusTcpConfig,
    MqttConfig,
    OpcUaConfig,
    SignalKind,
    SignalSpec,
    from_dict,
    to_dict,
)

pytestmark = pytest.mark.io


# ---------------------------------------------------------------------------
# SignalKind
# ---------------------------------------------------------------------------


def test_signal_kind_four_values() -> None:
    kinds = list(SignalKind)
    assert len(kinds) == 4
    values = {k.value for k in kinds}
    assert values == {"digital_in", "digital_out", "analog_in", "analog_out"}


def test_signal_kind_string_coercion() -> None:
    assert SignalKind("digital_in") is SignalKind.DIGITAL_IN
    assert SignalKind("analog_out") is SignalKind.ANALOG_OUT


def test_signal_kind_is_str_subclass() -> None:
    # SignalKind(str, Enum) — can be compared to plain strings
    assert SignalKind.DIGITAL_OUT == "digital_out"


def test_signal_kind_invalid_string_raises() -> None:
    with pytest.raises(ValueError):
        SignalKind("not_a_kind")


# ---------------------------------------------------------------------------
# ConnectionProtocol enum
# ---------------------------------------------------------------------------


def test_connection_protocol_four_values() -> None:
    values = {p.value for p in ConnectionProtocol}
    assert values == {"modbus_tcp", "modbus_rtu", "opcua", "mqtt"}


def test_connection_status_kind_five_values() -> None:
    values = {s.value for s in ConnectionStatusKind}
    assert values == {"disconnected", "connecting", "open", "error", "closing"}


# ---------------------------------------------------------------------------
# SignalSpec validators
# ---------------------------------------------------------------------------


def test_signal_spec_happy_path() -> None:
    sig = SignalSpec(name="di0", kind=SignalKind.DIGITAL_IN, address="coil:0")
    assert sig.name == "di0"
    assert sig.kind is SignalKind.DIGITAL_IN
    assert sig.scale == 1.0
    assert sig.offset == 0.0
    assert sig.poll_interval_s is None


def test_signal_spec_string_kind_coercion() -> None:
    sig = SignalSpec(name="ao1", kind="analog_out", address="holding:3")  # type: ignore[arg-type]
    assert sig.kind is SignalKind.ANALOG_OUT


def test_signal_spec_empty_name_raises() -> None:
    with pytest.raises(ValueError, match="name must not be empty"):
        SignalSpec(name="", kind=SignalKind.DIGITAL_IN, address="coil:0")


def test_signal_spec_empty_address_raises() -> None:
    with pytest.raises(ValueError, match="address must not be empty"):
        SignalSpec(name="sig", kind=SignalKind.DIGITAL_IN, address="")


def test_signal_spec_negative_poll_interval_raises() -> None:
    with pytest.raises(ValueError, match="poll_interval_s must be > 0"):
        SignalSpec(name="sig", kind=SignalKind.DIGITAL_IN, address="coil:0", poll_interval_s=-1.0)


def test_signal_spec_zero_poll_interval_raises() -> None:
    with pytest.raises(ValueError, match="poll_interval_s must be > 0"):
        SignalSpec(name="sig", kind=SignalKind.DIGITAL_IN, address="coil:0", poll_interval_s=0.0)


def test_signal_spec_valid_poll_interval() -> None:
    sig = SignalSpec(name="ai", kind=SignalKind.ANALOG_IN, address="input:0", poll_interval_s=0.5)
    assert sig.poll_interval_s == 0.5


def test_signal_spec_invalid_qos_raises() -> None:
    with pytest.raises(ValueError, match="qos must be 0, 1, or 2"):
        SignalSpec(name="sig", kind=SignalKind.DIGITAL_IN, address="t", qos=3)


def test_signal_spec_is_frozen() -> None:
    sig = SignalSpec(name="di0", kind=SignalKind.DIGITAL_IN, address="coil:0")
    with pytest.raises((AttributeError, TypeError)):
        sig.name = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ModbusTcpConfig
# ---------------------------------------------------------------------------


def test_modbus_tcp_config_happy_path() -> None:
    cfg = ModbusTcpConfig(host="127.0.0.1", port=502, unit_id=1, timeout_s=3.0)
    assert cfg.protocol == "modbus_tcp"
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 502


def test_modbus_tcp_config_defaults() -> None:
    cfg = ModbusTcpConfig(host="plc.local")
    assert cfg.port == 502
    assert cfg.unit_id == 1
    assert cfg.timeout_s == 3.0


def test_modbus_tcp_config_empty_host_raises() -> None:
    with pytest.raises(ValueError, match="host must not be empty"):
        ModbusTcpConfig(host="")


def test_modbus_tcp_config_zero_timeout_raises() -> None:
    with pytest.raises(ValueError, match="timeout_s must be > 0"):
        ModbusTcpConfig(host="h", timeout_s=0.0)


def test_modbus_tcp_config_negative_timeout_raises() -> None:
    with pytest.raises(ValueError, match="timeout_s must be > 0"):
        ModbusTcpConfig(host="h", timeout_s=-1.0)


def test_modbus_tcp_config_invalid_port_raises() -> None:
    with pytest.raises(ValueError, match="port must be 1-65535"):
        ModbusTcpConfig(host="h", port=0)


def test_modbus_tcp_config_invalid_unit_id_raises() -> None:
    with pytest.raises(ValueError, match="unit_id must be 0-247"):
        ModbusTcpConfig(host="h", unit_id=248)


def test_modbus_tcp_config_is_frozen() -> None:
    cfg = ModbusTcpConfig(host="h")
    with pytest.raises((AttributeError, TypeError)):
        cfg.host = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ModbusRtuConfig
# ---------------------------------------------------------------------------


def test_modbus_rtu_config_happy_path() -> None:
    cfg = ModbusRtuConfig(device="/dev/ttyUSB0", baudrate=19200)
    assert cfg.protocol == "modbus_rtu"
    assert cfg.parity == "N"
    assert cfg.stopbits == 1
    assert cfg.bytesize == 8


def test_modbus_rtu_config_empty_device_raises() -> None:
    with pytest.raises(ValueError, match="device must not be empty"):
        ModbusRtuConfig(device="")


def test_modbus_rtu_config_invalid_baudrate_raises() -> None:
    with pytest.raises(ValueError, match="baudrate must be 1200-921600"):
        ModbusRtuConfig(device="/dev/tty0", baudrate=100)


def test_modbus_rtu_config_invalid_parity_raises() -> None:
    with pytest.raises(ValueError, match="parity must be N/E/O"):
        ModbusRtuConfig(device="/dev/tty0", parity="X")  # type: ignore[arg-type]


def test_modbus_rtu_config_invalid_stopbits_raises() -> None:
    with pytest.raises(ValueError, match="stopbits must be 1 or 2"):
        ModbusRtuConfig(device="/dev/tty0", stopbits=3)  # type: ignore[arg-type]


def test_modbus_rtu_config_zero_timeout_raises() -> None:
    with pytest.raises(ValueError, match="timeout_s must be > 0"):
        ModbusRtuConfig(device="/dev/tty0", timeout_s=0.0)


# ---------------------------------------------------------------------------
# OpcUaConfig
# ---------------------------------------------------------------------------


def test_opcua_config_happy_path() -> None:
    cfg = OpcUaConfig(url="opc.tcp://localhost:4840")
    assert cfg.protocol == "opcua"
    assert cfg.namespace == 2
    assert cfg.username is None
    assert cfg.password is None


def test_opcua_config_empty_url_raises() -> None:
    with pytest.raises(ValueError, match="url must not be empty"):
        OpcUaConfig(url="")


def test_opcua_config_negative_namespace_raises() -> None:
    with pytest.raises(ValueError, match="namespace must be >= 0"):
        OpcUaConfig(url="opc.tcp://localhost:4840", namespace=-1)


def test_opcua_config_zero_timeout_raises() -> None:
    with pytest.raises(ValueError, match="timeout_s must be > 0"):
        OpcUaConfig(url="opc.tcp://localhost:4840", timeout_s=0.0)


def test_opcua_config_is_frozen() -> None:
    cfg = OpcUaConfig(url="opc.tcp://localhost:4840")
    with pytest.raises((AttributeError, TypeError)):
        cfg.url = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# MqttConfig
# ---------------------------------------------------------------------------


def test_mqtt_config_happy_path() -> None:
    cfg = MqttConfig(host="broker.local", port=1883, client_id="test_client")
    assert cfg.protocol == "mqtt"
    assert cfg.qos == 0
    assert cfg.keepalive_s == 60


def test_mqtt_config_empty_host_raises() -> None:
    with pytest.raises(ValueError, match="host must not be empty"):
        MqttConfig(host="")


def test_mqtt_config_zero_timeout_raises() -> None:
    with pytest.raises(ValueError, match="timeout_s must be > 0"):
        MqttConfig(host="b", timeout_s=0.0)


def test_mqtt_config_invalid_port_raises() -> None:
    with pytest.raises(ValueError, match="port must be 1-65535"):
        MqttConfig(host="b", port=65536)


def test_mqtt_config_invalid_qos_raises() -> None:
    with pytest.raises(ValueError, match="qos must be 0, 1, or 2"):
        MqttConfig(host="b", qos=3)  # type: ignore[arg-type]


def test_mqtt_config_invalid_keepalive_raises() -> None:
    with pytest.raises(ValueError, match="keepalive_s must be >= 1"):
        MqttConfig(host="b", keepalive_s=0)


# ---------------------------------------------------------------------------
# IoEvent
# ---------------------------------------------------------------------------


def test_io_event_happy_path() -> None:
    ev = IoEvent(connection="mb", kind="value_changed", signal="di0", value=True)
    assert ev.connection == "mb"
    assert ev.kind == "value_changed"
    assert ev.signal == "di0"
    assert isinstance(ev.monotonic_s, float)
    assert ev.monotonic_s > 0


def test_io_event_monotonic_s_sentinel_resolved() -> None:
    before = time.monotonic()
    ev = IoEvent(connection="c", kind="write_ack")
    after = time.monotonic()
    assert ev.monotonic_s is not None
    assert before <= ev.monotonic_s <= after  # type: ignore[operator]


def test_io_event_explicit_monotonic_s_preserved() -> None:
    ev = IoEvent(connection="c", kind="write_ack", monotonic_s=0.0)
    assert ev.monotonic_s == 0.0


def test_io_event_empty_connection_raises() -> None:
    with pytest.raises(ValueError, match="connection must not be empty"):
        IoEvent(connection="", kind="value_changed")


def test_io_event_invalid_kind_raises() -> None:
    with pytest.raises(ValueError, match="not a valid event kind"):
        IoEvent(connection="c", kind="unknown_kind")  # type: ignore[arg-type]


def test_io_event_kind_literals() -> None:
    valid_kinds = ("connection_changed", "value_changed", "write_ack", "error")
    for kind in valid_kinds:
        ev = IoEvent(connection="c", kind=kind)  # type: ignore[arg-type]
        assert ev.kind == kind


def test_io_event_is_frozen() -> None:
    ev = IoEvent(connection="c", kind="write_ack")
    with pytest.raises((AttributeError, TypeError)):
        ev.connection = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Risk #16 — bool-vs-int type preservation through JSON round-trip
# ---------------------------------------------------------------------------


def test_io_event_round_trip_preserves_bool_type() -> None:
    """Verifies that a True value survives to_dict/from_dict as bool, not int."""
    ev = IoEvent(connection="mb", kind="value_changed", signal="di0", value=True, monotonic_s=1.0)
    d = to_dict(ev)
    ev2 = from_dict(d, IoEvent)
    assert ev2.value is True
    assert type(ev2.value) is bool  # not int


def test_io_event_round_trip_preserves_false() -> None:
    ev = IoEvent(connection="mb", kind="value_changed", signal="di0", value=False, monotonic_s=1.0)
    d = to_dict(ev)
    ev2 = from_dict(d, IoEvent)
    assert ev2.value is False
    assert type(ev2.value) is bool


def test_io_event_round_trip_preserves_float_value() -> None:
    ev = IoEvent(connection="opc", kind="value_changed", signal="ai0", value=3.14, monotonic_s=2.0)
    d = to_dict(ev)
    ev2 = from_dict(d, IoEvent)
    assert abs(ev2.value - 3.14) < 1e-9  # type: ignore[operator]


# ---------------------------------------------------------------------------
# to_dict / from_dict round-trips for all config classes
# ---------------------------------------------------------------------------


def test_modbus_tcp_config_round_trip() -> None:
    cfg = ModbusTcpConfig(host="192.168.1.1", port=1502, unit_id=5, timeout_s=2.5)
    d = to_dict(cfg)
    assert d["__type__"] == "ModbusTcpConfig"
    assert d["host"] == "192.168.1.1"
    cfg2 = from_dict(d, ModbusTcpConfig)
    assert cfg2 == cfg


def test_modbus_rtu_config_round_trip() -> None:
    cfg = ModbusRtuConfig(device="/dev/ttyUSB0", baudrate=9600, parity="E", stopbits=2)
    d = to_dict(cfg)
    assert d["__type__"] == "ModbusRtuConfig"
    cfg2 = from_dict(d, ModbusRtuConfig)
    assert cfg2 == cfg


def test_opcua_config_round_trip() -> None:
    cfg = OpcUaConfig(url="opc.tcp://127.0.0.1:4840", namespace=3)
    d = to_dict(cfg)
    assert d["__type__"] == "OpcUaConfig"
    cfg2 = from_dict(d, OpcUaConfig)
    assert cfg2 == cfg


def test_mqtt_config_round_trip() -> None:
    cfg = MqttConfig(host="broker", port=8883, client_id="cli1", qos=1)
    d = to_dict(cfg)
    assert d["__type__"] == "MqttConfig"
    cfg2 = from_dict(d, MqttConfig)
    assert cfg2 == cfg


def test_signal_spec_round_trip() -> None:
    sig = SignalSpec(
        name="ao0", kind=SignalKind.ANALOG_OUT, address="holding:3",
        scale=0.1, offset=-5.0, poll_interval_s=0.25,
    )
    d = to_dict(sig)
    assert d["__type__"] == "SignalSpec"
    sig2 = from_dict(d, SignalSpec)
    assert sig2 == sig


def test_io_event_round_trip_full() -> None:
    ev = IoEvent(
        connection="opc_arm",
        kind="connection_changed",
        signal=None,
        value=None,
        status="open",
        monotonic_s=42.5,
    )
    d = to_dict(ev)
    ev2 = from_dict(d, IoEvent)
    assert ev2 == ev


def test_from_dict_wrong_type_raises() -> None:
    cfg = ModbusTcpConfig(host="h")
    d = to_dict(cfg)
    with pytest.raises(ValueError, match="does not match expected"):
        from_dict(d, IoEvent)


def test_from_dict_unknown_type_raises() -> None:
    with pytest.raises(ValueError, match="Unknown __type__"):
        from_dict({"__type__": "GhostConfig", "x": 1})


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


def test_io_error_is_runtime_error() -> None:
    assert issubclass(IoError, RuntimeError)


def test_all_errors_are_io_error_subclasses() -> None:
    subclasses = [
        IoUnavailable,
        IoConnectionError,
        IoNotConnected,
        IoTimeout,
        IoProtocolError,
        IoSignalKindMismatch,
        IoUnknownSignal,
    ]
    for cls in subclasses:
        assert issubclass(cls, IoError), f"{cls.__name__} should be a subclass of IoError"


def test_error_str_returns_message() -> None:
    exc = IoConnectionError("broker refused connection")
    assert "broker refused connection" in str(exc)


def test_each_error_is_instantiable() -> None:
    errors = [
        IoUnavailable("lib missing"),
        IoConnectionError("refused"),
        IoNotConnected("not open"),
        IoTimeout("timed out"),
        IoProtocolError("bad response"),
        IoSignalKindMismatch("wrong type"),
        IoUnknownSignal("no such signal"),
    ]
    for e in errors:
        assert isinstance(e, IoError)


# ---------------------------------------------------------------------------
# Registry — build_adapter (stdlib-only path: ValueError for unknown type)
# ---------------------------------------------------------------------------


def test_build_adapter_unknown_type_raises_value_error() -> None:
    from src.io.registry import build_adapter

    class _FakeConfig:
        protocol = "unknown"

    with pytest.raises(ValueError, match="Unknown connection config type"):
        build_adapter(_FakeConfig())  # type: ignore[arg-type]


def test_build_adapter_modbus_tcp_returns_adapter() -> None:
    """build_adapter with a valid config returns an IoAdapter (requires pymodbus)."""
    pymodbus = pytest.importorskip("pymodbus")  # noqa: F841
    from src.io.adapter import IoAdapter
    from src.io.registry import build_adapter

    cfg = ModbusTcpConfig(host="127.0.0.1", port=502)
    adapter = build_adapter(cfg)
    assert isinstance(adapter, IoAdapter)
