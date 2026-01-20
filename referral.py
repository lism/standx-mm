"""StandX Referral Script.

Checks if account is referred, if not, applies referral code.

Usage:
    python referral.py config.yaml
    python referral.py -c config-bot2.yaml
"""
import json
import time
import uuid
import base64
import asyncio
import argparse

import requests
import httpx

from config import load_config
from api.auth import StandXAuth


REFERRAL_CODE = "frozenbanana"
REFERRAL_URL = f"https://standx.com/referral?code={REFERRAL_CODE}"


async def check_if_referred(auth: StandXAuth) -> bool:
    """Check if account is already referred by querying points."""
    url = "https://api.standx.com/v1/offchain/perps-campaign/points"
    headers = {"Authorization": f"Bearer {auth.token}", "Accept": "application/json"}
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            refer_at = data.get("refer_at")
            if refer_at:
                return True
    return False


async def apply_referral(auth: StandXAuth, referral_code: str) -> dict:
    """Apply referral code to the account."""
    url = "https://api.standx.com/v1/offchain/referral"
    
    body = json.dumps({"referralCode": referral_code}, separators=(',', ':'))
    
    # Use existing auth method for request signature
    headers = auth.get_auth_headers(body)
    
    # Add body signature (required for this endpoint)
    body_signed = auth._signing_key.sign(body.encode())
    headers["x-body-signature"] = base64.b64encode(body_signed.signature).decode()
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, content=body, headers=headers)
        return response.json()


async def main(config_path: str):
    """Main entry point."""
    print(f"Loading config: {config_path}")
    config = load_config(config_path)
    
    print(f"Authenticating wallet on chain: {config.wallet.chain}")
    auth = StandXAuth()
    await auth.authenticate(
        chain=config.wallet.chain,
        private_key=config.wallet.private_key,
        api_token=config.wallet.api_token,
        api_secret=config.wallet.api_secret
    )
    print("Authentication successful")
    
    # Check if already referred
    print("Checking referral status...")
    is_referred = await check_if_referred(auth)
    
    if is_referred:
        print("✓ Account is already referred. No action needed.")
        return
    
    print(f"Account is NOT referred. Applying referral code: {REFERRAL_CODE}")
    
    try:
        result = await apply_referral(auth, REFERRAL_CODE)
        
        if result.get("success") or result.get("code") == 0:
            print(f"✓ Referral applied successfully!")
            print(f"  Response: {result}")
        else:
            print(f"✗ Referral failed: {result}")
            
    except Exception as e:
        print(f"✗ Error applying referral: {e}")


def parse_args():
    parser = argparse.ArgumentParser(description="StandX Referral Script")
    parser.add_argument(
        "config",
        nargs="?",
        default=None,
        help="Config file path",
    )
    parser.add_argument(
        "-c", "--config-file",
        dest="config_file",
        help="Config file path (alternative)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    
    config_path = args.config or args.config_file
    if not config_path:
        print("Usage: python referral.py config.yaml")
        print("   or: python referral.py -c config.yaml")
        exit(1)
    
    asyncio.run(main(config_path))
