"""Tests for MqttAdapter + mqtt_broker sim.

Gates:
- pytest.importorskip("aiomqtt")
- Skip module if mosquitto not in PATH (via session-scoped fixture)

Covers:
- Connect + publish + subscribe round-trip
- broker_down yields IoConnectionError (risk #13)
- QoS=1 redelivery after broker restart (risk #2)
- MqttAdapter.read() without prior watch raises IoNotConnected
"""

from __future__ import annotations

import asyncio
import shutil
import time

import pytest

aiomqtt = pytest.importorskip("aiomqtt")

pytestmark = pytest.mark.io

from src.io.adapters.mqtt import MqttAdapter  # noqa: E402
from src.io.errors import IoConnectionError, IoNotConnected  # noqa: E402
from src.io.simulators.mqtt_broker import find_free_port, start_mqtt_broker  # noqa: E402
from src.io.types import MqttConfig, SignalKind, SignalSpec  # noqa: E402

# ---------------------------------------------------------------------------
# Module-level mosquitto gate
# ---------------------------------------------------------------------------


def _mosquitto_available() -> bool:
    return shutil.which("mosquitto") is not None


# Apply a skip if mosquitto is not available
if not _mosquitto_available():
    pytestmark = [
        pytest.mark.io,
        pytest.mark.skip(reason="mosquitto binary not in PATH"),
    ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _digital_signal(name: str, topic: str) -> SignalSpec:
    return SignalSpec(name=name, kind=SignalKind.DIGITAL_OUT, address=topic)


def _analog_signal(name: str, topic: str) -> SignalSpec:
    return SignalSpec(name=name, kind=SignalKind.ANALOG_OUT, address=topic)


# ---------------------------------------------------------------------------
# Risk #13 — broker not running yields IoConnectionError
# ---------------------------------------------------------------------------


def test_broker_down_yields_connection_error() -> None:
    """Connecting to a non-running broker raises IoConnectionError (risk #13)."""

    async def _run():
        port = find_free_port()
        cfg = MqttConfig(host="127.0.0.1", port=port, client_id="test", timeout_s=3.0)
        adapter = MqttAdapter(cfg)

        t0 = time.monotonic()
        with pytest.raises(IoConnectionError):
            await adapter.connect()
        elapsed = time.monotonic() - t0
        assert elapsed < 5.0, (
            f"connect() to downed broker took {elapsed:.2f} s; expected < 5 s"
        )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Connect + publish + subscribe round-trip
# ---------------------------------------------------------------------------


def test_mqtt_connect_publish_subscribe_round_trip() -> None:
    async def _run():
        async with start_mqtt_broker() as (host, port):
            # Publisher adapter
            pub_cfg = MqttConfig(
                host=host, port=port, client_id="pub_client", timeout_s=5.0
            )
            pub = MqttAdapter(pub_cfg)
            await pub.connect()

            # Subscriber adapter
            sub_cfg = MqttConfig(
                host=host, port=port, client_id="sub_client", timeout_s=5.0
            )
            sub = MqttAdapter(sub_cfg)
            await sub.connect()

            topic = "test/roundtrip"
            sig = _digital_signal("relay", topic)

            received_events: list = []

            async def _watch():
                async for ev in sub.watch([sig]):
                    received_events.append(ev)
                    return

            watch_task = asyncio.create_task(_watch())
            await asyncio.sleep(0.1)  # Allow subscription to register

            # Publish
            await pub.write(sig, True)

            deadline = time.monotonic() + 5.0
            while not received_events and time.monotonic() < deadline:
                await asyncio.sleep(0.05)

            watch_task.cancel()
            try:
                await watch_task
            except (asyncio.CancelledError, Exception):
                pass

            assert received_events, "Subscriber did not receive published message"
            ev = received_events[0]
            assert ev.kind == "value_changed"
            assert ev.signal == "relay"
            # Payload "true" decoded as bool True for digital signal
            assert ev.value is True

            await pub.disconnect()
            await sub.disconnect()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# MqttAdapter.read() without prior watch raises IoNotConnected
# ---------------------------------------------------------------------------


def test_mqtt_read_without_watch_raises_not_connected() -> None:
    """read() before watch() has cached a value raises IoNotConnected."""

    async def _run():
        async with start_mqtt_broker() as (host, port):
            cfg = MqttConfig(host=host, port=port, client_id="reader", timeout_s=5.0)
            adapter = MqttAdapter(cfg)
            await adapter.connect()

            sig = _digital_signal("unseen_signal", "no/prior/watch")
            with pytest.raises(IoNotConnected, match="not yet seen"):
                await adapter.read(sig)

            await adapter.disconnect()

    asyncio.run(_run())


def test_mqtt_read_not_connected_raises() -> None:
    """read() when not connected raises IoNotConnected."""

    async def _run():
        cfg = MqttConfig(host="127.0.0.1", port=1883, client_id="r")
        adapter = MqttAdapter(cfg)
        sig = _digital_signal("s", "t")
        with pytest.raises(IoNotConnected):
            await adapter.read(sig)

    asyncio.run(_run())


def test_mqtt_write_not_connected_raises() -> None:
    async def _run():
        cfg = MqttConfig(host="127.0.0.1", port=1883, client_id="w")
        adapter = MqttAdapter(cfg)
        sig = _digital_signal("s", "t")
        with pytest.raises(IoNotConnected):
            await adapter.write(sig, True)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Risk #2 — QoS=1 redelivery semantics
# ---------------------------------------------------------------------------


def test_qos_1_redelivery_after_broker_restart() -> None:
    """QoS=1 retained-message redelivery to a new subscriber (risk #2).

    Scenario (Option A — retained message):
    1. Start ONE broker.
    2. Publisher A connects, publishes payload="42.0" to "test/retain" with
       qos=1 and retain=True, then disconnects.
    3. Subscriber B (brand-new client_id) connects and subscribes to "test/retain"
       with qos=1.
    4. Assert: B receives the retained "42.0" within timeout.

    This exercises the retained-state semantics that operators rely on (risk #2):
    any subscriber that connects after the fact still receives the last retained
    value, regardless of whether the original publisher is still connected.

    Full durable-session redelivery (clean_session=False) is not tested here
    because aiomqtt v2 does not expose clean_session directly.  That scenario
    is noted as risk #2 / untested-in-CI.
    """

    async def _run():
        async with start_mqtt_broker() as (host, port):
            topic = "test/retain"
            sig_pub = SignalSpec(
                name="cycle_count",
                kind=SignalKind.ANALOG_OUT,
                address=topic,
                qos=1,
            )

            # --- Phase 1: Publish with retain=True ---
            pub_cfg = MqttConfig(
                host=host, port=port, client_id="pub_retain", timeout_s=5.0, qos=1
            )
            pub = MqttAdapter(pub_cfg)
            await pub.connect()

            ev = await pub.write(sig_pub, 42.0)
            assert ev.kind == "write_ack", (
                f"Expected write_ack from QoS=1 publish, got {ev.kind!r}"
            )
            assert abs(float(ev.value) - 42.0) < 0.01  # type: ignore[arg-type]

            # Give mosquitto time to persist the retained message
            await asyncio.sleep(0.1)
            await pub.disconnect()

            # --- Phase 2: NEW subscriber connects AFTER publisher is gone ---
            # It must receive the retained "42.0" without any new publish.
            sig_sub = SignalSpec(
                name="cycle_count",
                kind=SignalKind.ANALOG_OUT,
                address=topic,
                qos=1,
            )
            sub_cfg = MqttConfig(
                host=host, port=port, client_id="sub_retain_new", timeout_s=5.0, qos=1
            )
            sub = MqttAdapter(sub_cfg)
            await sub.connect()

            events: list = []

            async def _watch():
                async for ev in sub.watch([sig_sub]):
                    events.append(ev)
                    return  # stop after first event

            watch_task = asyncio.create_task(_watch())

            deadline = time.monotonic() + 5.0
            while not events and time.monotonic() < deadline:
                await asyncio.sleep(0.05)

            watch_task.cancel()
            try:
                await watch_task
            except (asyncio.CancelledError, Exception):
                pass

            assert events, (
                "QoS=1 retained message was NOT delivered to a new subscriber.  "
                "Risk #2: operators rely on retained-state semantics — a new subscriber "
                "must receive the last retained value without waiting for a re-publish."
            )
            assert abs(float(events[0].value) - 42.0) < 0.01, (  # type: ignore[arg-type]
                f"Retained value mismatch: expected 42.0, got {events[0].value!r}"
            )

            await sub.disconnect()

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


def test_mqtt_capabilities() -> None:
    cfg = MqttConfig(host="b", client_id="c")
    adapter = MqttAdapter(cfg)
    caps = adapter.capabilities
    assert caps.supports_subscribe is True
    assert caps.supports_write is True
    assert caps.supports_analog is True


# ---------------------------------------------------------------------------
# Payload encoding / decoding
# ---------------------------------------------------------------------------


def test_mqtt_decode_payload_digital_true() -> None:
    cfg = MqttConfig(host="b", client_id="c")
    adapter = MqttAdapter(cfg)
    sig = _digital_signal("s", "t")
    for val in ("1", "true", "True", "on", "yes"):
        assert adapter._decode_payload(val.encode(), sig) is True


def test_mqtt_decode_payload_digital_false() -> None:
    cfg = MqttConfig(host="b", client_id="c")
    adapter = MqttAdapter(cfg)
    sig = _digital_signal("s", "t")
    for val in ("0", "false", "off", "no"):
        assert adapter._decode_payload(val.encode(), sig) is False


def test_mqtt_decode_payload_analog() -> None:
    cfg = MqttConfig(host="b", client_id="c")
    adapter = MqttAdapter(cfg)
    sig = _analog_signal("ao", "t")
    result = adapter._decode_payload(b"3.14", sig)
    assert abs(result - 3.14) < 1e-9


def test_mqtt_encode_payload_bool() -> None:
    cfg = MqttConfig(host="b", client_id="c")
    adapter = MqttAdapter(cfg)
    assert adapter._encode_payload(True) == "true"
    assert adapter._encode_payload(False) == "false"


# ---------------------------------------------------------------------------
# Extra coverage: disconnect is idempotent
# ---------------------------------------------------------------------------


# Extra coverage: double disconnect must not raise
def test_mqtt_disconnect_idempotent() -> None:
    async def _run():
        cfg = MqttConfig(host="127.0.0.1", port=1883, client_id="d")
        adapter = MqttAdapter(cfg)
        await adapter.disconnect()
        await adapter.disconnect()

    asyncio.run(_run())
