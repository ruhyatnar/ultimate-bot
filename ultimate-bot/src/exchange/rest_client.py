import asyncio
import time
import base64
import json
import logging
from urllib.parse import urlencode
import aiohttp
from aiolimiter import AsyncLimiter
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from src.core.backoff import async_retry

class RestClient:
    BASE_URL = "https://api.binance.com"
    BASE_URL_TESTNET = "https://testnet.binance.vision"

    def __init__(self, config):
        self.config = config
        self.api_key = config["API_KEY"]
        self.private_key_path = config["PRIVATE_KEY_PATH"]
        self.use_testnet = config.get("USE_TESTNET", False)
        self.base_url = self.BASE_URL_TESTNET if self.use_testnet else self.BASE_URL
        self.logger = logging.getLogger(__name__)
        self.session = None
        self.limiter = AsyncLimiter(config.get("REST_WEIGHT_LIMIT", 1200), 60)
        self.exchange_info_cache = {}
        self.symbol_info_cache = {}
        self.timeout = aiohttp.ClientTimeout(total=15)
        self.time_offset = 0
        self.last_time_sync = 0
        self._private_key = None
        self._initialized = False
        self._init_lock = asyncio.Lock()
        if not config.get("PAPER_TRADE", False):
            with open(self.private_key_path, "rb") as f:
                key = serialization.load_pem_private_key(f.read(), password=None)
            if not isinstance(key, Ed25519PrivateKey):
                raise ValueError("Private key is not Ed25519")
            self._private_key = key

    async def _ensure_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession(timeout=self.timeout)

    async def _load_exchange_info(self):
        if self.exchange_info_cache:
            return
        data = await self._request_internal("GET", "/api/v3/exchangeInfo")
        self.exchange_info_cache = data
        for s in data.get("symbols", []):
            self.symbol_info_cache[s["symbol"]] = s
        self.logger.info(f"Exchange Info cached for {len(self.symbol_info_cache)} symbols.")

    async def init(self):
        async with self._init_lock:
            if self._initialized:
                return
            await self._ensure_session()
            await self.sync_time()
            await self._load_exchange_info()
            self._initialized = True
            asyncio.create_task(self._periodic_time_sync())

    async def _periodic_time_sync(self):
        while True:
            await asyncio.sleep(600)
            try:
                await self.sync_time()
            except Exception as e:
                self.logger.warning(f"Periodic time sync failed: {e}")

    async def close(self):
        if self.session:
            await self.session.close()
            self.session = None
            self._initialized = False

    async def sync_time(self):
        try:
            resp = await self._request_internal("GET", "/api/v3/time")
            self.time_offset = resp["serverTime"] - int(time.time() * 1000)
            self.last_time_sync = int(time.time())
            self.logger.debug(f"Time offset set to {self.time_offset} ms")
        except Exception as e:
            self.logger.warning(f"Time sync failed: {e}")

    async def _get_timestamp(self):
        if self.time_offset == 0 or (int(time.time()) - self.last_time_sync) > 300:
            await self.sync_time()
        return int(time.time() * 1000) + self.time_offset

    async def _request_internal(self, method, endpoint, params=None, signed=False):
        await self._ensure_session()
        url = f"{self.base_url}{endpoint}"
        headers = {"X-MBX-APIKEY": self.api_key} if self.api_key else {}
        if params is None:
            params = {}
        if signed:
            params["timestamp"] = await self._get_timestamp()
            query_string = urlencode(sorted(params.items()))
            if not self._private_key:
                raise Exception("Private key not available for signing.")
            params["signature"] = self._sign_ed25519(query_string)
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        async with self.limiter:
            async with self.session.request(method, url, params=params, headers=headers) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    self.logger.error(f"REST error {resp.status}: {text}")
                    try:
                        data = json.loads(text)
                        code = data.get("code")
                        msg = data.get("msg", "")
                        if code == -1021:
                            await self.sync_time()
                            raise Exception("Timestamp error, retry after sync")
                        elif code == -2010:
                            raise Exception("Insufficient balance")
                        elif "maintenance" in msg.lower() or "system busy" in msg.lower():
                            raise Exception("Exchange maintenance")
                    except json.JSONDecodeError:
                        pass
                    raise Exception(f"REST error {resp.status}: {text}")
                return await resp.json()

    async def _request(self, method, endpoint, params=None, signed=False):
        return await self._request_with_retry(method, endpoint, params, signed)

    @async_retry(max_retries=3, backoff=2)
    async def _request_with_retry(self, method, endpoint, params, signed):
        return await self._request_internal(method, endpoint, params, signed)

    def _sign_ed25519(self, message: str) -> str:
        return base64.b64encode(self._private_key.sign(message.encode())).decode()

    async def ping(self):
        return await self._request("GET", "/api/v3/ping")

    async def get_symbol_info(self, symbol):
        await self._load_exchange_info()
        return self.symbol_info_cache.get(symbol)

    async def get_filters(self, symbol):
        info = await self.get_symbol_info(symbol)
        return {f["filterType"]: f for f in info.get("filters", [])}

    async def get_ticker(self, symbol):
        return await self._request("GET", "/api/v3/ticker/price", {"symbol": symbol})

    async def get_24hr_tickers(self):
        return await self._request("GET", "/api/v3/ticker/24hr")

    async def get_klines(self, symbol, interval, limit=500):
        return await self._request("GET", "/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})

    async def get_account(self):
        return await self._request("GET", "/api/v3/account", signed=True)

    async def get_order(self, symbol, order_id):
        return await self._request("GET", "/api/v3/order", {"symbol": symbol, "orderId": order_id}, signed=True)

    async def place_order(self, symbol, side, order_type, quantity):
        qty_str = f"{quantity:f}" if isinstance(quantity, float) else str(quantity)
        if "." in qty_str:
            qty_str = qty_str.rstrip("0").rstrip(".")
        params = {"symbol": symbol, "side": side, "type": order_type, "quantity": qty_str}
        return await self._request("POST", "/api/v3/order", params, signed=True)

    async def cancel_order(self, symbol, order_id):
        return await self._request("DELETE", "/api/v3/order", {"symbol": symbol, "orderId": order_id}, signed=True)
