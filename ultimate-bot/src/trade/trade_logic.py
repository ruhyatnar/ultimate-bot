import asyncio
import logging
import re
import time
from datetime import datetime, timedelta, timezone
import pandas as pd

class TradeLogic:
    def __init__(self, config, order_mgr, risk_mgr, signal_gen, trend_detector, db, rest, ws_stream, webhook, health_check=None):
        self.config = config
        self.order_mgr = order_mgr
        self.risk_mgr = risk_mgr
        self.signal_gen = signal_gen
        self.trend_detector = trend_detector
        self.db = db
        self.rest = rest
        self.ws_stream = ws_stream
        self.webhook = webhook
        self.health_check = health_check
        self.logger = logging.getLogger(__name__)
        self.active_trades = {}
        self.current_symbols = []
        self.symbol_cooldowns = {}
        self.cooldown = 10
        self.last_atr_update = {}
        self.last_exchange_sync_time = 0

    def _is_valid_symbol(self, symbol):
        base = symbol[:-len(self.config["QUOTE_ASSET"])] if symbol.endswith(self.config["QUOTE_ASSET"]) else symbol
        return bool(re.match(r'^[A-Z0-9]+$', base))

    async def update_symbols(self):
        if self.config["DYNAMIC_SYMBOLS"]:
            candidates = await self.trend_detector.get_top_symbols()
            active_symbols = set(self.active_trades.keys())
            new_symbols = [s for s in candidates if s not in active_symbols]
            allowed_new = max(0, self.config["MAX_SYMBOLS"] - len(active_symbols))
            new_symbols = list(active_symbols) + new_symbols[:allowed_new]
        else:
            new_symbols = self.config["STATIC_SYMBOLS"]

        valid_symbols = []
        for s in new_symbols:
            if not self._is_valid_symbol(s):
                self.logger.warning(f"Invalid symbol format ignored: {s}")
                continue
            info = await self.rest.get_symbol_info(s)
            if info and info.get("status") == "TRADING":
                valid_symbols.append(s)
            else:
                self.logger.warning(f"Symbol {s} not tradable; skipping.")
        if set(valid_symbols) != set(self.current_symbols):
            self.logger.info(f"Symbols updated: {valid_symbols}")
            old_symbols = set(self.current_symbols)
            self.current_symbols = valid_symbols
            if not self.config["PAPER_TRADE"] and self.ws_stream.is_connected():
                add_syms = [s for s in valid_symbols if s not in old_symbols]
                remove_syms = [s for s in old_symbols if s not in valid_symbols]
                if add_syms: await self.ws_stream.subscribe(add_syms)
                if remove_syms: await self.ws_stream.unsubscribe(remove_syms)

    async def refresh_symbols_loop(self):
        while True:
            await asyncio.sleep(self.config["SYMBOL_REFRESH_INTERVAL"])
            await self.update_symbols()

    async def run(self):
        while True:
            if self.health_check and self.health_check.pause_trading:
                self.logger.warning("Trading paused by health check")
                await asyncio.sleep(30)
                continue
            if not self.config["PAPER_TRADE"]:
                now = time.time()
                if now - self.last_exchange_sync_time >= 300:
                    await self.sync_positions_from_exchange()
                    self.last_exchange_sync_time = now
            if not self.current_symbols:
                await self.update_symbols()
            for symbol in self.current_symbols:
                try:
                    await self.process_symbol(symbol)
                except Exception as e:
                    self.logger.error(f"Error processing {symbol}: {e}")
                    await asyncio.sleep(1)
            await asyncio.sleep(self.config["SIGNAL_INTERVAL"])

    async def process_symbol(self, symbol):
        self.logger.debug(f"Processing symbol {symbol}")
        if symbol in self.active_trades:
            self.logger.debug(f"{symbol} already active, managing...")
            await self.manage_trade(symbol)
            return
        if len(self.active_trades) >= self.config["MAX_SYMBOLS"]:
            self.logger.debug(f"Max active trades reached ({len(self.active_trades)}/{self.config['MAX_SYMBOLS']}). Skipping {symbol}")
            return
        if symbol in self.symbol_cooldowns and time.time() < self.symbol_cooldowns[symbol]:
            self.logger.debug(f"{symbol} in cooldown until {self.symbol_cooldowns[symbol]}")
            return
        unrealized = await self.calculate_unrealized_pnl()
        risk_ok = await self.risk_mgr.check_risk(symbol, unrealized)
        self.logger.debug(f"Risk check for {symbol}: {'PASSED' if risk_ok else 'FAILED'}")
        if not risk_ok: return
        signal, atr = await self.signal_gen.generate_signal(symbol)
        self.logger.debug(f"Signal for {symbol}: {signal}, ATR={atr:.6f}")
        if signal == "NEUTRAL":
            self.logger.debug(f"{symbol} signal NEUTRAL, skipping entry")
            return
        if signal == "SELL":
            self.logger.debug(f"{symbol} signal SELL (ignored in spot mode)")
            return
        self.logger.info(f"BUY signal for {symbol}, entering trade...")
        await self.enter_trade(symbol, signal, atr)
        self.symbol_cooldowns[symbol] = time.time() + self.cooldown

    async def enter_trade(self, symbol, signal, atr):
        price = await self.ws_stream.get_current_price(symbol)
        if not price:
            try:
                ticker = await self.rest.get_ticker(symbol)
                price = float(ticker["price"])
            except: return
        entry_price = price
        stop_price = entry_price - atr * self.config["ATR_MULTIPLIER_SL"]
        take_profit = entry_price + atr * self.config["ATR_MULTIPLIER_TP"]
        min_tp_dist = entry_price * self.config["MIN_TP_PERCENT"]
        if take_profit - entry_price < min_tp_dist:
            take_profit = entry_price + min_tp_dist
        side = "BUY"

        qty = await self.risk_mgr.calculate_position_size(symbol, entry_price, stop_price)
        order_id = await self.order_mgr.place_market_order(symbol, side, qty, expected_price=entry_price)
        if order_id is None: return
        self.logger.info(f"Entry market order placed: {order_id} for {symbol}")
        filled, executed_qty = await self.order_mgr.wait_for_fill(symbol, order_id)
        if not filled:
            self.logger.warning(f"Entry order {order_id} not filled. Aborting.")
            return
        if executed_qty and executed_qty > 0:
            if executed_qty < qty:
                self.logger.warning(f"Partial fill: {executed_qty} of {qty}. Adjusting position size.")
                qty = executed_qty
            if not self.config["PAPER_TRADE"]:
                try:
                    order_info = await self.rest.get_order(symbol, order_id)
                    avg_price = float(order_info.get("avgPrice", order_info.get("price", entry_price)))
                    if avg_price > 0:
                        entry_price = avg_price
                        stop_price = entry_price - atr * self.config["ATR_MULTIPLIER_SL"]
                        take_profit = entry_price + atr * self.config["ATR_MULTIPLIER_TP"]
                        min_tp_dist = entry_price * self.config["MIN_TP_PERCENT"]
                        if take_profit - entry_price < min_tp_dist:
                            take_profit = entry_price + min_tp_dist
                except Exception as e:
                    self.logger.warning(f"Could not fetch avg fill price: {e}")

        trade = {
            "symbol": symbol, "entry_price": entry_price, "side": side, "quantity": qty,
            "entry_time": time.time(), "stop_price": stop_price, "take_profit": take_profit,
            "atr": atr, "trailing_active": False, "trailing_stop": stop_price,
            "breakeven_activated": False, "order_id": order_id
        }
        self.active_trades[symbol] = trade
        await self.db.save_active_trade(trade)
        await self.webhook.send(f"ENTRY {symbol} ({side}) Price: {entry_price:.2f} SL: {stop_price:.2f} TP: {take_profit:.2f} Size: {qty:.4f} ID: {order_id}")

    async def manage_trade(self, symbol):
        trade = self.active_trades[symbol]
        price = await self.ws_stream.get_current_price(symbol)
        if not price:
            try:
                ticker = await self.rest.get_ticker(symbol)
                price = float(ticker["price"])
            except: return
        now = time.time()
        if symbol not in self.last_atr_update or (now - self.last_atr_update[symbol]) > 1800:
            klines = await self.rest.get_klines(symbol, self.config["TIMEFRAME"], 100)
            if klines:
                atr = await self._calculate_atr_from_klines(klines)
                if atr > 0:
                    trade["atr"] = atr
                    self.last_atr_update[symbol] = now

        if trade["side"] == "BUY":
            if price <= trade["stop_price"]:
                await self.close_trade(symbol, "STOP_LOSS"); return
            if price >= trade["take_profit"]:
                await self.close_trade(symbol, "TAKE_PROFIT"); return
        if time.time() - trade["entry_time"] > self.config["MAX_HOLD_TIME"]:
            await self.close_trade(symbol, "TIME_STOP"); return

        if not trade["trailing_active"]:
            profit_pct = (price - trade["entry_price"]) / trade["entry_price"]
            if profit_pct >= self.config["TRAILING_STOP_ACTIVATE"]:
                trade["trailing_active"] = True
                trade["trailing_stop"] = max(trade.get("trailing_stop", 0), trade["stop_price"])
                self.logger.info(f"Trailing stop activated for {symbol} at profit {profit_pct*100:.2f}%.")
        if trade["trailing_active"]:
            new_stop = price * (1 - self.config["TRAILING_STOP_CALLBACK"])
            if new_stop > trade["trailing_stop"]:
                trade["trailing_stop"] = new_stop
            if price <= trade["trailing_stop"]:
                await self.close_trade(symbol, "TRAILING_STOP"); return

        if not trade.get("breakeven_activated", False):
            profit_pct = (price - trade["entry_price"]) / trade["entry_price"]
            if profit_pct >= 0.01:
                trade["breakeven_activated"] = True
                # Professional Breakeven: cover spot exchange round-trip fees (0.1% buy + 0.1% sell + 0.05% cushion = 0.25%)
                be_price = trade["entry_price"] * 1.0025
                if be_price > trade["stop_price"]:
                    trade["stop_price"] = be_price
                if trade["trailing_active"] and be_price > trade["trailing_stop"]:
                    trade["trailing_stop"] = be_price
                self.logger.info(f"Breakeven locked for {symbol} at {be_price:.4f} (fees covered).")
                await self.webhook.send(f"🛡️ Breakeven lock engaged for {symbol} at {be_price:.4f} (fees covered).")

        if int(time.time()) % 30 == 0:
            await self.db.save_active_trade(trade)

    async def _calculate_atr_from_klines(self, klines):
        if not klines: return 0
        df = pd.DataFrame(klines, columns=['open_time','open','high','low','close','volume','close_time','quote_volume','trades','taker_buy_base','taker_buy_quote','ignore'])
        for col in ['open','high','low','close']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        tr = pd.concat([df['high']-df['low'], (df['high']-df['close'].shift()).abs(), (df['low']-df['close'].shift()).abs()], axis=1).max(axis=1)
        atr = tr.rolling(self.config["ATR_PERIOD"]).mean().iloc[-1]
        return atr if not pd.isna(atr) else 0

    async def close_trade(self, symbol, reason):
        trade = self.active_trades.pop(symbol, None)
        if not trade: return
        exit_side = "SELL"
        exit_order_id = await self.order_mgr.place_market_order(symbol, exit_side, trade["quantity"])
        if exit_order_id is None:
            self.logger.error(f"Failed to place exit order for {symbol}. Position remains!")
            self.active_trades[symbol] = trade
            return
        filled, executed_qty = await self.order_mgr.wait_for_fill(symbol, exit_order_id, timeout=10)
        if not filled:
            self.logger.warning(f"Exit order {exit_order_id} not filled? Keeping position.")
            self.active_trades[symbol] = trade
            return

        fill_price = None
        if self.config["PAPER_TRADE"]:
            row = await self.db.fetch_one("SELECT avg_fill_price FROM orders WHERE order_id = ?", (exit_order_id,))
            fill_price = float(row[0]) if row and row[0] else None
        if not fill_price:
            fill_price = await self.ws_stream.get_current_price(symbol)
            if not fill_price:
                ticker = await self.rest.get_ticker(symbol)
                fill_price = float(ticker["price"])

        remaining_qty = trade["quantity"] - executed_qty

        # Professional net PnL calculation deducting Binance spot exchange taker commissions (0.1% each leg)
        fee_rate = 0.001
        entry_cost = trade["entry_price"] * executed_qty
        exit_cost = fill_price * executed_qty
        total_fees = (entry_cost + exit_cost) * fee_rate
        gross_pnl = (fill_price - trade["entry_price"]) * executed_qty
        pnl = gross_pnl - total_fees

        # In live trading, purge any lingering open orders for this symbol on Binance to prevent orphan execution
        if not self.config["PAPER_TRADE"]:
            try:
                await self.rest._request("DELETE", "/api/v3/openOrders", {"symbol": symbol}, signed=True)
            except Exception:
                pass

        await self.db.update_order_status(exit_order_id, "FILLED", executed_qty, fill_price, profit_loss=pnl)
        if remaining_qty > 0:
            trade["quantity"] = remaining_qty
            self.active_trades[symbol] = trade
            await self.db.save_active_trade(trade)
            await self.risk_mgr.update_trade_result(pnl, symbol)
            await self.webhook.send(f"⚠️ Partial exit for {symbol} ({reason}): {executed_qty} of {trade['quantity']} sold. Net PnL (after fees): {pnl:+.2f} USDT. Remaining {remaining_qty} units.")
            return

        await self.db.delete_active_trade(symbol)
        await self.risk_mgr.update_trade_result(pnl, symbol)
        emoji = "✅" if pnl >= 0 else "❌"
        await self.webhook.send(f"{emoji} CLOSE {symbol} ({reason}) Net PnL: {pnl:+.2f} USDT (Gross: {gross_pnl:+.2f}, Fees: -{total_fees:.2f})")
        self.logger.info(f"Closed {symbol} due to {reason}, Net PnL: {pnl:.2f} (Gross: {gross_pnl:.2f}, Fees: -{total_fees:.2f})")

    async def reconcile_positions(self):
        self.logger.info("Reconciling positions...")
        active = await self.db.get_active_trades()
        for trade in active:
            self.active_trades[trade["symbol"]] = trade
            self.logger.info(f"Restored active trade for {trade['symbol']}")
        await self.sync_positions_from_exchange()

    async def sync_positions_from_exchange(self):
        if self.config["PAPER_TRADE"]: return
        try:
            account = await self.rest.get_account()
            quote_asset = self.config["QUOTE_ASSET"]
            asset_balances = {}
            for b in account["balances"]:
                asset = b["asset"]
                free = float(b["free"])
                if asset != quote_asset and free > 0:
                    asset_balances[asset + quote_asset] = free
            managed_symbols = set(self.current_symbols) | set(self.active_trades.keys())
            auto_liquidate = self.config.get("AUTO_LIQUIDATE_ORPHANS", False)
            for symbol, free_balance in asset_balances.items():
                if symbol in managed_symbols and symbol not in self.active_trades:
                    if auto_liquidate:
                        self.logger.warning(f"AUTO_LIQUIDATE_ORPHANS=True: closing {symbol} balance={free_balance}")
                        await self.order_mgr.place_market_order(symbol, "SELL", free_balance)
                        await self.webhook.send(f"⚠️ Orphan position closed for {symbol}: {free_balance} units")
                    else:
                        self.logger.info(f"Unmanaged balance detected for {symbol}: {free_balance}. Leaving untouched (AUTO_LIQUIDATE_ORPHANS=False).")
            for symbol in list(self.active_trades.keys()):
                if symbol in managed_symbols and symbol not in asset_balances:
                    self.active_trades.pop(symbol, None)
                    await self.db.delete_active_trade(symbol)
                    self.logger.warning(f"Active trade for {symbol} has no balance; removing.")
                    await self.webhook.send(f"ℹ️ Active trade for {symbol} removed (balance zero).")
        except Exception as e:
            self.logger.error(f"Error during exchange sync: {e}")
            await self.webhook.send(f"❌ Exchange sync error: {e}")

    async def calculate_unrealized_pnl(self):
        total = 0.0
        for symbol, trade in self.active_trades.items():
            price = await self.ws_stream.get_current_price(symbol)
            if not price:
                try:
                    ticker = await self.rest.get_ticker(symbol)
                    price = float(ticker["price"])
                except: continue
            total += (price - trade["entry_price"]) * trade["quantity"]
        return total

    async def send_daily_report_loop(self):
        while True:
            now = datetime.now(timezone.utc)
            target = now.replace(hour=23, minute=59, second=59, microsecond=0)
            if now >= target: target += timedelta(days=1)
            await asyncio.sleep((target - now).total_seconds())
            await self._send_daily_report()

    async def _send_daily_report(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        row = await self.db.fetch_one("SELECT COUNT(*), SUM(profit_loss) FROM orders WHERE status='FILLED' AND side='SELL' AND date(created_at/1000, 'unixepoch') = ?", (today,))
        total_trades = row[0] if row else 0
        total_pnl = row[1] if row and row[1] is not None else 0.0
        row = await self.db.fetch_one("SELECT COUNT(*) FROM orders WHERE status='FILLED' AND side='SELL' AND profit_loss > 0 AND date(created_at/1000, 'unixepoch') = ?", (today,))
        wins = row[0] if row else 0
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        embed = {
            "title": "Daily Trading Report",
            "color": 0x00ff00 if total_pnl >= 0 else 0xff0000,
            "fields": [
                {"name": "Date", "value": today, "inline": True},
                {"name": "Total PnL", "value": f"${total_pnl:.2f}", "inline": True},
                {"name": "Win Rate", "value": f"{win_rate:.1f}% ({wins}/{total_trades})", "inline": True},
                {"name": "Active Positions", "value": str(len(self.active_trades)), "inline": True},
                {"name": "Status", "value": "RUNNING", "inline": True},
            ],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await self.webhook.send("", embed=embed)
