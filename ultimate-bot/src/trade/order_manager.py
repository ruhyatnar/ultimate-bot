import asyncio
import logging
import time
import uuid
from decimal import Decimal

class OrderManager:
    def __init__(self, config, db, rest, ws_api, risk_mgr=None):
        self.config = config
        self.db = db
        self.rest = rest
        self.ws_api = ws_api
        self.risk_mgr = risk_mgr
        self.logger = logging.getLogger(__name__)
        self.paper_trade = config["PAPER_TRADE"]
        self.entry_timeout = config["ENTRY_TIMEOUT"]
        self.last_order_quantity = None

    async def sanitize_order(self, symbol, quantity, price=None):
        filters = await self.rest.get_filters(symbol)
        lot_size = filters.get("LOT_SIZE", {})
        step_size_str = str(lot_size.get("stepSize", "0.000001"))
        min_qty_str = str(lot_size.get("minQty", "0.00001"))
        max_qty_str = str(lot_size.get("maxQty", "99999999"))
        
        step_size = Decimal(step_size_str)
        min_qty = Decimal(min_qty_str)
        max_qty = Decimal(max_qty_str)
        
        d_qty = Decimal(str(quantity))
        # Floor strictly to step_size
        d_qty = (d_qty // step_size) * step_size
        
        if d_qty < min_qty:
            self.logger.warning(f"Quantity {d_qty} below minQty {min_qty} for {symbol}")
            return None, price
        if d_qty > max_qty:
            d_qty = max_qty

        # Verify against MIN_NOTIONAL / NOTIONAL filter
        notional_filter = filters.get("NOTIONAL", filters.get("MIN_NOTIONAL", {}))
        min_notional = float(notional_filter.get("minNotional", 5.0))
        if price is not None and float(d_qty) * price < min_notional:
            self.logger.warning(f"Order value {float(d_qty) * price:.2f} USDT is below minNotional {min_notional} for {symbol}")
            return None, price

        # Quantize to stepSize decimals without scientific notation
        clean_qty = f"{d_qty.quantize(step_size):f}"
        if "." in clean_qty:
            clean_qty = clean_qty.rstrip("0").rstrip(".")
        return clean_qty, price

    async def place_market_order(self, symbol, side, quantity, expected_price=None):
        if self.paper_trade:
            ticker = await self.rest.get_ticker(symbol)
            price = float(ticker["price"])
            qty, _ = await self.sanitize_order(symbol, quantity, price)
            if qty is None:
                self.logger.warning(f"Paper order quantity sanitization failed for {symbol}; order skipped.")
                return None
            order_id = f"paper_{uuid.uuid4().hex[:12]}"
            self.last_order_quantity = float(qty)
            self.logger.info(f"PAPER: {side} MARKET {qty} {symbol} @ {price} (ID: {order_id})")
            await self.db.save_order({
                "order_id": order_id, "symbol": symbol, "side": side, "order_type": "MARKET",
                "price": price, "stop_price": None, "quantity": float(qty), "executed_qty": float(qty),
                "status": "FILLED", "created_at": int(time.time()*1000), "updated_at": int(time.time()*1000),
                "profit_loss": 0, "avg_fill_price": price
            })
            return order_id

        try:
            ticker = await self.rest.get_ticker(symbol)
            current_price = float(ticker["price"])
            if expected_price:
                slippage = abs(current_price - expected_price) / expected_price * 100
                if slippage > self.config["MAX_SLIPPAGE_PERCENT"]:
                    self.logger.warning(f"Slippage too high for {symbol}: {slippage:.2f}%")
                    return None
            if side == "SELL":
                # Base-asset fee clamp: exchange deducts the taker fee from the received
                # base asset when BNB fee-pay is off, so the true sellable balance is the
                # free balance. Clamping instead of rejecting avoids -2010 on exits.
                account = await self.rest.get_account()
                quote_asset = self.config.get("QUOTE_ASSET", "USDT")
                base_asset = symbol[:-len(quote_asset)] if symbol.endswith(quote_asset) else symbol
                free_base = next((float(b["free"]) for b in account.get("balances", []) if b["asset"] == base_asset), None)
                if free_base is not None and free_base < float(quantity):
                    self.logger.info(f"Available {base_asset} ({free_base}) < requested sell qty ({quantity}) - adjusting sell qty to available balance.")
                    quantity = free_base
            else:  # BUY: pre-check free quote balance (1% fee/slippage buffer) to fail fast instead of a -2010 rejection
                account = await self.rest.get_account()
                free_quote = next((float(b["free"]) for b in account.get("balances", []) if b["asset"] == self.config["QUOTE_ASSET"]), 0.0)
                if quantity * current_price > free_quote * 0.99:
                    self.logger.warning(f"BUY rejected: notional ${quantity * current_price:.2f} exceeds 99% of free {self.config['QUOTE_ASSET']} (${free_quote:.2f}).")
                    return None

            qty, _ = await self.sanitize_order(symbol, quantity, current_price)
            if qty is None:
                self.logger.warning(f"Order quantity sanitization failed for {symbol}; order skipped.")
                return None
            try:
                if self.ws_api and self.ws_api.is_connected():
                    resp = await self.ws_api.place_order(symbol, side, "MARKET", qty)
                    result = resp.get("result", {})
                    order_id = result.get("orderId")
                else:
                    resp = await self.rest.place_order(symbol, side, "MARKET", qty)
                    result = resp
                    order_id = result.get("orderId")
            except Exception as e:
                self.logger.error(f"Order placement failed: {e}")
                return None

            if order_id is None:
                self.logger.error("Failed to get orderId")
                return None
            # Retain the synchronous placement response: MARKET orders usually
            # carry the final FILLED status + executedQty in this very payload.
            # wait_for_fill consults it first so a later REST/API outage can
            # never make a filled order look unfilled.
            self.last_order_result = result if isinstance(result, dict) else {}
            self.last_order_quantity = float(qty)
            await self.db.save_order({
                "order_id": str(order_id), "symbol": symbol, "side": side, "order_type": "MARKET",
                "price": result.get("price"), "stop_price": result.get("stopPrice"),
                "quantity": float(qty), "executed_qty": result.get("executedQty", 0),
                "status": result.get("status", "NEW"), "created_at": int(time.time()*1000),
                "updated_at": int(time.time()*1000), "profit_loss": 0,
                "avg_fill_price": result.get("avgPrice")
            })
            return str(order_id)
        except Exception as e:
            # Every failure mode (REST/WS outage, account fetch, filter lookup,
            # sanitization) degrades to a clean skip. Callers treat `None` as
            # "order not placed" and retry/re-arm — never an unhandled crash.
            self.logger.error(f"Order preparation failed for {symbol} {side}: {e}")
            return None

    async def wait_for_fill(self, symbol, order_id, timeout=None):
        if self.paper_trade:
            return True, self.last_order_quantity
        # 1) Fast path: the placement response for a MARKET order is normally
        #    already FILLED with executedQty. Trusting it avoids any dependence
        #    on follow-up polling (which may fail during API outages).
        sync_res = getattr(self, "last_order_result", {}) or {}
        if str(sync_res.get("orderId", "")) == str(order_id) and sync_res.get("status") in ("FILLED", "PARTIALLY_FILLED"):
            executed_qty = float(sync_res.get("executedQty", 0) or 0)
            if executed_qty > 0:
                avg_fill_price = float(sync_res.get("avgPrice", 0) or 0)
                await self.db.update_order_status(order_id, "FILLED" if sync_res["status"] == "FILLED" else "PARTIALLY_FILLED", executed_qty, avg_fill_price)
                self.logger.info(f"Order {order_id} fill confirmed from placement response ({sync_res['status']}, {executed_qty} units).")
                return True, executed_qty
        timeout = timeout or self.entry_timeout
        start = time.time()
        while time.time() - start < timeout:
            try:
                status = await self.rest.get_order(symbol, order_id)
                if status["status"] == "FILLED":
                    executed_qty = float(status.get("executedQty", 0))
                    avg_fill_price = float(status.get("avgPrice", status.get("price", 0)))
                    await self.db.update_order_status(order_id, "FILLED", executed_qty, avg_fill_price)
                    return True, executed_qty
                elif status["status"] in ["CANCELED", "EXPIRED", "REJECTED"]:
                    await self.db.update_order_status(order_id, status["status"], 0)
                    return status["status"] == "FILLED", float(status.get("executedQty", 0))
            except Exception as e:
                self.logger.warning(f"Polling order {order_id} error: {e}")
            await asyncio.sleep(1)
        # Timeout: try to cancel and handle partial fill
        try:
            status = await self.rest.get_order(symbol, order_id)
            if status["status"] == "PARTIALLY_FILLED":
                executed = float(status.get("executedQty", 0))
                if executed > 0:
                    if self.ws_api and self.ws_api.is_connected():
                        await self.ws_api.cancel_order(symbol, order_id)
                    else:
                        await self.rest.cancel_order(symbol, order_id)
                    avg_fill_price = float(status.get("avgPrice", 0))
                    await self.db.update_order_status(order_id, "CANCELED", executed, avg_fill_price)
                    return True, executed
        except Exception:
            pass
        try:
            if self.ws_api and self.ws_api.is_connected():
                await self.ws_api.cancel_order(symbol, order_id)
            else:
                await self.rest.cancel_order(symbol, order_id)
            await self.db.update_order_status(order_id, "CANCELED", 0)
        except Exception:
            pass
        # The cancel may have raced a fill (market orders can fill between the
        # timeout poll and the cancel). Verify final state so a position that
        # actually filled is never dropped from tracking.
        try:
            final = await self.rest.get_order(symbol, order_id)
            if final["status"] == "FILLED":
                executed = float(final.get("executedQty", 0))
                avg = float(final.get("avgPrice", 0) or 0)
                await self.db.update_order_status(order_id, "FILLED", executed, avg)
                self.logger.info(f"Order {order_id} filled despite cancel attempt (race) — tracking {executed} units.")
                return True, executed
        except Exception:
            pass
        return False, 0
