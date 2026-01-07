"""WebSocket client for StandX Perps API.

Handles two WebSocket connections:
1. Market stream (wss://perps.standx.com/ws-stream/v1) - price data
2. User stream (wss://perps.standx.com/ws-api/v1) - order/position updates

Both clients support auto-reconnection.
"""
import json
import asyncio
import logging
from typing import Optional, Callable

import websockets
from websockets.client import WebSocketClientProtocol

from .auth import StandXAuth


logger = logging.getLogger(__name__)


class MarketWSClient:
    """WebSocket client for market data stream with auto-reconnection."""
    
    WS_URL = "wss://perps.standx.com/ws-stream/v1"
    RECONNECT_DELAY = 5  # seconds
    
    def __init__(self):
        self._ws: Optional[WebSocketClientProtocol] = None
        self._running = False
        self._callbacks: dict[str, list[Callable]] = {}
        self._subscribed_symbols: list[str] = []
        self._msg_count = 0
        self._last_log_time = 0
    
    async def connect(self):
        """Connect to market data stream."""
        logger.info(f"Connecting to market stream: {self.WS_URL}")
        self._ws = await websockets.connect(
            self.WS_URL,
            ping_interval=None,  # Server sends ping, we just respond
            ping_timeout=60,     # Long timeout to avoid false disconnects
            close_timeout=10,
        )
        self._running = True
        logger.info("Market stream connected")
    
    async def subscribe_price(self, symbol: str):
        """Subscribe to price channel for a symbol."""
        if symbol not in self._subscribed_symbols:
            self._subscribed_symbols.append(symbol)
        
        if self._ws:
            msg = {"subscribe": {"channel": "price", "symbol": symbol}}
            await self._ws.send(json.dumps(msg))
            logger.info(f"Subscribed to price channel for {symbol}")
    
    def on_price(self, callback: Callable[[dict], None]):
        """Register callback for price updates."""
        if "price" not in self._callbacks:
            self._callbacks["price"] = []
        self._callbacks["price"].append(callback)
    
    async def _reconnect(self):
        """Reconnect and resubscribe."""
        logger.info(f"Reconnecting in {self.RECONNECT_DELAY} seconds...")
        await asyncio.sleep(self.RECONNECT_DELAY)
        
        try:
            await self.connect()
            # Resubscribe to all symbols
            for symbol in self._subscribed_symbols:
                msg = {"subscribe": {"channel": "price", "symbol": symbol}}
                await self._ws.send(json.dumps(msg))
                logger.info(f"Resubscribed to price channel for {symbol}")
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
            return False
        
        return True
    
    async def run(self):
        """Run the message receive loop with auto-reconnection."""
        self._running = True
        
        while self._running:
            if not self._ws:
                if not await self._reconnect():
                    continue
            
            try:
                message = await self._ws.recv()
                data = json.loads(message)
                self._msg_count += 1
                
                # Log heartbeat every 10 seconds
                import time
                now = time.time()
                if now - self._last_log_time >= 10:
                    logger.info(f"[Heartbeat] Market WS alive, {self._msg_count} msgs total")
                    self._last_log_time = now
                
                # Handle server ping (JSON-based)
                if data.get("ping"):
                    await self._ws.send(json.dumps({"pong": data["ping"]}))
                    continue
                
                # Dispatch to callbacks
                channel = data.get("channel")
                if channel in self._callbacks:
                    for callback in self._callbacks[channel]:
                        try:
                            callback(data)
                        except Exception as e:
                            logger.error(f"Callback error: {e}")
                            
            except websockets.ConnectionClosed as e:
                logger.warning(f"Market stream connection closed: {e}")
                self._ws = None
                if self._running:
                    continue  # Will reconnect in next iteration
            except Exception as e:
                logger.error(f"Error in market stream: {e}")
                self._ws = None
                if self._running:
                    await asyncio.sleep(1)
                    continue
    
    async def close(self):
        """Close the WebSocket connection."""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None


class UserWSClient:
    """WebSocket client for user data stream (orders, positions) with auto-reconnection."""
    
    WS_URL = "wss://perps.standx.com/ws-api/v1"
    RECONNECT_DELAY = 5  # seconds
    
    def __init__(self, auth: StandXAuth):
        self._auth = auth
        self._ws: Optional[WebSocketClientProtocol] = None
        self._running = False
        self._session_id: Optional[str] = None
        self._callbacks: dict[str, list[Callable]] = {}
    
    async def connect(self):
        """Connect to user data stream."""
        import uuid
        
        logger.info(f"Connecting to user stream: {self.WS_URL}")
        self._ws = await websockets.connect(
            self.WS_URL,
            ping_interval=None,  # Server sends ping, we just respond
            ping_timeout=60,     # Long timeout to avoid false disconnects
            close_timeout=10,
        )
        self._session_id = str(uuid.uuid4())
        self._running = True
        logger.info("User stream connected")
        
        # Authenticate
        await self._authenticate()
    
    async def _authenticate(self):
        """Authenticate the WebSocket connection."""
        if not self._ws or not self._auth.token:
            raise RuntimeError("WebSocket not connected or not authenticated")
        
        import uuid
        msg = {
            "session_id": self._session_id,
            "request_id": str(uuid.uuid4()),
            "method": "auth:login",
            "params": json.dumps({"token": self._auth.token}),
        }
        
        await self._ws.send(json.dumps(msg))
        logger.info("User stream authentication sent")
        
        # Wait for auth response
        response = await self._ws.recv()
        data = json.loads(response)
        
        if data.get("code") != 0:
            raise RuntimeError(f"User stream auth failed: {data}")
        
        logger.info("User stream authenticated")
        
        # Subscribe to order and position channels
        await self._ws.send(json.dumps({"subscribe": {"channel": "order"}}))
        logger.info("Subscribed to order channel")
        
        await self._ws.send(json.dumps({"subscribe": {"channel": "position"}}))
        logger.info("Subscribed to position channel")
    
    async def _reconnect(self):
        """Reconnect and re-authenticate."""
        logger.info(f"Reconnecting user stream in {self.RECONNECT_DELAY} seconds...")
        await asyncio.sleep(self.RECONNECT_DELAY)
        
        try:
            await self.connect()
        except Exception as e:
            logger.error(f"User stream reconnection failed: {e}")
            return False
        
        return True
    
    def on_order(self, callback: Callable[[dict], None]):
        """Register callback for order updates."""
        if "order" not in self._callbacks:
            self._callbacks["order"] = []
        self._callbacks["order"].append(callback)
    
    def on_position(self, callback: Callable[[dict], None]):
        """Register callback for position updates."""
        if "position" not in self._callbacks:
            self._callbacks["position"] = []
        self._callbacks["position"].append(callback)
    
    def on_trade(self, callback: Callable[[dict], None]):
        """Register callback for trade updates."""
        if "trade" not in self._callbacks:
            self._callbacks["trade"] = []
        self._callbacks["trade"].append(callback)
    
    async def run(self):
        """Run the message receive loop with auto-reconnection."""
        self._running = True
        
        while self._running:
            if not self._ws:
                if not await self._reconnect():
                    continue
            
            try:
                message = await self._ws.recv()
                data = json.loads(message)
                
                # Handle server ping (JSON-based)
                if data.get("ping"):
                    await self._ws.send(json.dumps({"pong": data["ping"]}))
                    continue
                
                # Dispatch to callbacks based on channel
                channel = data.get("channel")
                if channel in self._callbacks:
                    for callback in self._callbacks[channel]:
                        try:
                            callback(data)
                        except Exception as e:
                            logger.error(f"Callback error: {e}")
                            
            except websockets.ConnectionClosed as e:
                logger.warning(f"User stream connection closed: {e}")
                self._ws = None
                if self._running:
                    continue  # Will reconnect in next iteration
            except Exception as e:
                logger.error(f"Error in user stream: {e}")
                self._ws = None
                if self._running:
                    await asyncio.sleep(1)
                    continue
    
    async def close(self):
        """Close the WebSocket connection."""
        self._running = False
        if self._ws:
            await self._ws.close()
            self._ws = None
