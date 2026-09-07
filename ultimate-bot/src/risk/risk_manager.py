import json
import logging
from datetime import datetime, timezone
from decimal import Decimal

class RiskManager:
    def __init__(self, config, db, rest):
        self.config = config
        self.db = db
        self.rest = rest
        self.logger = logging.getLogger(__name__)
        self.daily_pnl = 0.0
        self.last_reset_date = None
        self.symbol_states = {}
        self.total_equity = 0.0
        self.unrealized_pnl = 0.0
        self.paper_balance = 1000.0

    async def load_state(self):
        daily_pnl_str = await self.db.get_risk_state("daily_pnl")
        if daily_pnl_str: self.daily_pnl = float(daily_pnl_str)
        last_reset = await self.db.get_risk_state("last_reset_date")
        if last_reset: self.last_reset_date = datetime.fromisoformat(last_reset)
        paper_balance_str = await self.db.get_risk_state("paper_balance")
        if paper_balance_str: self.paper_balance = float(paper_balance_str)
        for symbol in self.config["STATIC_SYMBOLS"]:
            val = await self.db.get_risk_state(f"risk_{symbol}")
            self.symbol_states[symbol] = json.loads(val) if val else {"loss_streak":0, "win_streak":0, "cooldown_until":0}
        if self.config.get("PAPER_TRADE", False):
            self.total_equity = self.paper_balance
            self.logger.info(f"Paper trading mode: simulated equity {self.total_equity} USDT.")
        else:
            await self._fetch_equity()

    async def _fetch_equity(self):
        account = await self.rest.get_account()
        total_equity = 0.0
        for b in account["balances"]:
            asset = b["asset"]
            free = float(b["free"]) + float(b["locked"])
            if free <= 0: continue
            if asset == self.config["QUOTE_ASSET"]:
                total_equity += free
            else:
                symbol = asset + self.config["QUOTE_ASSET"]
                try:
                    ticker = await self.rest.get_ticker(symbol)
                    total_equity += free * float(ticker["price"])
                except Exception:
                    pass
        self.total_equity = total_equity

    async def save_state(self):
        await self.db.set_risk_state("daily_pnl", str(self.daily_pnl))
        if self.last_reset_date:
            await self.db.set_risk_state("last_reset_date", self.last_reset_date.isoformat())
        await self.db.set_risk_state("unrealized_pnl", str(self.unrealized_pnl))
        for symbol, state in self.symbol_states.items():
            await self.db.set_risk_state(f"risk_{symbol}", json.dumps(state))
        if self.config.get("PAPER_TRADE", False):
            self.paper_balance = self.total_equity
            await self.db.set_risk_state("paper_balance", str(self.paper_balance))

    async def check_risk(self, symbol, unrealized_pnl=0.0):
        self.unrealized_pnl = unrealized_pnl
        await self._reset_daily_if_needed()
        total_loss = self.daily_pnl + self.unrealized_pnl
        self.logger.debug(f"Risk check: daily_pnl={self.daily_pnl}, unrealized={unrealized_pnl}, total_loss={total_loss}")
        if self.total_equity > 0 and total_loss <= -self.config["MAX_DAILY_DRAWDOWN"] * self.total_equity:
            self.logger.debug("Drawdown limit exceeded, risk FAILED")
            return False
        if symbol not in self.symbol_states:
            self.symbol_states[symbol] = {"loss_streak":0, "win_streak":0, "cooldown_until":0}
        state = self.symbol_states[symbol]
        self.logger.debug(f"{symbol} risk state: {state}")
        if state["loss_streak"] >= self.config["MAX_LOSS_STREAK"] and state["cooldown_until"] > int(datetime.now().timestamp()):
            self.logger.debug(f"{symbol} in loss streak cooldown")
            return False
        if state["win_streak"] >= self.config["MAX_WIN_STREAK"] and state["cooldown_until"] > int(datetime.now().timestamp()):
            self.logger.debug(f"{symbol} in win streak cooldown")
            return False
        self.logger.debug("Risk check PASSED")
        return True

    async def _reset_daily_if_needed(self):
        today = datetime.now(timezone.utc).date()
        if self.last_reset_date is None or self.last_reset_date.date() != today:
            self.daily_pnl = 0.0
            self.unrealized_pnl = 0.0
            self.last_reset_date = datetime.now(timezone.utc)
            await self.save_state()
            self.logger.info("Daily PnL reset.")

    async def update_trade_result(self, pnl, symbol=None):
        self.daily_pnl += pnl
        if self.config.get("PAPER_TRADE", False):
            self.total_equity += pnl
        else:
            try:
                await self._fetch_equity()
            except Exception as e:
                self.logger.warning(f"Failed to refresh live equity after trade: {e}")
                self.total_equity += pnl
        await self.save_state()
        if symbol:
            state = self.symbol_states.setdefault(symbol, {"loss_streak":0, "win_streak":0, "cooldown_until":0})
            if pnl > 0:
                state["win_streak"] += 1
                state["loss_streak"] = 0
            else:
                state["loss_streak"] += 1
                state["win_streak"] = 0
            now = int(datetime.now().timestamp())
            if pnl > 0 and state["win_streak"] >= self.config["MAX_WIN_STREAK"]:
                state["cooldown_until"] = now + self.config["COOLDOWN_WIN"]
            elif pnl < 0 and state["loss_streak"] >= self.config["MAX_LOSS_STREAK"]:
                state["cooldown_until"] = now + self.config["COOLDOWN_LOSS"]
            await self.save_state()

    async def calculate_position_size(self, symbol, entry_price, stop_price):
        if self.total_equity <= 0 or entry_price <= 0:
            return self.config["BASE_ORDER_SIZE"]
        allocation = Decimal(str(self.total_equity)) * Decimal(str(self.config["BALANCE_USAGE_PERCENT"]))
        max_symbol_alloc = Decimal(str(self.total_equity)) * Decimal(str(self.config["MAX_SYMBOL_ALLOCATION_PERCENT"]))
        allocation = min(allocation, max_symbol_alloc)

        # Safeguard: Never allocate more than available free quote currency (e.g. USDT)
        free_quote = None
        if not self.config.get("PAPER_TRADE", False):
            try:
                account = await self.rest.get_account()
                for b in account.get("balances", []):
                    if b["asset"] == self.config["QUOTE_ASSET"]:
                        free_quote = float(b["free"])
                        break
                if free_quote is not None:
                    max_spendable = Decimal(str(max(0.0, free_quote * 0.99)))
                    allocation = min(allocation, max_spendable)
            except Exception as e:
                self.logger.warning(f"Failed to check free quote asset balance: {e}")

        qty_dec = allocation / Decimal(str(entry_price))
        filters = await self.rest.get_filters(symbol)
        step_size = Decimal(str(filters.get("LOT_SIZE", {}).get("stepSize", "0.000001")))
        min_qty = Decimal(str(filters.get("LOT_SIZE", {}).get("minQty", "0.00001")))
        
        # Check NOTIONAL filter
        notional_filter = filters.get("NOTIONAL", filters.get("MIN_NOTIONAL", {}))
        min_notional = float(notional_filter.get("minNotional", 5.0))
        if float(allocation) < min_notional:
            needed = min_notional * 1.02
            if free_quote is not None and free_quote < needed:
                self.logger.warning(
                    f"Free quote balance ({free_quote:.2f} {self.config.get('QUOTE_ASSET', 'USDT')}) is below minNotional ({needed:.2f}) for {symbol}. Order skipped."
                )
                return 0.0
            if float(self.total_equity) >= min_notional:
                self.logger.info(f"Allocation {float(allocation):.2f} USDT is below minNotional {min_notional} for {symbol}. Bumping allocation to minNotional.")
                qty_dec = Decimal(str(needed)) / Decimal(str(entry_price))
            else:
                self.logger.warning(f"Total equity {self.total_equity} is less than minNotional {min_notional} for {symbol}.")
                return 0.0

        qty_dec = (qty_dec // step_size) * step_size
        qty_dec = max(qty_dec, min_qty)
        if "maxQty" in filters.get("LOT_SIZE", {}):
            qty_dec = min(qty_dec, Decimal(str(filters["LOT_SIZE"]["maxQty"])))

        order_cost = float(qty_dec) * entry_price
        if free_quote is not None and order_cost > free_quote:
            self.logger.warning(
                f"Calculated cost {order_cost:.2f} USDT exceeds available free quote ({free_quote:.2f} USDT) for {symbol}. Skipped."
            )
            return 0.0

        if order_cost > float(self.total_equity):
            self.logger.warning(f"Calculated size {float(qty_dec)} ({order_cost:.2f} USDT) exceeds total equity ({self.total_equity:.2f} USDT) for {symbol}. Skipped.")
            return 0.0
        return float(qty_dec)
