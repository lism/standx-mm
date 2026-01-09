"""Compare price latency between WebSocket and REST API.

This script tests the timeliness of price data from both sources.
"""
import asyncio
import time
import logging
from statistics import mean, stdev

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
TEST_DURATION_SEC = 30  # Run test for 30 seconds


class PriceCollector:
    """Collect prices from WebSocket."""
    
    def __init__(self):
        self.ws_prices = []  # [(timestamp, price), ...]
        self.ws_client = MarketWSClient()
    
    def on_price(self, data):
        price_data = data.get("data", {})
        last_price = price_data.get("last_price")
        if last_price:
            self.ws_prices.append((time.time(), float(last_price)))
    
    async def start(self):
        await self.ws_client.connect()
        await self.ws_client.subscribe_price(SYMBOL)
        self.ws_client.on_price(self.on_price)
        return asyncio.create_task(self.ws_client.run())
    
    async def stop(self):
        await self.ws_client.close()


async def test_rest_latency(count: int = 20) -> list:
    """Test REST API latency for getting price."""
    latencies = []
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for i in range(count):
            start = time.time()
            response = await client.get(REST_URL)
            latency_ms = (time.time() - start) * 1000
            
            if response.status_code == 200:
                data = response.json()
                price = data.get("last_price", "N/A")
                latencies.append(latency_ms)
                logger.debug(f"REST #{i+1}: {price} in {latency_ms:.0f}ms")
            else:
                logger.warning(f"REST #{i+1}: Failed with {response.status_code}")
            
            await asyncio.sleep(0.5)  # Avoid rate limiting
    
    return latencies


async def main():
    logger.info(f"=== Price Latency Comparison Test ===")
    logger.info(f"Symbol: {SYMBOL}")
    logger.info(f"Test duration: {TEST_DURATION_SEC}s")
    logger.info("")
    
    # Start WebSocket collector
    logger.info("Connecting to WebSocket...")
    collector = PriceCollector()
    ws_task = await collector.start()
    
    # Wait for initial connection
    await asyncio.sleep(2)
    
    # Record WebSocket update frequency
    ws_start_time = time.time()
    ws_start_count = len(collector.ws_prices)
    
    logger.info(f"Running WebSocket collection for {TEST_DURATION_SEC}s...")
    await asyncio.sleep(TEST_DURATION_SEC)
    
    ws_end_time = time.time()
    ws_end_count = len(collector.ws_prices)
    
    # Stop WebSocket
    await collector.stop()
    ws_task.cancel()
    
    # Test REST API
    logger.info("")
    logger.info("Testing REST API latency (20 requests)...")
    rest_latencies = await test_rest_latency(20)
    
    # Calculate results
    ws_updates = ws_end_count - ws_start_count
    ws_duration = ws_end_time - ws_start_time
    ws_rate = ws_updates / ws_duration if ws_duration > 0 else 0
    
    # Calculate intervals between WS updates
    ws_intervals = []
    for i in range(ws_start_count + 1, ws_end_count):
        interval = (collector.ws_prices[i][0] - collector.ws_prices[i-1][0]) * 1000
        ws_intervals.append(interval)
    
    logger.info("")
    logger.info("=" * 50)
    logger.info("Results:")
    logger.info("=" * 50)
    logger.info("")
    
    logger.info("WebSocket:")
    logger.info(f"  Updates received: {ws_updates} in {ws_duration:.1f}s")
    logger.info(f"  Update rate: {ws_rate:.2f} updates/sec")
    if ws_intervals:
        logger.info(f"  Avg interval: {mean(ws_intervals):.0f}ms")
        logger.info(f"  Min interval: {min(ws_intervals):.0f}ms")
        logger.info(f"  Max interval: {max(ws_intervals):.0f}ms")
    
    logger.info("")
    logger.info("REST API:")
    if rest_latencies:
        logger.info(f"  Requests: {len(rest_latencies)}")
        logger.info(f"  Avg latency: {mean(rest_latencies):.0f}ms")
        logger.info(f"  Min latency: {min(rest_latencies):.0f}ms")
        logger.info(f"  Max latency: {max(rest_latencies):.0f}ms")
        if len(rest_latencies) > 1:
            logger.info(f"  Std dev: {stdev(rest_latencies):.0f}ms")
    
    logger.info("")
    logger.info("Conclusion:")
    if ws_intervals and rest_latencies:
        ws_avg = mean(ws_intervals)
        rest_avg = mean(rest_latencies)
        if ws_avg < rest_avg:
            logger.info(f"  WebSocket is faster by {rest_avg - ws_avg:.0f}ms on average")
        else:
            logger.info(f"  REST API is faster by {ws_avg - rest_avg:.0f}ms on average")


if __name__ == "__main__":
    asyncio.run(main())
