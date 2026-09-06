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
        self.klines_cache = {}
        self._listen_task = None
        self.max_klines_per_symbol = 500
        self._subscribed_symbols = set()

    async def connect(self, symbols):
        if len(symbols) > 500:
            self.logger.warning(f"Too many symbols ({len(symbols)}). Limit to 500.")
            symbols = symbols[:500]
        while True:
            try:
                self.logger.info(f"Connecting to WebSocket Stream for symbols: {symbols}")
                self.websocket = await websockets.connect(self.stream_url, ping_interval=20, ping_timeout=10)
                self.connected = True
                streams = []
                for symbol in symbols:
                    sym_lower = symbol.lower()
                    streams.append(f"{sym_lower}@aggTrade")
                    streams.append(f"{sym_lower}@kline_{self.config['TIMEFRAME']}")
                await self.websocket.send(json.dumps({"method": "SUBSCRIBE", "params": streams, "id": 1}))
                resp = await self.websocket.recv()
                if '"result":null' in resp and '"error"' in resp:
                    raise Exception(f"Subscription error: {resp}")
                self._subscribed_symbols = set(symbols)
                self.logger.info(f"Subscribed to {len(symbols)} symbols.")
                self._listen_task = asyncio.create_task(self._listen())
                return
            except Exception as e:
                self.logger.error(f"Stream connection failed: {e}")
                await self.disconnect()
                await asyncio.sleep(5)

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
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
            self._listen_task = None
        if self.websocket:
            await self.websocket.close()
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
            except websockets.exceptions.ConnectionClosed:
                self.connected = False
                self.logger.warning("WebSocket Stream connection closed.")
                asyncio.create_task(self.connect(list(self._subscribed_symbols)))
                break
            except asyncio.CancelledError:
                break

    async def _process(self, data):
        e = data.get("e")
        if e == "aggTrade":
            symbol = data.get("s")
            if symbol:
                self.last_price[symbol] = {"price": float(data.get("p", 0)), "time": int(time.time() * 1000)}
        elif e == "kline":
            symbol = data.get("s")
            k = data.get("k")
            if symbol and k and k.get("x") is True:
                if symbol not in self.klines_cache:
                    self.klines_cache[symbol] = []
                self.klines_cache[symbol].append(k)
                if len(self.klines_cache[symbol]) > self.max_klines_per_symbol:
                    self.klines_cache[symbol] = self.klines_cache[symbol][-self.max_klines_per_symbol:]

    async def get_current_price(self, symbol):
        entry = self.last_price.get(symbol)
        if entry and (int(time.time() * 1000) - entry["time"] < 5000):
            return entry["price"]
        return None
