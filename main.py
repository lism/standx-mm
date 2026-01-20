"""StandX Maker Bot - Main entry point.

Usage:
    python main.py
    python main.py --config custom_config.yaml
"""
import sys
import signal
import asyncio
import logging
import argparse

from config import load_config
from api.auth import StandXAuth
from api.http_client import StandXHTTPClient
from api.ws_client import MarketWSClient, UserWSClient
from core.state import State
from core.maker import Maker
from referral import check_if_referred, apply_referral, REFERRAL_CODE


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


async def main(config_path: str):
    """Main async entry point."""
    
    # Load config
    logger.info(f"Loading config from {config_path}")
    config = load_config(config_path)
    logger.info(f"Symbol: {config.symbol}, Order size: {config.order_size_btc} BTC")
    
    # Initialize authentication
    logger.info("Initializing authentication...")
    auth = StandXAuth()
    await auth.authenticate(
        chain=config.wallet.chain,
        private_key=config.wallet.private_key,
        api_token=config.wallet.api_token,
        api_secret=config.wallet.api_secret
    )
    logger.info("Authentication successful")
    
    # Check and apply referral if needed
    try:
        is_referred = await check_if_referred(auth)
        if not is_referred:
            logger.info(f"Account not referred, applying referral code: {REFERRAL_CODE}")
            result = await apply_referral(auth, "frozenbanana")
            if result.get("success") or result.get("code") == 0:
                logger.info("Referral applied successfully")
            else:
                logger.warning(f"Referral failed: {result}")
        else:
            logger.debug("Account already referred")
    except Exception as e:
        logger.warning(f"Referral check/apply failed: {e}")
    
    # Initialize clients
    http_client = StandXHTTPClient(auth)
    
    # Set latency log file based on config name
    config_name = config_path.replace(".yaml", "").replace(".yml", "")
    latency_log_file = f"latency_{config_name}.log"
    http_client.set_latency_log_file(latency_log_file)
    logger.info(f"Latency logging to: {latency_log_file}")
    
    market_ws = MarketWSClient()
    user_ws = UserWSClient(auth)
    
    # Initialize state
    state = State()
    
    # Initialize maker
    maker = Maker(config, http_client, state)
    
    # Set reduce position log file
    reduce_log_file = f"reduce_{config_name}.log"
    maker.set_reduce_log_file(reduce_log_file)
    logger.info(f"Reduce position logging to: {reduce_log_file}")
    
    # Setup shutdown handler
    shutdown_event = asyncio.Event()
    
    def handle_shutdown(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        shutdown_event.set()
    
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    try:
        # Connect WebSockets
        await market_ws.connect()
        await market_ws.subscribe_price(config.symbol)
        
        await user_ws.connect()
        
        # Register price callback - triggers order checks
        def on_price(data):
            price_data = data.get("data", {})
            last_price = price_data.get("last_price")
            if last_price:
                maker.on_price_update(float(last_price))
                logger.debug(f"Price update: {last_price}")
        
        market_ws.on_price(on_price)
        
        # Register order callback to detect fills
        def on_order(data):
            order_data = data.get("data", {})
            status = order_data.get("status")
            cl_ord_id = order_data.get("cl_ord_id", "")
            side = order_data.get("side")
            
            logger.info(f"Order update: cl_ord_id={cl_ord_id}, status={status}, side={side}")
            
            # Clear order from local state if filled or cancelled
            if status in ("filled", "cancelled", "rejected"):
                if side in ("buy", "sell"):
                    current_order = state.get_order(side)
                    if current_order and current_order.cl_ord_id == cl_ord_id:
                        logger.info(f"Order {status}: clearing {side} from state")
                        state.set_order(side, None)
                        
                        # Trigger a check to potentially place new order
                        maker._pending_check.set()
        
        user_ws.on_order(on_order)
        
        # Register position callback to track fills
        def on_position(data):
            pos_data = data.get("data", {})
            qty = float(pos_data.get("qty", 0))
            symbol = pos_data.get("symbol", "")
            
            if symbol == config.symbol:
                logger.info(f"Position update: {symbol} qty={qty}")
                state.update_position(qty)
        
        user_ws.on_position(on_position)
        
        # Initialize state from exchange
        await maker.initialize()
        
        # Start all tasks
        tasks = [
            asyncio.create_task(market_ws.run(), name="market_ws"),
            asyncio.create_task(user_ws.run(), name="user_ws"),
            asyncio.create_task(maker.run(), name="maker"),
            asyncio.create_task(shutdown_event.wait(), name="shutdown"),
        ]
        
        logger.info("Bot started, press Ctrl+C to stop")
        
        # Wait for shutdown or any task to complete
        done, pending = await asyncio.wait(
            tasks,
            return_when=asyncio.FIRST_COMPLETED,
        )
        
        # Stop all running components first
        await maker.stop()
        await market_ws.close()
        await user_ws.close()
        
        # Cancel pending tasks with timeout
        for task in pending:
            task.cancel()
        
        if pending:
            # Wait up to 3 seconds for tasks to finish
            await asyncio.wait(pending, timeout=3.0)
        
    finally:
        # Cancel all open orders on exit
        logger.info("Cleaning up...")
        try:
            orders_to_cancel = []
            if state.has_order("buy"):
                orders_to_cancel.append(state.get_order("buy").cl_ord_id)
            if state.has_order("sell"):
                orders_to_cancel.append(state.get_order("sell").cl_ord_id)
            
            if orders_to_cancel:
                logger.info(f"Cancelling {len(orders_to_cancel)} orders on exit: {orders_to_cancel}")
                await http_client.cancel_orders(orders_to_cancel)
                state.clear_all_orders()
                logger.info("All orders cancelled successfully")
        except Exception as e:
            logger.error(f"Failed to cancel orders on exit: {e}")
        
        await http_client.close()
        logger.info("Shutdown complete")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="StandX Maker Bot")
    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args.config))
