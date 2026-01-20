"""Query StandX account status - points and maker uptime.

Usage:
    python query_status.py
    python query_status.py --config config_account2.yaml
"""
import asyncio
import argparse
from datetime import datetime, timezone

import httpx

from config import load_config
from api.auth import StandXAuth


async def query_trading_points(auth: StandXAuth) -> dict:
    """Query trading campaign points (Trader Points)."""
    url = "https://api.standx.com/v1/offchain/trading-campaign/points"
    headers = {"Authorization": f"Bearer {auth.token}", "Accept": "application/json"}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()


async def query_maker_points(auth: StandXAuth) -> dict:
    """Query maker campaign points (Maker Points)."""
    url = "https://api.standx.com/v1/offchain/maker-campaign/points"
    headers = {"Authorization": f"Bearer {auth.token}", "Accept": "application/json"}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()


async def query_perps_points(auth: StandXAuth) -> dict:
    """Query perps campaign points (Holder Points)."""
    url = "https://api.standx.com/v1/offchain/perps-campaign/points"
    headers = {"Authorization": f"Bearer {auth.token}", "Accept": "application/json"}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()


async def query_uptime(auth: StandXAuth) -> dict:
    """Query maker uptime hours."""
    url = "https://perps.standx.com/api/maker/uptime"
    
    # This endpoint needs request signature
    payload = ""
    headers = auth.get_auth_headers(payload)
    headers["Accept"] = "application/json"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()


async def query_balance(auth: StandXAuth) -> dict:
    """Query account balance and equity."""
    url = "https://perps.standx.com/api/query_balance"
    headers = auth.get_auth_headers()
    headers["Accept"] = "application/json"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        return response.json()


def format_points(value) -> str:
    """Format points value (in millions) for display."""
    if value is None:
        return "0"
    try:
        num = float(value)
        if num >= 1_000_000:
            return f"{num / 1_000_000:.1f}"
        elif num >= 1000:
            return f"{num / 1000:.1f}K"
        else:
            return f"{num:.1f}"
    except:
        return str(value)


def format_hour(iso_time: str) -> str:
    """Format ISO time to readable format like '1月7日 09:00'."""
    try:
        dt = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
        # Convert to local time (UTC+8)
        local_dt = dt.astimezone()
        return f"{local_dt.month}月{local_dt.day}日 {local_dt.strftime('%H:%M')}"
    except:
        return iso_time[:16]


def tier_to_name(tier: str) -> str:
    """Convert tier code to display name."""
    tier_map = {
        "tier_a": "Green",
        "tier_b": "Light Green",
        "tier_c": "Yellow",
        "tier_d": "Gray",
        "": "Gray",
        None: "Gray",
    }
    return tier_map.get(tier, tier or "Gray")


async def main(config_path: str):
    """Query and display account status."""
    
    # Load config
    config = load_config(config_path)
    print(f"Loading config: {config_path}")
    
    # Authenticate
    auth = StandXAuth()
    await auth.authenticate(
        chain=config.wallet.chain,
        private_key=config.wallet.private_key,
        api_token=config.wallet.api_token,
        api_secret=config.wallet.api_secret
    )
    print("Authentication successful\n")
    
    # Query all data
    trading_data = {}
    maker_data = {}
    perps_data = {}
    uptime_data = {}
    
    try:
        trading_data = await query_trading_points(auth)
    except Exception as e:
        print(f"Warning: Failed to query trading points: {e}")
    
    try:
        maker_data = await query_maker_points(auth)
    except Exception as e:
        print(f"Warning: Failed to query maker points: {e}")
    
    try:
        perps_data = await query_perps_points(auth)
    except Exception as e:
        print(f"Warning: Failed to query perps points: {e}")
    
    try:
        uptime_data = await query_uptime(auth)
    except Exception as e:
        print(f"Warning: Failed to query uptime: {e}")
    
    balance_data = {}
    try:
        balance_data = await query_balance(auth)
    except Exception as e:
        print(f"Warning: Failed to query balance: {e}")
    
    # Display Account Summary
    print("=" * 60)
    print("Account Summary")
    print("=" * 60)
    
    equity = float(balance_data.get("equity", 0) or 0)
    balance = float(balance_data.get("balance", 0) or 0)
    upnl = float(balance_data.get("upnl", 0) or 0)
    
    print(f"Equity (Net):    ${equity:,.2f}")
    print(f"Balance:         ${balance:,.2f}")
    print(f"Unrealized PnL:  ${upnl:,.2f}")
    
    # Display Points Summary
    print("\n" + "=" * 60)
    print("Points Summary")
    print("=" * 60)
    
    trader_points = trading_data.get("trading_point", 0)
    maker_points = maker_data.get("maker_point", 0)
    # perps-campaign uses total_point, total_amount (in micro units)
    holder_points = perps_data.get("total_point", 0)
    holding_value_raw = perps_data.get("total_amount", 0)
    holding_value = float(holding_value_raw or 0) / 1_000_000  # Convert from micro units
    
    print(f"Trader Points:   {format_points(trader_points)}")
    print(f"Maker Points:    {format_points(maker_points)}")
    print(f"Holder Points:   {format_points(holder_points)}")
    print(f"Holding Value:   ${holding_value:,.2f}")
    
    # Display Uptime Table
    print("\n" + "=" * 60)
    print("Maker Uptime (Recent Hours)")
    print("=" * 60)
    
    hours = uptime_data.get("hours", [])
    total_hours = uptime_data.get("total_eligible_hours", 0)
    
    print(f"Total Eligible Hours: {total_hours:.4f}\n")
    
    # Table header
    print(f"{'Time':<18} {'Tier':<14} {'Eligible':<10} {'P70':<10} {'P50':<10}")
    print("-" * 60)
    
    # Reverse to show most recent first
    for h in reversed(hours):
        time_str = format_hour(h.get("hour", ""))
        tier = tier_to_name(h.get("tier", ""))
        eligible = h.get("eligible_hour", 0)
        x70 = h.get("x70", 0)
        x50 = h.get("x50", 0)
        
        print(f"{time_str:<18} {tier:<14} {eligible:<10.4f} {x70:<10.4f} {x50:<10.4f}")
    
    print("-" * 60)


def parse_args():
    parser = argparse.ArgumentParser(description="Query StandX Account Status")
    parser.add_argument(
        "--config", "-c",
        default="config.yaml",
        help="Path to config file (default: config.yaml)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args.config))
