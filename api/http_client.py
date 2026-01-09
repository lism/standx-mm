"""HTTP client for StandX Perps API."""
import json
import time
import logging
from typing import Optional, List
from dataclasses import dataclass
from datetime import datetime

import httpx

from .auth import StandXAuth


logger = logging.getLogger(__name__)


@dataclass
class Order:
    """Represents an open order."""
    id: int
    cl_ord_id: str
    side: str
    price: str
    qty: str
    status: str
    symbol: str


@dataclass 
class Position:
    """Represents a position."""
    qty: float
    entry_price: float
    upnl: float


class StandXHTTPClient:
    """HTTP client for StandX Perps API."""
    
    BASE_URL = "https://perps.standx.com"
    
    def __init__(self, auth: StandXAuth, latency_log_file: str = None):
        self._auth = auth
        self._client = httpx.AsyncClient(timeout=30.0)
        self._latency_log_file = latency_log_file
    
    def set_latency_log_file(self, filepath: str):
        """Set the file path for latency logging."""
        self._latency_log_file = filepath
    
    def _write_latency(self, endpoint: str, latency_ms: float):
        """Write latency record to log file."""
        if not self._latency_log_file:
            return
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(self._latency_log_file, "a") as f:
                f.write(f"{timestamp},{endpoint},{latency_ms:.0f}\n")
        except:
            pass  # Don't let logging failure affect trading
    
    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()
    
    async def new_order(
        self,
        symbol: str,
        side: str,
        qty: str,
        price: str,
        cl_ord_id: str,
        order_type: str = "limit",
        time_in_force: str = "gtc",
        reduce_only: bool = False,
    ) -> dict:
        """
        Place a new order.
        
        Args:
            symbol: Trading pair (e.g., BTC-USD)
            side: Order side (buy or sell)
            qty: Order quantity
            price: Order price
            cl_ord_id: Client order ID for tracking
            order_type: Order type (limit, market)
            time_in_force: Time in force (gtc, ioc, fok)
            reduce_only: Whether this is a reduce-only order
            
        Returns:
            API response
        """
        payload = {
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "qty": qty,
            "price": price,
            "time_in_force": time_in_force,
            "reduce_only": reduce_only,
            "cl_ord_id": cl_ord_id,
        }
        
        return await self._post("/api/new_order", payload, sign=True)
    
    async def cancel_order(self, cl_ord_id: str) -> dict:
        """
        Cancel an order by client order ID.
        
        Args:
            cl_ord_id: Client order ID
            
        Returns:
            API response
        """
        payload = {"cl_ord_id": cl_ord_id}
        return await self._post("/api/cancel_order", payload, sign=True)
    
    async def cancel_orders(self, cl_ord_ids: List[str]) -> dict:
        """
        Cancel multiple orders by client order IDs.
        
        Args:
            cl_ord_ids: List of client order IDs
            
        Returns:
            API response
        """
        payload = {"cl_ord_id_list": cl_ord_ids}
        return await self._post("/api/cancel_orders", payload, sign=True)
    
    async def query_open_orders(self, symbol: Optional[str] = None) -> List[Order]:
        """
        Query open orders.
        
        Args:
            symbol: Optional symbol filter
            
        Returns:
            List of open orders
        """
        params = {}
        if symbol:
            params["symbol"] = symbol
        
        response = await self._get("/api/query_open_orders", params)
        orders = []
        for item in response.get("result", []):
            orders.append(Order(
                id=item["id"],
                cl_ord_id=item.get("cl_ord_id", ""),
                side=item["side"],
                price=item["price"],
                qty=item["qty"],
                status=item["status"],
                symbol=item["symbol"],
            ))
        return orders
    
    async def query_positions(self, symbol: Optional[str] = None) -> List[Position]:
        """
        Query positions.
        
        Args:
            symbol: Optional symbol filter
            
        Returns:
            List of positions
        """
        params = {}
        if symbol:
            params["symbol"] = symbol
        
        response = await self._get("/api/query_positions", params)
        positions = []
        
        # Response is a list directly
        if isinstance(response, list):
            items = response
        else:
            items = response.get("result", [])
        
        for item in items:
            positions.append(Position(
                qty=float(item.get("qty", 0)),
                entry_price=float(item.get("entry_price", 0)),
                upnl=float(item.get("upnl", 0)),
            ))
        return positions
    
    async def query_price(self, symbol: str) -> dict:
        """
        Query current price.
        
        Args:
            symbol: Trading pair
            
        Returns:
            Price data including last_price, mark_price, index_price
        """
        params = {"symbol": symbol}
        return await self._get("/api/query_symbol_price", params, auth=False)
    
    async def _get(self, path: str, params: dict = None, auth: bool = True) -> dict:
        """Make a GET request."""
        url = f"{self.BASE_URL}{path}"
        headers = {}
        
        if auth:
            headers = self._auth.get_auth_headers()
        
        response = await self._client.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response.json()
    
    async def _post(self, path: str, payload: dict, sign: bool = False) -> dict:
        """Make a POST request with latency tracking."""
        url = f"{self.BASE_URL}{path}"
        payload_str = json.dumps(payload)
        
        if sign:
            headers = self._auth.get_auth_headers(payload_str)
        else:
            headers = self._auth.get_auth_headers()
        
        logger.debug(f"POST {path}: {payload_str}")
        
        start_time = time.time()
        response = await self._client.post(url, content=payload_str, headers=headers)
        latency_ms = (time.time() - start_time) * 1000
        
        # Log response for debugging
        if response.status_code >= 400:
            logger.error(f"API error {response.status_code}: {response.text}")
        
        response.raise_for_status()
        
        result = response.json()
        logger.info(f"[Latency] {path} responded in {latency_ms:.0f}ms")
        
        # Write latency to log file
        self._write_latency(path, latency_ms)
        
        return result
