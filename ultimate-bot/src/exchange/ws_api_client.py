import asyncio
import json
import logging
import time
import base64
import aiohttp
import websockets
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

class WSApiClient:
    WS_URL = "wss://ws-api.binance.com:443/ws-api/v3"
    WS_URL_TESTNET = "wss://testnet.binance.vision/ws-api/v3"

    def __init__(self, config):
        self.config = config
        self.api_key = config["API_KEY"]
        self.private_key_path = config["PRIVATE_KEY_PATH"]
        self.use_testnet = config.get("USE_TESTNET", False)
        self.ws_url = self.WS_URL_TESTNET if self.use_testnet else self.WS_URL
        self.base_url = "https://testnet.binance.vision" if self.use_testnet else "https://api.binance.com"
        self.logger = logging.getLogger(__name__)
        self.websocket = None
        self.connected = False
        self.request_id = 1
        self.time_offset = 0
        self._session = None
        self._private_key = None
        self._monitor_task = None
        self._lock = asyncio.Lock()
        if not config.get("PAPER_TRADE", False):
            with open(self.private_key_path, "rb") as f:
                key = serialization.load_pem_private_key(f.read(), password=None)
            if not isinstance(key, Ed25519PrivateKey):
                raise ValueError("Not Ed25519")
            self._private_key = key

    async def _get_session(self):
        if not self._session:
            self._session = aiohttp.ClientSession()
        return self._session

    async def _get_server_time(self):
        session = await self._get_session()
        async with session.get(f"{self.base_url}/api/v3/time") as resp:
            data = await resp.json()
            return data["serverTime"]

    async def connect(self):
        retry_count = 0
        while True:
            try:
                self.logger.info(f"Connecting to WebSocket API (attempt {retry_count+1})...")
                self.websocket = await websockets.connect(self.ws_url, ping_interval=20, ping_timeout=10)
                self.connected = True
                await self.logon()
                self.logger.info("WebSocket API connected and authenticated.")
                self._monitor_task = asyncio.create_task(self._monitor_connection())
                return
            except Exception as e:
                self.logger.error(f"WebSocket API connection failed: {e}")
                await self.disconnect()
                retry_count += 1
                if retry_count > 5:
                    raise
                await asyncio.sleep(min(2 ** retry_count, 30))

    async def disconnect(self):
        current_task = asyncio.current_task()
        if self._monitor_task and self._monitor_task is not current_task:
            self._monitor_task.cancel()
            self._monitor_task = None
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception:
                pass
            self.websocket = None
            self.connected = False
        if self._session:
            await self._session.close()
            self._session = None

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

    async def _monitor_connection(self):
        while self.connected:
            await asyncio.sleep(15)
            if not self.is_connected():
                self.logger.warning("WebSocket API connection lost. Reconnecting...")
                self.connected = False
                await self.connect()
                break

    async def send_request(self, method, params=None):
        async with self._lock:
            req_id = str(self.request_id)
            self.request_id += 1
            payload = {"id": req_id, "method": method, "params": params or {}}
            await self.websocket.send(json.dumps(payload))
            tries = 0
            max_tries = 20
            while tries < max_tries:
                tries += 1
                try:
                    resp = await asyncio.wait_for(self.websocket.recv(), timeout=5)
                except asyncio.TimeoutError:
                    if tries >= max_tries:
                        self.logger.error("WebSocket API request timed out after retries")
                        raise
                    continue
                data = json.loads(resp)
                if data.get("id") == req_id:
                    if data.get("status") != 200:
                        raise Exception(f"API error {data.get('status')}: {data.get('error')}")
                    return data

    async def logon(self):
        server_time = await self._get_server_time()
        self.time_offset = server_time - int(time.time() * 1000)
        params = {"timestamp": server_time, "apiKey": self.api_key}
        query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
        if not self._private_key:
            raise Exception("Private key not available")
        params["signature"] = self._sign_ed25519(query_string)
        result = await self.send_request("session.logon", params)
        if result.get("status") != 200:
            raise Exception(f"session.logon failed: {result}")

    def _sign_ed25519(self, message):
        return base64.b64encode(self._private_key.sign(message.encode())).decode()

    async def place_order(self, symbol, side, order_type, quantity):
        qty_str = f"{quantity:f}" if isinstance(quantity, float) else str(quantity)
        if "." in qty_str:
            qty_str = qty_str.rstrip("0").rstrip(".")
        if not qty_str:
            qty_str = "0"
        params = {"symbol": symbol, "side": side, "type": order_type, "quantity": qty_str,
                  "timestamp": int(time.time() * 1000) + self.time_offset, "apiKey": self.api_key}
        query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
        params["signature"] = self._sign_ed25519(query_string)
        return await self.send_request("order.place", params)

    async def cancel_order(self, symbol, order_id):
        params = {"symbol": symbol, "orderId": order_id,
                  "timestamp": int(time.time() * 1000) + self.time_offset, "apiKey": self.api_key}
        query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
        params["signature"] = self._sign_ed25519(query_string)
        return await self.send_request("order.cancel", params)
