import asyncio
import json
import logging
import time
import websockets

class WSStreamClient:
    STREAM_URL = "wss://stream.binance.com:9443/ws"
    STREAM_URL_TESTNET = "wss://testnet.binance.vision/ws"

    def __init__(self, config):
        self.config = config
        self.use_testnet = config.get("USE_TESTNET", False)
        self.stream_url = self.STREAM_URL_TESTNET if self.use_testnet else self.STREAM_URL
        self.logger = logging.getLogger(__name__)
        self.websocket = None
        self.connected = False
        self.last_price = {}
        self._listen_task = None
        self._reconnect_task = None
        self._subscribed_symbols = set()

    # Bound initial connect attempts so a dead network fails fast into REST fallback
    # instead of hanging main() startup forever. Reconnect-after-drop uses its own
    # longer backoff loop (_reconnect_loop).
    MAX_CONNECT_ATTEMPTS = 5

    async def connect(self, symbols):
        if len(symbols) > 500:
            self.logger.warning(f"Too many symbols ({len(symbols)}). Limit to 500.")
            symbols = symbols[:500]
        last_error = None
        for attempt in range(1, self.MAX_CONNECT_ATTEMPTS + 1):
            try:
                self.logger.info(f"Connecting to WebSocket Stream (attempt {attempt}/{self.MAX_CONNECT_ATTEMPTS}) for symbols: {symbols}")
                self.websocket = await websockets.connect(self.stream_url, ping_interval=20, ping_timeout=10)
                self.connected = True
                streams = []
                for symbol in symbols:
                    sym_lower = symbol.lower()
                    streams.append(f"{sym_lower}@aggTrade")
                    streams.append(f"{sym_lower}@kline_{self.config['TIMEFRAME']}")
                await self.websocket.send(json.dumps({"method": "SUBSCRIBE", "params": streams, "id": 1}))
                resp = await asyncio.wait_for(self.websocket.recv(), timeout=10)
                if '"result":null' in resp and '"error"' in resp:
                    raise Exception(f"Subscription error: {resp}")
                self._subscribed_symbols = set(symbols)
                self.logger.info(f"Subscribed to {len(symbols)} symbols.")
                self._listen_task = asyncio.create_task(self._listen())
                return
            except Exception as e:
                last_error = e
                self.logger.error(f"Stream connection attempt {attempt} failed: {e}")
                await self.disconnect()
                if attempt < self.MAX_CONNECT_ATTEMPTS:
                    await asyncio.sleep(min(2 ** attempt, 30))
        self.logger.error(
            f"WebSocket Stream unavailable after {self.MAX_CONNECT_ATTEMPTS} attempts ({last_error}). "
            "Continuing with REST price polling; background reconnects will retry."
        )

    async def subscribe(self, symbols):
        if not self.is_connected():
            return
        new_syms = [s for s in symbols if s not in self._subscribed_symbols]
        if not new_syms:
            return
        streams = []
        for symbol in new_syms:
            sym_lower = symbol.lower()
            streams.append(f"{sym_lower}@aggTrade")
            streams.append(f"{sym_lower}@kline_{self.config['TIMEFRAME']}")
        await self.websocket.send(json.dumps({"method": "SUBSCRIBE", "params": streams, "id": int(time.time()*1000)}))
        self._subscribed_symbols.update(new_syms)

    async def unsubscribe(self, symbols):
        if not self.is_connected():
            return
        remove_syms = [s for s in symbols if s in self._subscribed_symbols]
        if not remove_syms:
            return
        streams = []
        for symbol in remove_syms:
            sym_lower = symbol.lower()
            streams.append(f"{sym_lower}@aggTrade")
            streams.append(f"{sym_lower}@kline_{self.config['TIMEFRAME']}")
        await self.websocket.send(json.dumps({"method": "UNSUBSCRIBE", "params": streams, "id": int(time.time()*1000)}))
        for s in remove_syms:
            self._subscribed_symbols.discard(s)

    async def disconnect(self):
        current_task = asyncio.current_task()
        if self._reconnect_task and self._reconnect_task is not current_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
            self._reconnect_task = None
        if self._listen_task and self._listen_task is not current_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None
        if self.websocket:
            # Bounded close: a listener cancelled mid-`recv()` can leave the
            # connection's `connection_lost_waiter` unset, which would otherwise
            # hang `websocket.close()` forever and wedge the engine's shutdown.
            try:
                await asyncio.wait_for(self.websocket.close(), timeout=3.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self.logger.warning("WebSocket close timed out during disconnect; aborting connection.")
            except Exception:
                pass
            finally:
                try:
                    transport = getattr(self.websocket, "transport", None)
                    if transport is not None:
                        transport.abort()
                except Exception:
                    pass
            self.websocket = None
        self.connected = False
        self._subscribed_symbols.clear()

    def is_connected(self):
        if not self.connected or self.websocket is None:
            return False
        try:
            # Modern websockets (v12+ / v13+ / v14+ / v15+): uses State enum
            state = getattr(self.websocket, "state", None)
            if state is not None:
                state_name = getattr(state, "name", str(state))
                return state_name == "OPEN" or state == 1 or "OPEN" in str(state)
            # Legacy websockets: .open or .closed attribute
            if hasattr(self.websocket, "open"):
                return bool(self.websocket.open)
            if hasattr(self.websocket, "closed"):
                return not bool(self.websocket.closed)
        except Exception:
            pass
        return self.connected

    async def _listen(self):
        while self.connected:
            try:
                msg = await self.websocket.recv()
                data = json.loads(msg)
                await self._process(data)
            except (websockets.exceptions.ConnectionClosed, websockets.exceptions.WebSocketException, OSError, asyncio.TimeoutError) as e:
                self.connected = False
                self.logger.warning(f"WebSocket Stream disconnected ({e}). Reconnecting...")
                # Reconnect on a fresh socket object. Calling self.connect() directly
                # here would block the listener and, worse, self.connect() reassigns
                # self.websocket while this coroutine still holds the dead one.
                if not self._reconnect_task or self._reconnect_task.done():
                    self._reconnect_task = asyncio.create_task(
                        self._reconnect_loop(list(self._subscribed_symbols))
                    )
                break
            except asyncio.CancelledError:
                break

    async def _reconnect_loop(self, symbols):
        """Exponential-backoff reconnect that always builds a fresh websocket.
        NOTE: deliberately avoids self.disconnect() — it would cancel this very task."""
        self.connected = False
        if self._listen_task:
            self._listen_task = None
        for attempt in range(1, 8):
            try:
                if self.websocket:
                    try:
                        await self.websocket.close()
                    except Exception:
                        pass
                    self.websocket = None
                await self.connect(symbols)
                if self.connected:
                    self.logger.info("WebSocket Stream reconnected successfully.")
                    return
            except Exception as e:
                self.logger.warning(f"Stream reconnect attempt {attempt} failed: {e}")
            await asyncio.sleep(min(2 ** attempt, 60))
        self.logger.error("WebSocket Stream reconnect abandoned after repeated failures; price reads fall back to REST.")

    async def _process(self, data):
        e = data.get("e")
        if e == "aggTrade":
            symbol = data.get("s")
            if symbol:
                self.last_price[symbol] = {"price": float(data.get("p", 0)), "time": int(time.time() * 1000)}
        # Kline events are intentionally not cached: the engine reads OHLCV straight
        # from REST when needed (signal generation, ATR refresh, gap checks) and a
        # websocket-side kline buffer was never read by any consumer.

    async def get_current_price(self, symbol):
        entry = self.last_price.get(symbol)
        if entry and (int(time.time() * 1000) - entry["time"] < 5000):
            return entry["price"]
        return None
