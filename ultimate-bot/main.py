#!/usr/bin/env python3
import asyncio
import logging
import signal
import sys
import fcntl
from dotenv import load_dotenv
from src.core.health_check import HealthCheck
from src.core.error_handler import ErrorHandler
from src.exchange.rest_client import RestClient
from src.exchange.ws_api_client import WSApiClient
from src.exchange.ws_stream_client import WSStreamClient
from src.database.db_manager import DatabaseManager
from src.risk.risk_manager import RiskManager
from src.strategies.signal_generator import SignalGenerator
from src.strategies.trend_detector import TrendDetector
from src.trade.order_manager import OrderManager
from src.trade.trade_logic import TradeLogic
from src.reporting.discord_webhook import DiscordWebhook
from config import load_config
from src.utils.helpers import setup_logging

load_dotenv()
config = load_config()

lock_file = open("/tmp/ultimate_bot.lock", "w")
try:
    fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    print("Another instance is already running. Exiting.")
    sys.exit(1)

shutdown_event = asyncio.Event()

async def shutdown(sig, loop):
    logging.getLogger(__name__).info(f"Received signal {sig}, shutting down...")
    shutdown_event.set()
    await asyncio.sleep(2)
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()

async def main():
    setup_logging(config)
    logger = logging.getLogger(__name__)
    mode_str = "PAPER TRADING" if config["PAPER_TRADE"] else "LIVE EXECUTION"
    logger.info(f"Starting MARKET-ONLY BOT [{mode_str}] with PRESET={config['PRESET']}")

    db = DatabaseManager(config["DB_PATH"])
    await db.init()

    rest = RestClient(config)
    await rest.init()

    ws_api = WSApiClient(config) if not config["PAPER_TRADE"] else None
    ws_stream = WSStreamClient(config)
    risk = RiskManager(config, db, rest)
    await risk.load_state()

    trend_detector = TrendDetector(config, rest)
    signal_gen = SignalGenerator(config, rest)
    order_mgr = OrderManager(config, db, rest, ws_api, risk_mgr=risk)
    webhook = DiscordWebhook(config["DISCORD_WEBHOOK_URL"], config["DISCORD_COOLDOWN"])

    trade_logic = TradeLogic(
        config, order_mgr, risk, signal_gen, trend_detector,
        db, rest, ws_stream, webhook
    )

    def get_current_symbols():
        return trade_logic.current_symbols if trade_logic.current_symbols else config["STATIC_SYMBOLS"]

    health = HealthCheck(
        config, rest, ws_api, ws_stream, db, webhook,
        get_symbols_func=get_current_symbols,
        enable_ws=True
    )
    trade_logic.health_check = health

    error_handler = ErrorHandler(webhook)

    try:
        if not config["PAPER_TRADE"] and ws_api:
            try:
                await ws_api.connect()
            except Exception as e:
                # Order execution falls back to REST automatically (OrderManager
                # checks is_connected()); do NOT let a WS API outage at startup
                # kill the bot. HealthCheck keeps retrying the connection.
                logger.error(f"WebSocket API unavailable at startup ({e}); continuing with REST-only order execution.")
                try:
                    await ws_api.disconnect()
                except Exception:
                    pass

        await trade_logic.update_symbols()
        await trade_logic.reconcile_positions()

        # Connect public WebSocket market stream for real-time tick prices
        try:
            await ws_stream.connect(trade_logic.current_symbols)
        except Exception as e:
            logger.warning(f"WebSocket stream initial connect issue (falling back to REST): {e}")

        # Keep strong references to background loops so they are never garbage-collected mid-run
        background_tasks = [
            asyncio.create_task(health.run()),
            asyncio.create_task(trade_logic.run()),
            asyncio.create_task(trade_logic.refresh_symbols_loop()),
            asyncio.create_task(trade_logic.send_daily_report_loop()),
        ]

        while not shutdown_event.is_set():
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received.")
    except Exception as e:
        await error_handler.handle(e, "main_loop")
    finally:
        if ws_api:
            await ws_api.disconnect()
        await ws_stream.disconnect()
        await db.close()
        await rest.close()
        await webhook.close()
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s, loop)))
    try:
        loop.run_until_complete(main())
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)
        loop.close()
