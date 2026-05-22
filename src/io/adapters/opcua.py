"""OPC-UA adapter backed by ``asyncua.Client``.

All asyncua imports are deferred to method bodies so this module is importable
without the ``[io]`` extra installed.

Notes
-----
* Phase 4 is anonymous-only — no certificate or username/password auth is
  implemented even though :class:`OpcUaConfig` carries those fields.
* Address format — supported variants (see :func:`_parse_opcua_address`):

  * ``"i=42"`` — numeric identifier in default namespace (``config.namespace``).
  * ``"ns=2;i=42"`` — numeric identifier with explicit namespace index.
  * ``"s=MyTag"`` — string identifier in default namespace.
  * ``"ns=2;s=MyTag"`` — string identifier with explicit namespace index.

* OPC-UA natively supports push (monitored items / subscriptions), so
  ``watch()`` uses a subscription rather than polling.  ``asyncio.sleep``
  with a short interval is used as a fallback heartbeat so the generator
  remains cancellable.
* ``ua.UaStatusCodeError`` (write to read-only node, ``BadUserAccessDenied``,
  etc.) is mapped to :class:`~src.io.errors.IoProtocolError`.
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
from src.io.types import IoEvent, OpcUaConfig, SignalSpec

__all__ = ["OpcUaAdapter"]

_HEARTBEAT_S = 0.1  # polling interval for the subscription-based watch loop


class OpcUaAdapter(IoAdapter):
    """OPC-UA client adapter.

    Parameters
    ----------
    config:
        :class:`~src.io.types.OpcUaConfig` for this connection.
    """

    def __init__(self, config: OpcUaConfig) -> None:
        try:
            import asyncua  # noqa: F401
        except ImportError as exc:
            raise IoUnavailable(
                "asyncua is not installed; run: pip install 'asyncua>=1.1,<2'"
            ) from exc
        self._config = config
        self._client: object | None = None
        self._connected = False
        # Populated in connect(): maps (namespace_idx, identifier) → SignalSpec.
        # Built per-connection so the lookup is O(1) and structurally correct.
        self._signal_lookup: dict[tuple[int, str | int], SignalSpec] = {}

    @property
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            supports_subscribe=True,
            supports_write=True,
            supports_analog=True,
        )

    def _parse_opcua_address(self, address: str) -> tuple[int, str | int]:
        """Parse an OPC-UA address string into ``(namespace_idx, identifier)``.

        Supported formats
        -----------------
        * ``"i=42"`` — numeric identifier in default namespace.
        * ``"ns=2;i=42"`` — numeric identifier with explicit namespace.
        * ``"s=MyTag"`` — string identifier in default namespace.
        * ``"ns=2;s=MyTag"`` — string identifier with explicit namespace.

        Returns
        -------
        (namespace_idx, identifier)
            ``namespace_idx`` is an ``int``; ``identifier`` is ``int`` for
            numeric node ids and ``str`` for string node ids.
        """
        ns = self._config.namespace
        rest = address

        if address.startswith("ns="):
            # Split "ns=2;i=42" → ns_part="ns=2", rest="i=42"
            semicolon = address.index(";")
            ns = int(address[3:semicolon])
            rest = address[semicolon + 1 :]

        if "=" not in rest:
            raise ValueError(
                f"OPC-UA address must include 'i=<n>' or 's=<tag>', got {address!r}"
            )
        kind, raw = rest.split("=", 1)
        if kind == "i":
            return ns, int(raw)
        if kind == "s":
            return ns, raw
        raise ValueError(
            f"OPC-UA address kind must be 'i' (numeric) or 's' (string), got {kind!r}"
        )

    def _node_id_from_address(self, address: str) -> object:
        """Build an asyncua NodeId from the address string."""
        from asyncua import ua

        ns, identifier = self._parse_opcua_address(address)
        return ua.NodeId(identifier, ns)

    async def connect(self) -> None:
        """Open the OPC-UA connection."""
        from asyncua import Client
        from asyncua.ua.uaerrors import BadTimeout, UaConnectionError, UaError

        self._client = Client(url=self._config.url)
        try:
            await self._client.connect()  # type: ignore[union-attr]
        except (UaConnectionError, BadTimeout, OSError, ConnectionRefusedError) as exc:
            self._client = None
            raise IoConnectionError(
                f"OPC-UA connect to {self._config.url} failed: {exc}"
            ) from exc
        except UaError as exc:
            self._client = None
            raise IoConnectionError(
                f"OPC-UA connect to {self._config.url} failed: {exc}"
            ) from exc
        self._connected = True

    async def disconnect(self) -> None:
        """Disconnect the OPC-UA client (idempotent)."""
        self._connected = False
        if self._client is not None:
            try:
                await self._client.disconnect()  # type: ignore[union-attr]
            except Exception:
                pass
            self._client = None

    async def _get_node(self, signal: SignalSpec) -> object:
        """Return the asyncua Node object for ``signal``."""
        if self._client is None:
            raise IoNotConnected(f"OPC-UA not connected to {self._config.url}")
        node_id = self._node_id_from_address(signal.address)
        return self._client.get_node(node_id)  # type: ignore[union-attr]

    async def read(self, signal: SignalSpec) -> IoEvent:
        """Read one OPC-UA node value."""
        if not self._connected or self._client is None:
            raise IoNotConnected(f"OPC-UA not connected to {self._config.url}")
        from asyncua.ua.uaerrors import UaError, UaStatusCodeError

        try:
            node = await self._get_node(signal)
            raw = await asyncio.wait_for(
                node.read_value(),  # type: ignore[union-attr]
                timeout=self._config.timeout_s,
            )
        except asyncio.TimeoutError as exc:
            raise IoTimeout(
                f"OPC-UA read of {signal.address} timed out"
            ) from exc
        except UaStatusCodeError as exc:
            raise IoProtocolError(
                f"OPC-UA read of {signal.address} failed: {exc}"
            ) from exc
        except UaError as exc:
            raise IoProtocolError(f"OPC-UA read of {signal.address} failed: {exc}") from exc

        value = self._coerce_value(raw, signal)
        return IoEvent(
            connection=self._config.url,
            kind="value_changed",
            signal=signal.name,
            value=value,
            monotonic_s=time.monotonic(),
        )

    def _coerce_value(self, raw: object, signal: SignalSpec) -> bool | int | float:
        """Coerce the asyncua raw value to bool / int / float per signal kind."""
        from src.io.types import SignalKind

        if signal.kind in (SignalKind.DIGITAL_IN, SignalKind.DIGITAL_OUT):
            return bool(raw)
        # Analog — apply scale and offset.
        try:
            numeric = float(raw)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            numeric = 0.0
        return numeric * signal.scale + signal.offset

    async def write(self, signal: SignalSpec, value: bool | int | float) -> IoEvent:
        """Write a value to an OPC-UA node."""
        if not self._connected or self._client is None:
            raise IoNotConnected(f"OPC-UA not connected to {self._config.url}")
        from asyncua import ua
        from asyncua.ua.uaerrors import UaError, UaStatusCodeError

        try:
            node = await self._get_node(signal)
            dv = ua.DataValue(ua.Variant(value))
            await asyncio.wait_for(
                node.write_value(dv),  # type: ignore[union-attr]
                timeout=self._config.timeout_s,
            )
        except asyncio.TimeoutError as exc:
            raise IoTimeout(
                f"OPC-UA write to {signal.address} timed out"
            ) from exc
        except UaStatusCodeError as exc:
            raise IoProtocolError(
                f"OPC-UA write to {signal.address} failed: {exc}"
            ) from exc
        except UaError as exc:
            raise IoProtocolError(f"OPC-UA write to {signal.address} failed: {exc}") from exc

        return IoEvent(
            connection=self._config.url,
            kind="write_ack",
            signal=signal.name,
            value=value,
            monotonic_s=time.monotonic(),
        )

    async def watch(self, signals: Sequence[SignalSpec]) -> AsyncIterator[IoEvent]:  # type: ignore[override]
        """Subscribe to all signals and yield value-changed events indefinitely.

        Uses OPC-UA monitored items via a ``Subscription`` object.  Falls back
        to a polling heartbeat to remain cancellable between subscription callbacks.
        ``asyncio.CancelledError`` propagates cleanly.
        """
        if not self._connected or self._client is None:
            raise IoNotConnected(f"OPC-UA not connected to {self._config.url}")
        if not signals:
            while True:
                await asyncio.sleep(1.0)

        from asyncua.ua.uaerrors import UaError

        # Build a structural lookup: (namespace_idx, identifier) → SignalSpec.
        # This avoids the substring-match bug — "i=2" must NOT match "ns=2;i=12".
        sig_lookup: dict[tuple[int, str | int], SignalSpec] = {
            self._parse_opcua_address(s.address): s for s in signals
        }

        # Queue receives events from the subscription callback (thread-safe path
        # via call_soon_threadsafe in the asyncua callback).
        queue: asyncio.Queue[IoEvent] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        class _Handler:
            """asyncua subscription handler that forwards data changes to the queue."""

            def __init__(self, conn: str, lookup: dict[tuple[int, str | int], SignalSpec]) -> None:
                self._conn = conn
                self._lookup = lookup

            def datachange_notification(
                self, node: object, val: object, data: object
            ) -> None:
                # Called from asyncua's internal task — use call_soon_threadsafe.
                try:
                    nid = node.nodeid  # type: ignore[union-attr]
                    key = (nid.NamespaceIndex, nid.Identifier)
                    sig = self._lookup.get(key)
                    if sig is None:
                        return
                    from src.io.types import SignalKind

                    if sig.kind in (SignalKind.DIGITAL_IN, SignalKind.DIGITAL_OUT):
                        coerced: bool | int | float = bool(val)
                    else:
                        coerced = float(val) * sig.scale + sig.offset  # type: ignore[arg-type]

                    event = IoEvent(
                        connection=self._conn,
                        kind="value_changed",
                        signal=sig.name,
                        value=coerced,
                        monotonic_s=time.monotonic(),
                    )
                    loop.call_soon_threadsafe(queue.put_nowait, event)
                except Exception:
                    pass  # Never raise in a subscription callback

        handler = _Handler(conn=self._config.url, lookup=sig_lookup)
        subscription: object | None = None
        try:
            subscription = await self._client.create_subscription(  # type: ignore[union-attr]
                period=500, handler=handler
            )
            nodes = [await self._get_node(s) for s in signals]
            await subscription.subscribe_data_change(nodes)  # type: ignore[union-attr]
        except UaError as exc:
            if subscription is not None:
                try:
                    await subscription.delete()  # type: ignore[union-attr]
                except Exception:
                    pass
            raise IoProtocolError(f"OPC-UA subscription failed: {exc}") from exc

        try:
            while True:
                try:
                    event = queue.get_nowait()
                    yield event
                except asyncio.QueueEmpty:
                    await asyncio.sleep(_HEARTBEAT_S)
        finally:
            if subscription is not None:
                try:
                    await subscription.delete()  # type: ignore[union-attr]
                except Exception:
                    pass
