import asyncio
import json
import logging
import os
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
        self.ws_stream = self._ws_stream_proxy(ws_stream, self.rest)
        self.webhook = webhook
        self.health_check = health_check
        self.logger = logging.getLogger(__name__)
        self.active_trades = {}
        self.current_symbols = []
        self.symbol_cooldowns = {}
        self.cooldown = 10
        self.last_atr_update = {}
        self.last_exchange_sync_time = 0
        # Remote-control channel: the web monitor (status.py) writes this JSON
        # file; the engine polls it every cycle. Supports pause/resume and
        # one-shot close_all / close_symbol commands (deduped via command_id).
        self.control_file = config.get("CONTROL_FILE", "./data/engine_control.json")
        self._control = {}
        self._control_mtime = 0.0
        self._last_command_id = None

    def _read_control(self):
        """Read the control file only when it changed (cheap mtime check)."""
        try:
            mtime = os.path.getmtime(self.control_file)
            if mtime == self._control_mtime:
                return self._control
            with open(self.control_file, "r", encoding="utf-8") as f:
                self._control = json.load(f)
            self._control_mtime = mtime
        except FileNotFoundError:
            self._control = {}
            self._control_mtime = 0.0
        except Exception as e:
            self.logger.warning(f"Could not read engine control file {self.control_file}: {e}")
            self._control = {}
            self._control_mtime = 0.0
        return self._control

    def _write_control(self, data):
        """Atomically persist control state (used to clear executed commands)."""
        try:
            os.makedirs(os.path.dirname(self.control_file) or ".", exist_ok=True)
            tmp = self.control_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, self.control_file)
            self._control = data
            self._control_mtime = os.path.getmtime(self.control_file)
        except Exception as e:
            self.logger.error(f"Failed to write engine control file: {e}")

    async def _process_control_commands(self):
        """Execute one-shot remote commands (close_all / close_symbol).

        Commands are deduplicated via command_id, but a command is only cleared once it
        has fully succeeded. If an exit order is rejected (network outage, dust balance,
        exchange hiccup) close_trade() re-arms the position, so the command stays pending
        and is retried on the next loop iteration instead of silently dropping a position
        the operator asked to liquidate.

        Returns True while a close command is still pending (entries stay blocked).
        """
        control = self._read_control()
        cmd_id = control.get("command_id")
        if not cmd_id:
            return False
        is_new = cmd_id != self._last_command_id
        self._last_command_id = cmd_id

        if control.get("close_all"):
            open_symbols = list(self.active_trades.keys())
            if is_new and open_symbols:
                self.logger.warning(f"REMOTE CONTROL: closing ALL active positions ({len(open_symbols)})")
                await self.webhook.send(f"🛑 REMOTE CONTROL: Close ALL requested ({len(open_symbols)} positions).")
            for symbol in list(open_symbols):
                if symbol in self.active_trades:
                    await self.close_trade(symbol, "REMOTE_CLOSE_ALL")
            # If any exit was rejected and re-armed, keep the command so it retries.
            if any(s in self.active_trades for s in open_symbols):
                self.logger.warning("REMOTE CONTROL: some close-all exits were rejected; command stays pending and will retry.")
                return True
            control.pop("close_all", None)
            control.pop("command_id", None)
            self._write_control(control)
            return False

        if control.get("close_symbol"):
            symbol = str(control.get("close_symbol", "")).strip().upper()
            if is_new:
                self.logger.warning(f"REMOTE CONTROL: closing {symbol}")
                await self.webhook.send(f"🛑 REMOTE CONTROL: Close {symbol} requested.")
            if symbol in self.active_trades:
                await self.close_trade(symbol, "REMOTE_CLOSE")
                if symbol in self.active_trades:
                    self.logger.warning(f"REMOTE CONTROL: exit rejected for {symbol}; command stays pending and will retry.")
                    return True
            control.pop("close_symbol", None)
            control.pop("command_id", None)
            self._write_control(control)
            return False

        # Stale/malformed command (no recognized action): clear it so it never wedges.
        control.pop("command_id", None)
        control.pop("close_all", None)
        control.pop("close_symbol", None)
        self._write_control(control)
        return False

    def _ws_stream_proxy(self, stream, rest):
        """Wrap the stream client so price reads transparently fall back to REST
        when the public WebSocket is disconnected or the tick cache is stale."""
        class _StreamProxy:
            def __init__(self, stream, rest):
                self._stream = stream
                self._rest = rest

            async def _fallback_price(self, symbol):
                try:
                    ticker = await self._rest.get_ticker(symbol)
                    return float(ticker["price"])
                except Exception:
                    return None

            async def get_current_price(self, symbol):
                price = None
                if self._stream is not None and self._stream.is_connected():
                    price = await self._stream.get_current_price(symbol)
                if not price:
                    price = await self._fallback_price(symbol)
                return price

            def is_connected(self):
                return self._stream is not None and self._stream.is_connected()

            def __getattr__(self, name):
                return getattr(self._stream, name)

        return _StreamProxy(stream, rest)

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
            # In static mode, always retain any currently active trades so they stay monitored
            active_symbols = list(self.active_trades.keys())
            new_symbols = list(dict.fromkeys(active_symbols + self.config["STATIC_SYMBOLS"]))

        valid_symbols = []
        for s in new_symbols:
            if not self._is_valid_symbol(s):
                self.logger.warning(f"Invalid symbol format ignored: {s}")
                continue
            info = await self.rest.get_symbol_info(s)
            if info and info.get("status") == "TRADING":
                valid_symbols.append(s)
            elif s in self.active_trades:
                # If an active trade is open, keep it in valid_symbols even if info lookup had a glitch
                valid_symbols.append(s)
            else:
                self.logger.warning(f"Symbol {s} not tradable; skipping.")
        if set(valid_symbols) != set(self.current_symbols):
            self.logger.info(f"Symbols updated: {valid_symbols}")
            old_symbols = set(self.current_symbols)
            self.current_symbols = valid_symbols
            if not self.config["PAPER_TRADE"] and self.ws_stream.is_connected():
                add_syms = [s for s in valid_symbols if s not in old_symbols]
                remove_syms = [s for s in old_symbols if s not in valid_symbols and s not in self.active_trades]
                if add_syms: await self.ws_stream.subscribe(add_syms)
                if remove_syms: await self.ws_stream.unsubscribe(remove_syms)

        # Persist monitored symbols and scanned pairs to SQLite for status.py and web monitor
        try:
            await self.db.set_risk_state("monitored_symbols", json.dumps(self.current_symbols))
            scanned = self.trend_detector.get_last_scanned()
            if scanned:
                await self.db.set_risk_state("scanned_pairs", json.dumps(scanned))
        except Exception as e:
            self.logger.debug(f"Could not persist scanned pairs to db: {e}")

    async def refresh_symbols_loop(self):
        while True:
            await asyncio.sleep(self.config["SYMBOL_REFRESH_INTERVAL"])
            await self.update_symbols()

    async def run(self):
        while True:
            # Remote web-monitor commands first so emergency closes always win
            # over every other gate below. Returns True while a close command is
            # still being retried (some exits were rejected) — keep blocking new
            # entries until the liquidation fully completes.
            pending_close = await self._process_control_commands()

            control = self._read_control()
            if control.get("paused") or pending_close:
                # Web-monitor pause: block NEW entries but keep managing open
                # positions so stops/TPs/trailing stays armed while the operator
                # reviews the market. The same holds while a remote close command
                # is still retrying rejected exits.
                self.logger.debug("Web-monitor pause ACTIVE — new entries blocked; managing open positions only.")
                for symbol in list(self.active_trades.keys()):
                    try:
                        await self.manage_trade(symbol)
                    except Exception as e:
                        self.logger.error(f"Error managing {symbol} during web pause: {e}")
                await asyncio.sleep(self.config["SIGNAL_INTERVAL"])
                continue

            if self.health_check and self.health_check.pause_trading:
                self.logger.warning("Trading paused by health check")
                await asyncio.sleep(30)
                continue
            if not self.config["PAPER_TRADE"]:
                now = time.time()
                if now - self.last_exchange_sync_time >= 60:
                    await self.sync_positions_from_exchange()
                    await self.risk_mgr._fetch_equity()
                    await self.risk_mgr.save_state()
                    self.last_exchange_sync_time = now
            if not self.current_symbols:
                await self.update_symbols()

            # 1. ALWAYS manage all open active trades first to guarantee stops, TPs, trailing stops
            # and time stops are evaluated every single cycle regardless of whether the symbol is in current_symbols.
            for symbol in list(self.active_trades.keys()):
                try:
                    await self.manage_trade(symbol)
                except Exception as e:
                    self.logger.error(f"Error managing active trade {symbol}: {e}")

            # 2. Evaluate un-entered symbols for potential entry
            for symbol in self.current_symbols:
                if symbol in self.active_trades:
                    continue
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
        # Professional guard: only process long entries in spot mode.
        if signal != "BUY":
            self.logger.debug(f"{symbol}: enter_trade called with signal={signal}; spot long-only engine ignores it.")
            return
        price = await self.ws_stream.get_current_price(symbol)
        if not price:
            self.logger.warning(f"{symbol}: no live price available (WS stale & REST ticker failed); skipping entry.")
            return
        entry_price = price
        stop_price = entry_price - atr * self.config["ATR_MULTIPLIER_SL"]
        take_profit = entry_price + atr * self.config["ATR_MULTIPLIER_TP"]
        min_tp_dist = entry_price * self.config["MIN_TP_PERCENT"]
        if take_profit - entry_price < min_tp_dist:
            take_profit = entry_price + min_tp_dist
        side = "BUY"

        # Hard cap total capital deployed (equity * BALANCE_USAGE_PERCENT).
        # Computed AFTER the live price is known so the cap shares the same benchmark.
        deployed = sum(t["quantity"] * t["entry_price"] for t in self.active_trades.values())
        remaining = self.config["BALANCE_USAGE_PERCENT"] * self.risk_mgr.total_equity - deployed
        if remaining <= 0:
            self.logger.info(f"{symbol}: no remaining allocation headroom (${remaining:.2f}); skipping entry.")
            return

        qty = await self.risk_mgr.calculate_position_size(symbol, entry_price, stop_price)
        if not qty or qty <= 0:
            self.logger.info(f"{symbol}: position size 0 (equity/fee/minNotional caps) — entry skipped.")
            return
        # Enforce the total-capital cap after sizing (planned notional vs remaining headroom)
        if qty * entry_price > remaining:
            self.logger.info(f"{symbol}: planned notional ${qty * entry_price:.2f} exceeds remaining allocation headroom ${remaining:.2f}; skipping entry.")
            return
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

                # Verify actual net base asset credited (accounts for base-asset taker fee deduction)
                try:
                    account = await self.rest.get_account()
                    quote_asset = self.config.get("QUOTE_ASSET", "USDT")
                    base_asset = symbol[:-len(quote_asset)] if symbol.endswith(quote_asset) else symbol
                    free_base = next((float(b["free"]) for b in account.get("balances", []) if b["asset"] == base_asset), None)
                    if free_base is not None and 0 < free_base < qty:
                        self.logger.info(f"{symbol}: Net available {base_asset} is {free_base} (taker fee deducted from base asset). Updating tracked position size from {qty} to {free_base}.")
                        qty = free_base
                except Exception as e:
                    self.logger.warning(f"Could not verify net base asset balance: {e}")

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
            except Exception:
                return
        now = time.time()
        if symbol not in self.last_atr_update or (now - self.last_atr_update[symbol]) > 1800:
            klines = await self.rest.get_klines(symbol, self.config["TIMEFRAME"], 100)
            if klines:
                atr = await self._calculate_atr_from_klines(klines)
                if atr > 0:
                    trade["atr"] = atr
                    self.last_atr_update[symbol] = now

        if trade["side"] == "BUY":
            # Gap-breach protection: compare against bar LOWS/HIGHS, not just the
            # current tick. A tick-based check alone misses violent wicks that spike
            # through the stop between SIGNAL_INTERVAL polls and bounce back — the #1
            # cause of unexpected deep losses in live market-only bots. We evaluate
            # both the just-closed candle and the forming one (the exchange returns
            # them newest-last) so a wick on a candle that closed between polls is
            # still caught, not only the one that happens to be open right now.
            recent = await self.rest.get_klines(symbol, self.config["TIMEFRAME"], 2)
            if recent:
                try:
                    df = pd.DataFrame(recent, columns=['open_time','open','high','low','close','volume','close_time','quote_volume','trades','taker_buy_base','taker_buy_quote','ignore'])
                    low = min(float(v) for v in df['low'].tail(2).tolist())
                    high = max(float(v) for v in df['high'].tail(2).tolist())
                except Exception:
                    low = price
                    high = price
                # Evaluate both just-closed and forming candles (newest-last from the
                # exchange) so a wick on a candle that closed between polls still triggers.
                if low <= trade["stop_price"]:
                    await self.close_trade(symbol, "STOP_LOSS", fill_override=min(trade["stop_price"], low))
                    return
                if high >= trade["take_profit"]:
                    await self.close_trade(symbol, "TAKE_PROFIT", fill_override=trade["take_profit"])
                    return
            # Tick-level check as immediate backstop
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

    async def close_trade(self, symbol, reason, fill_override=None):
        trade = self.active_trades.pop(symbol, None)
        if not trade:
            return
        original_qty = trade["quantity"]
        try:
            exit_side = "SELL"
            exit_order_id = await self.order_mgr.place_market_order(symbol, exit_side, original_qty)
            if exit_order_id is None:
                # Failsafe: never silently drop a position we intended to close.
                # Re-arm the stop locally and alert loudly — the next manage_trade pass
                # (or sync_positions_from_exchange) retries the liquidation.
                self.active_trades[symbol] = trade
                self.symbol_cooldowns[symbol] = time.time() + self.cooldown
                self.logger.critical(f"{symbol}: EXIT ORDER REJECTED ({reason}). Position remains open with stop ${trade['stop_price']:.4f}. Will retry next cycle.")
                await self.webhook.send(f"🚨 CRITICAL: exit order REJECTED for {symbol} ({reason}). Position remains open — retrying. Stop: {trade['stop_price']:.4f}")
                return
            filled, executed_qty = await self.order_mgr.wait_for_fill(symbol, exit_order_id, timeout=10)
            if not filled:
                self.logger.warning(f"Exit order {exit_order_id} not filled? Keeping position.")
                self.active_trades[symbol] = trade
                return
        except Exception as e:
            # CRITICAL SAFETY NET: an exception between pop and re-arm would lose
            # the position from memory while it stays open on the exchange — stops
            # stop being monitored and a duplicate long could be entered. Re-arm
            # the trade and alert loudly so the next cycle retries the exit.
            self.active_trades[symbol] = trade
            self.symbol_cooldowns[symbol] = time.time() + self.cooldown
            self.logger.critical(f"{symbol}: EXIT FAILED with exception ({reason}): {e}. Position re-armed; will retry next cycle. Stop: {trade['stop_price']:.4f}")
            await self.webhook.send(f"🚨 CRITICAL: exit FAILED for {symbol} ({reason}): {e}. Position re-armed — retrying. Stop: {trade['stop_price']:.4f}")
            return

        fill_price = None
        if not self.config["PAPER_TRADE"] and exit_order_id:
            # Live mode: always query the exchange's actual average fill price so slippage
            # and market impact are accurately recorded in PnL.
            try:
                order_info = await self.rest.get_order(symbol, exit_order_id)
                avg = float(order_info.get("avgPrice", 0) or 0)
                if avg > 0:
                    fill_price = avg
            except Exception as e:
                self.logger.warning(f"Could not fetch exit avg fill price for {symbol}: {e}")

        if not fill_price and fill_override:
            fill_price = fill_override
        elif not fill_price and self.config["PAPER_TRADE"] and exit_order_id:
            row = await self.db.fetch_one("SELECT avg_fill_price FROM orders WHERE order_id = ?", (exit_order_id,))
            fill_price = float(row[0]) if row and row[0] else None
        if not fill_price:
            try:
                fill_price = await self.ws_stream.get_current_price(symbol)
                if not fill_price:
                    ticker = await self.rest.get_ticker(symbol)
                    fill_price = float(ticker["price"])
            except Exception as e:
                # Last resort: zero-gross assumption (fees still deducted) rather
                # than letting PnL accounting crash the exit finalization.
                self.logger.error(f"Could not resolve exit fill price for {symbol}: {e}")
                fill_price = trade["entry_price"]

        remaining_qty = max(0.0, original_qty - executed_qty)
        is_partial = False

        if remaining_qty > 0:
            if self.config["PAPER_TRADE"]:
                # In paper trading, only treat as partial if remaining notional is significant
                is_partial = (remaining_qty * fill_price >= 5.0)
            else:
                # In live trading, check if actual remaining base balance on Binance is tradable
                try:
                    filters = await self.rest.get_filters(symbol)
                    min_notional = float(filters.get("NOTIONAL", filters.get("MIN_NOTIONAL", {})).get("minNotional", 5.0))
                    lot_size = filters.get("LOT_SIZE", {})
                    min_qty = float(lot_size.get("minQty", "0.00001"))

                    account = await self.rest.get_account()
                    quote_asset = self.config.get("QUOTE_ASSET", "USDT")
                    base_asset = symbol[:-len(quote_asset)] if symbol.endswith(quote_asset) else symbol
                    free_base = next((float(b["free"]) for b in account.get("balances", []) if b["asset"] == base_asset), 0.0)

                    # If remaining free base is marketable on Binance, treat as partial.
                    # Otherwise, it's non-tradable dust/fee remainder: position is closed!
                    if free_base >= min_qty and free_base * fill_price >= min_notional:
                        is_partial = True
                        remaining_qty = free_base
                    else:
                        self.logger.info(f"{symbol}: Remaining base {free_base} ({free_base * fill_price:.2f} USDT) is non-tradable dust (< minNotional {min_notional} or < minQty {min_qty}). Marking trade as FULL EXIT.")
                        is_partial = False
                        remaining_qty = 0.0
                except Exception as e:
                    self.logger.warning(f"Could not verify remaining balance for {symbol}: {e}")
                    is_partial = False
                    remaining_qty = 0.0

        # Professional net PnL calculation deducting Binance spot exchange taker commissions (0.1% each leg)
        fee_rate = 0.001
        entry_cost = trade["entry_price"] * executed_qty
        exit_cost = fill_price * executed_qty
        total_fees = (entry_cost + exit_cost) * fee_rate
        gross_pnl = (fill_price - trade["entry_price"]) * executed_qty
        pnl = gross_pnl - total_fees
        # Sanity clamp: a wildly off fill_price (e.g. a 0 fallback) would produce nonsensical PnL.
        # Keep the calculation but flag it so logs are interpretable.
        if fill_price <= 0:
            self.logger.error(f"{symbol}: exit fill_price was non-positive ({fill_price}); PnL may be unreliable.")

        # In live trading, purge any lingering open orders for this symbol on Binance to prevent orphan execution
        if not self.config["PAPER_TRADE"]:
            try:
                await self.rest._request("DELETE", "/api/v3/openOrders", {"symbol": symbol}, signed=True)
            except Exception:
                pass

        # Partial exit = the order was canceled after a partial fill; full exit = FILLED.
        exit_status = "CANCELED" if (is_partial and remaining_qty > 0) else "FILLED"
        await self.db.update_order_status(exit_order_id, exit_status, executed_qty, fill_price, profit_loss=pnl)
        if is_partial and remaining_qty > 0:
            trade["quantity"] = remaining_qty
            self.active_trades[symbol] = trade
            await self.db.save_active_trade(trade)
            await self.risk_mgr.update_trade_result(pnl, symbol)
            await self.webhook.send(f"⚠️ Partial exit for {symbol} ({reason}): {executed_qty} of {original_qty} sold. Net PnL (after fees): {pnl:+.2f} USDT. Remaining {remaining_qty} units.")
            return

        await self.db.delete_active_trade(symbol)
        await self.risk_mgr.update_trade_result(pnl, symbol)
        if not self.config["PAPER_TRADE"]:
            try:
                await self.risk_mgr._fetch_equity()
                await self.risk_mgr.save_state()
            except Exception as e:
                self.logger.warning(f"Could not refresh equity after exit: {e}")
        emoji = "✅" if pnl >= 0 else "❌"
        await self.webhook.send(f"{emoji} CLOSE {symbol} ({reason}) Net PnL: {pnl:+.2f} USDT (Gross: {gross_pnl:+.2f}, Fees: -{total_fees:.2f})")
        self.logger.info(f"Closed {symbol} due to {reason}, Net PnL: {pnl:.2f} (Gross: {gross_pnl:.2f}, Fees: -{total_fees:.2f})")

        # Clean up pending remote-control state if this was a requested close.
        control = self._read_control()
        if control.get("close_all") or control.get("close_symbol"):
            symbol_key = control.get("close_symbol", "").strip().upper()
            if not control.get("close_all") and symbol_key and symbol_key == symbol:
                self.logger.info(f"Remote close_symbol for {symbol} fully completed.")
            elif control.get("close_all"):
                # close_all may have targeted multiple symbols; only clear if this symbol
                # was part of that request and is now gone from active_trades.
                if symbol not in self.active_trades:
                    self.logger.info(f"Remote close_all: {symbol} fully closed.")

    async def reconcile_positions(self):
        self.logger.info("Reconciling positions...")
        active = await self.db.get_active_trades()
        for trade in active:
            self.active_trades[trade["symbol"]] = trade
            self.logger.info(f"Restored active trade for {trade['symbol']} (entry={trade['entry_price']}, qty={trade['quantity']}, stop={trade['stop_price']}, tp={trade['take_profit']})")
        await self.sync_positions_from_exchange()

    async def sync_positions_from_exchange(self):
        if self.config["PAPER_TRADE"]: return
        try:
            account = await self.rest.get_account()
            quote_asset = self.config["QUOTE_ASSET"]
            asset_balances = {}
            for b in account.get("balances", []):
                asset = b.get("asset", "")
                free = float(b.get("free", 0.0))
                locked = float(b.get("locked", 0.0))
                total = free + locked
                if asset != quote_asset and total > 0:
                    asset_balances[asset + quote_asset] = {
                        "total": total,
                        "free": free,
                        "locked": locked,
                        "asset": asset
                    }

            managed_symbols = set(self.current_symbols) | set(self.active_trades.keys())
            auto_liquidate = self.config.get("AUTO_LIQUIDATE_ORPHANS", False)

            # 1. Check all currently tracked active trades against Binance balances
            for symbol, trade in list(self.active_trades.items()):
                bal_info = asset_balances.get(symbol)
                total_bal = bal_info["total"] if bal_info else 0.0

                price = await self.ws_stream.get_current_price(symbol)
                if not price:
                    try:
                        ticker = await self.rest.get_ticker(symbol)
                        price = float(ticker["price"])
                    except Exception:
                        price = trade.get("entry_price", 0.0)

                filters = await self.rest.get_filters(symbol)
                min_notional = float(filters.get("NOTIONAL", filters.get("MIN_NOTIONAL", {})).get("minNotional", 5.0))
                lot_size = filters.get("LOT_SIZE", {})
                min_qty = float(lot_size.get("minQty", "0.00001"))
                notional_val = total_bal * price

                # If the balance is zero or non-marketable dust, it was closed or liquidated externally
                if total_bal < min_qty or notional_val < min_notional:
                    self.active_trades.pop(symbol, None)
                    await self.db.delete_active_trade(symbol)
                    self.logger.warning(f"Active trade for {symbol} has no marketable Binance balance (balance={total_bal}, value=${notional_val:.2f} < ${min_notional:.2f}); removed from tracking.")
                    await self.webhook.send(f"ℹ️ Active trade for {symbol} removed from tracking (balance below minNotional / closed externally).")
                    continue

                # If balance is valid but differs from tracked quantity (e.g. fees or partial manual trade), reconcile
                if bal_info and abs(trade["quantity"] - bal_info["free"]) > min_qty and bal_info["free"] >= min_qty:
                    old_qty = trade["quantity"]
                    trade["quantity"] = bal_info["free"]
                    self.active_trades[symbol] = trade
                    await self.db.save_active_trade(trade)
                    self.logger.info(f"{symbol}: Reconciled tracked position quantity from {old_qty} to {bal_info['free']} to match Binance free balance.")

            # 2. Check for unmanaged/orphan balances on the exchange
            for symbol, bal_info in asset_balances.items():
                if symbol in managed_symbols and symbol not in self.active_trades:
                    free_balance = bal_info["free"]
                    price = await self.ws_stream.get_current_price(symbol)
                    if not price:
                        try:
                            ticker = await self.rest.get_ticker(symbol)
                            price = float(ticker["price"])
                        except Exception:
                            continue
                    filters = await self.rest.get_filters(symbol)
                    min_notional = float(filters.get("NOTIONAL", filters.get("MIN_NOTIONAL", {})).get("minNotional", 5.0))
                    lot_size = filters.get("LOT_SIZE", {})
                    min_qty = float(lot_size.get("minQty", "0.00001"))

                    # Ignore dust orphan balances that cannot be traded on Binance
                    if free_balance < min_qty or free_balance * price < min_notional:
                        continue

                    if auto_liquidate:
                        self.logger.warning(f"AUTO_LIQUIDATE_ORPHANS=True: closing orphan position {symbol} balance={free_balance} (${free_balance * price:.2f})")
                        await self.order_mgr.place_market_order(symbol, "SELL", free_balance)
                        await self.webhook.send(f"⚠️ Orphan position closed for {symbol}: {free_balance} units")
                    else:
                        self.logger.info(f"Unmanaged balance detected for {symbol}: {free_balance} (${free_balance * price:.2f}). Leaving untouched (AUTO_LIQUIDATE_ORPHANS=False).")
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
                except Exception:
                    continue
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
        # "Closed trades" uses the same definition as the web monitor stats: SELL exit
        # orders that recorded a realized PnL, including partial-exit legs (CANCELED
        # SELL orders with profit_loss set). BUY entries are never counted.
        row = await self.db.fetch_one("SELECT COUNT(*), SUM(profit_loss) FROM orders WHERE side='SELL' AND status IN ('FILLED','CANCELED') AND profit_loss IS NOT NULL AND date(created_at/1000, 'unixepoch') = ?", (today,))
        total_trades = row[0] if row else 0
        total_pnl = row[1] if row and row[1] is not None else 0.0
        row = await self.db.fetch_one("SELECT COUNT(*) FROM orders WHERE side='SELL' AND status IN ('FILLED','CANCELED') AND profit_loss > 0 AND date(created_at/1000, 'unixepoch') = ?", (today,))
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
