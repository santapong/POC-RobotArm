"""MQTT adapter backed by ``aiomqtt.Client``.

All aiomqtt imports are deferred to method bodies so this module is importable
without the ``[io]`` extra installed.

Notes
-----
* aiomqtt v2 uses an async context manager — ``async with aiomqtt.Client(...) as c``
  opens the connection.  We manage the context lifecycle manually so that
  ``connect()`` and ``disconnect()`` mirror the other adapters.
* Address format: the signal ``address`` is the MQTT topic string, e.g.
  ``"robot/cycles"`` or ``"floor/di0"``.
* Signal values are published / received as plain text (str(value)).  The
  adapter coerces incoming payloads to bool for digital signals or float for
  analog signals.
* ``watch()`` opens a second subscription context and iterates messages via
  ``async for msg in client.messages``, which is natively cancellable.
* ``aiomqtt.MqttError`` (broker not available, connection refused) is mapped
  to :class:`~src.io.errors.IoConnectionError`.
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
from src.io.types import IoEvent, MqttConfig, SignalKind, SignalSpec

__all__ = ["MqttAdapter"]


class MqttAdapter(IoAdapter):
    """MQTT publish/subscribe adapter.

    Parameters
    ----------
    config:
        :class:`~src.io.types.MqttConfig` for this connection.
    """

    def __init__(self, config: MqttConfig) -> None:
        try:
            import aiomqtt  # noqa: F401
        except ImportError as exc:
            raise IoUnavailable(
                "aiomqtt is not installed; run: pip install 'aiomqtt>=2.3,<3'"
            ) from exc
        self._config = config
        self._client: object | None = None
        self._connected = False
        # Topic → latest decoded value; populated by the watch loop.
        self._last_values: dict[str, bool | int | float] = {}

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            supports_subscribe=True,
            supports_write=True,
            supports_analog=True,
        )

    async def connect(self) -> None:
        """Connect to the MQTT broker."""
        import aiomqtt

        kwargs: dict[str, object] = {
            "hostname": self._config.host,
            "port": self._config.port,
            "keepalive": self._config.keepalive_s,
        }
        if self._config.client_id:
            kwargs["identifier"] = self._config.client_id
        if self._config.username is not None:
            kwargs["username"] = self._config.username
        if self._config.password is not None:
            kwargs["password"] = self._config.password

        try:
            client = aiomqtt.Client(**kwargs)  # type: ignore[arg-type]
            await client.__aenter__()
        except (aiomqtt.MqttError, OSError, ConnectionRefusedError) as exc:
            raise IoConnectionError(
                f"MQTT connect to {self._config.host}:{self._config.port} failed: {exc}"
            ) from exc

        self._client = client
        self._connected = True

    async def disconnect(self) -> None:
        """Disconnect from the MQTT broker (idempotent)."""
        self._connected = False
        if self._client is not None:
            try:
                await self._client.__aexit__(None, None, None)  # type: ignore[union-attr]
            except Exception:
                pass
            self._client = None

    def _decode_payload(
        self, payload: bytes | str | bytearray, signal: SignalSpec
    ) -> bool | int | float:
        """Decode an MQTT message payload to the correct Python type."""
        raw = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else str(payload)
        raw = raw.strip()
        if signal.kind in (SignalKind.DIGITAL_IN, SignalKind.DIGITAL_OUT):
            return raw.lower() in ("1", "true", "on", "yes")
        try:
            return float(raw) * signal.scale + signal.offset
        except ValueError:
            return 0.0

    def _encode_payload(self, value: bool | int | float) -> str:
        """Encode a value to an MQTT payload string."""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, int):
            return str(value)
        return str(value)

    async def read(self, signal: SignalSpec) -> IoEvent:
        """Return the last received value for ``signal`` (cached from watch).

        MQTT is push-only; this returns the cached value from the watch loop.
        If no value has been received yet, subscribes once and waits.
        """
        if not self._connected or self._client is None:
            raise IoNotConnected(
                f"MQTT not connected to {self._config.host}:{self._config.port}"
            )
        cached = self._last_values.get(signal.address)
        if cached is not None:
            return IoEvent(
                connection=self._config.host,
                kind="value_changed",
                signal=signal.name,
                value=cached,
                monotonic_s=time.monotonic(),
            )
        # No cached value — subscribe and wait for one message.
        import aiomqtt

        qos = signal.qos if signal.qos is not None else self._config.qos
        try:
            await asyncio.wait_for(
                self._client.subscribe(signal.address, qos=qos),  # type: ignore[union-attr]
                timeout=5.0,
            )
            async with asyncio.timeout(5.0):
                async for msg in self._client.messages:  # type: ignore[union-attr]
                    if str(msg.topic) == signal.address:
                        value = self._decode_payload(msg.payload, signal)  # type: ignore[arg-type]
                        self._last_values[signal.address] = value
                        return IoEvent(
                            connection=self._config.host,
                            kind="value_changed",
                            signal=signal.name,
                            value=value,
                            monotonic_s=time.monotonic(),
                        )
        except asyncio.TimeoutError as exc:
            raise IoTimeout(
                f"MQTT read of topic {signal.address!r} timed out"
            ) from exc
        except aiomqtt.MqttError as exc:
            raise IoProtocolError(f"MQTT read of topic {signal.address!r} failed: {exc}") from exc

        raise IoTimeout(f"MQTT read of topic {signal.address!r}: no message received")

    async def write(self, signal: SignalSpec, value: bool | int | float) -> IoEvent:
        """Publish a value to the signal's MQTT topic."""
        if not self._connected or self._client is None:
            raise IoNotConnected(
                f"MQTT not connected to {self._config.host}:{self._config.port}"
            )
        import aiomqtt

        qos = signal.qos if signal.qos is not None else self._config.qos
        payload = self._encode_payload(value)
        try:
            await asyncio.wait_for(
                self._client.publish(signal.address, payload=payload, qos=qos, retain=True),  # type: ignore[union-attr]
                timeout=5.0,
            )
        except asyncio.TimeoutError as exc:
            raise IoTimeout(
                f"MQTT publish to {signal.address!r} timed out"
            ) from exc
        except aiomqtt.MqttError as exc:
            raise IoProtocolError(
                f"MQTT publish to {signal.address!r} failed: {exc}"
            ) from exc

        return IoEvent(
            connection=self._config.host,
            kind="write_ack",
            signal=signal.name,
            value=value,
            monotonic_s=time.monotonic(),
        )

    async def watch(self, signals: Sequence[SignalSpec]) -> AsyncIterator[IoEvent]:  # type: ignore[override]
        """Subscribe to all signal topics and yield value-changed events.

        Uses aiomqtt's ``async for msg in client.messages`` iteration, which
        is natively cancellable.  ``asyncio.CancelledError`` propagates.
        """
        if not self._connected or self._client is None:
            raise IoNotConnected(
                f"MQTT not connected to {self._config.host}:{self._config.port}"
            )
        if not signals:
            while True:
                await asyncio.sleep(1.0)

        import aiomqtt

        topic_to_signal = {s.address: s for s in signals}
        # Subscribe to all topics.
        for sig in signals:
            qos = sig.qos if sig.qos is not None else self._config.qos
            try:
                await self._client.subscribe(sig.address, qos=qos)  # type: ignore[union-attr]
            except aiomqtt.MqttError as exc:
                raise IoProtocolError(
                    f"MQTT subscribe to {sig.address!r} failed: {exc}"
                ) from exc

        async for msg in self._client.messages:  # type: ignore[union-attr]
            topic = str(msg.topic)
            sig = topic_to_signal.get(topic)
            if sig is None:
                continue
            value = self._decode_payload(msg.payload, sig)  # type: ignore[arg-type]
            self._last_values[topic] = value
            yield IoEvent(
                connection=self._config.host,
                kind="value_changed",
                signal=sig.name,
                value=value,
                monotonic_s=time.monotonic(),
            )
