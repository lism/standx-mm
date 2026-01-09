"""Compare price update timing between WebSocket and REST API.

This script runs both methods simultaneously and records which one
detects price changes first.
"""
import asyncio
import time
import logging
from datetime import datetime
from collections import deque

import httpx

from api.ws_client import MarketWSClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


SYMBOL = "BTC-USD"
REST_URL = f"https://perps.standx.com/api/query_symbol_price?symbol={SYMBOL}"
REST_POLL_INTERVAL_MS = 200  # Poll every 200ms
TEST_DURATION_SEC = 60  # Run test for 60 seconds


class PriceRaceTracker:
    """Track which method detects price changes first."""
    
    def __init__(self):
        self.ws_prices = deque(maxlen=100)  # [(timestamp, price)]
        self.rest_prices = deque(maxlen=100)
        self.ws_first_count = 0
        self.rest_first_count = 0
        self.same_time_count = 0
        self.price_changes = []  # [(new_price, ws_time, rest_time, winner)]
        self.last_known_price = None
        self._lock = asyncio.Lock()
    
    async def on_ws_price(self, price: float):
        """Called when WebSocket receives a price."""
        now = time.time()
        async with self._lock:
            self.ws_prices.append((now, price))
            self._check_new_price(price, "WS", now)
    
    async def on_rest_price(self, price: float, latency_ms: float):
        """Called when REST API returns a price."""
        # Adjust time to account for request duration (use midpoint)
        now = time.time() - (latency_ms / 1000 / 2)
        async with self._lock:
            self.rest_prices.append((now, price))
            self._check_new_price(price, "REST", now)
    
    def _check_new_price(self, price: float, source: str, timestamp: float):
        """Check if this is a new price and who saw it first."""
        if self.last_known_price is None:
            self.last_known_price = price
            return
        
        if abs(price - self.last_known_price) < 0.001:
            return  # Same price, no change
        
        # New price detected!
        new_price = price
        old_price = self.last_known_price
        self.last_known_price = price
        
        # Find when each method first saw this price
        ws_time = None
        rest_time = None
        
        for ts, p in self.ws_prices:
            if abs(p - new_price) < 0.001:
                ws_time = ts
                break
        
        for ts, p in self.rest_prices:
            if abs(p - new_price) < 0.001:
                rest_time = ts
                break
        
        # Determine winner
        if ws_time and rest_time:
            diff_ms = (rest_time - ws_time) * 1000
            if abs(diff_ms) < 10:  # Within 10ms = tie
                winner = "TIE"
                self.same_time_count += 1
            elif ws_time < rest_time:
                winner = "WS"
                self.ws_first_count += 1
            else:
                winner = "REST"
                self.rest_first_count += 1
            
            logger.info(
                f"Price change: {old_price:.2f} -> {new_price:.2f} | "
                f"Winner: {winner} (diff: {diff_ms:+.0f}ms)"
            )
            self.price_changes.append((new_price, ws_time, rest_time, winner, diff_ms))
        elif ws_time:
            winner = "WS"
            self.ws_first_count += 1
            logger.info(f"Price change: {old_price:.2f} -> {new_price:.2f} | Winner: WS (REST missed)")
        elif rest_time:
            winner = "REST"
            self.rest_first_count += 1
            logger.info(f"Price change: {old_price:.2f} -> {new_price:.2f} | Winner: REST (WS missed)")
    
    def print_summary(self):
        """Print final summary."""
        total = self.ws_first_count + self.rest_first_count + self.same_time_count
        logger.info("")
        logger.info("=" * 60)
        logger.info("Price Change Detection Race Results")
        logger.info("=" * 60)
        logger.info(f"Total price changes detected: {total}")
        logger.info(f"  WebSocket first:  {self.ws_first_count} ({self.ws_first_count/total*100:.1f}%)" if total else "  WebSocket first:  0")
        logger.info(f"  REST first:       {self.rest_first_count} ({self.rest_first_count/total*100:.1f}%)" if total else "  REST first:       0")
        logger.info(f"  Tie (<10ms):      {self.same_time_count} ({self.same_time_count/total*100:.1f}%)" if total else "  Tie:              0")
        
        if self.price_changes:
            diffs = [d for _, _, _, _, d in self.price_changes if d is not None]
            if diffs:
                avg_diff = sum(diffs) / len(diffs)
                logger.info(f"  Avg time diff:    {avg_diff:+.0f}ms (positive = REST slower)")


async def ws_collector(tracker: PriceRaceTracker, shutdown_event: asyncio.Event):
    """Collect prices from WebSocket."""
    ws_client = MarketWSClient()
    
    def on_price(data):
        price_data = data.get("data", {})
        last_price = price_data.get("last_price")
        if last_price:
            asyncio.create_task(tracker.on_ws_price(float(last_price)))
    
    try:
        await ws_client.connect()
        await ws_client.subscribe_price(SYMBOL)
        ws_client.on_price(on_price)
        
        # Run until shutdown
        ws_task = asyncio.create_task(ws_client.run())
        await shutdown_event.wait()
        await ws_client.close()
        ws_task.cancel()
    except Exception as e:
        logger.error(f"WS error: {e}")


async def rest_poller(tracker: PriceRaceTracker, shutdown_event: asyncio.Event):
    """Poll prices from REST API."""
    interval_sec = REST_POLL_INTERVAL_MS / 1000.0
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        while not shutdown_event.is_set():
            try:
                start = time.time()
                response = await client.get(REST_URL)
                latency_ms = (time.time() - start) * 1000
                
                if response.status_code == 200:
                    data = response.json()
                    price = data.get("last_price")
                    if price:
                        await tracker.on_rest_price(float(price), latency_ms)
            except Exception as e:
                logger.warning(f"REST error: {e}")
            
            await asyncio.sleep(interval_sec)


async def main():
    logger.info("=" * 60)
    logger.info("WebSocket vs REST Price Update Race Test")
    logger.info("=" * 60)
    logger.info(f"Symbol: {SYMBOL}")
    logger.info(f"REST poll interval: {REST_POLL_INTERVAL_MS}ms")
    logger.info(f"Test duration: {TEST_DURATION_SEC}s")
    logger.info("")
    logger.info("Starting both collectors...")
    
    tracker = PriceRaceTracker()
    shutdown_event = asyncio.Event()
    
    # Start both collectors
    ws_task = asyncio.create_task(ws_collector(tracker, shutdown_event))
    rest_task = asyncio.create_task(rest_poller(tracker, shutdown_event))
    
    # Wait for initial connection
    await asyncio.sleep(2)
    logger.info(f"Running for {TEST_DURATION_SEC}s, watching for price changes...")
    logger.info("")
    
    # Run for test duration
    await asyncio.sleep(TEST_DURATION_SEC)
    
    # Shutdown
    shutdown_event.set()
    await asyncio.sleep(1)
    
    # Print results
    tracker.print_summary()


if __name__ == "__main__":
    asyncio.run(main())
