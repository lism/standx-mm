"""Authentication module for StandX API.

Handles:
- Ed25519 key pair generation
- JWT token acquisition via wallet signature
- Request signing for authenticated endpoints
"""
import time
import uuid
import json
import base64
import hashlib
from typing import Optional, Callable, Awaitable

import httpx
from nacl.signing import SigningKey
from nacl.encoding import RawEncoder
from eth_account import Account
from eth_account.messages import encode_defunct


class StandXAuth:
    """Handles StandX API authentication."""
    
    BASE_URL = "https://api.standx.com"
    
    def __init__(self):
        # Generate temporary Ed25519 key pair
        self._signing_key = SigningKey.generate()
        self._verify_key = self._signing_key.verify_key
        
        # requestId is the base58-encoded public key
        self._request_id = self._base58_encode(bytes(self._verify_key))
        
        # JWT token (obtained after authentication)
        self._token: Optional[str] = None
        self._token_expires_at: float = 0
    
    @property
    def token(self) -> Optional[str]:
        """Get current JWT token."""
        return self._token
    
    @property
    def is_authenticated(self) -> bool:
        """Check if we have a valid token."""
        return self._token is not None and time.time() < self._token_expires_at
    
    async def authenticate(self, chain: str, private_key: Optional[str] = None, api_token: Optional[str] = None, api_secret: Optional[str] = None) -> str:
        """
        Authenticate with StandX.
        
        Args:
            chain: Blockchain chain (bsc or solana)
            private_key: Wallet private key (for wallet auth)
            api_token: Pre-generated API token (skips wallet auth)
            api_secret: Ed25519 private key seed (base58 or hex) for signing requests (required if using api_token with signed endpoints)
            
        Returns:
            JWT access token
        """
        if api_secret:
            try:
                # Try base58 decoding first, then hex
                try:
                    seed = self._base58_decode(api_secret)
                except Exception:
                    # Fallback to hex decoding
                    seed = bytes.fromhex(api_secret.replace("0x", ""))
                
                self._signing_key = SigningKey(seed)
                self._verify_key = self._signing_key.verify_key
                self._request_id = self._base58_encode(bytes(self._verify_key))
            except Exception as e:
                # Fallback or logging could be added here
                print(f"Warning: Failed to load api_secret: {e}")

        if api_token:
            self._token = api_token
            self._token_expires_at = float('inf')
            return self._token

        if not private_key:
            raise ValueError("private_key is required if api_token is not provided")

        async with httpx.AsyncClient() as client:
            # Step 1: Get signature data
            wallet_address = self._get_wallet_address(chain, private_key)
            signed_data = await self._prepare_sign_in(client, chain, wallet_address)
            
            # Step 2: Parse message from signed data
            payload = self._parse_jwt(signed_data)
            message = payload["message"]
            
            # Step 3: Sign message with wallet
            signature = self._sign_message(chain, private_key, message)
            
            # Step 4: Login to get access token
            login_response = await self._login(client, chain, signature, signed_data)
            
            self._token = login_response["token"]
            # Token expires in 7 days by default
            self._token_expires_at = time.time() + 7 * 24 * 60 * 60
            
            return self._token
    
    def sign_request(self, payload: str) -> dict:
        """
        Sign a request payload for authenticated endpoints.
        
        Args:
            payload: JSON string of request body
            
        Returns:
            Dictionary of signature headers
        """
        request_id = str(uuid.uuid4())
        timestamp = int(time.time() * 1000)
        version = "v1"
        
        # Create message to sign: "v1,{request_id},{timestamp},{payload}"
        message = f"{version},{request_id},{timestamp},{payload}"
        message_bytes = message.encode("utf-8")
        
        # Sign with Ed25519
        signed = self._signing_key.sign(message_bytes, encoder=RawEncoder)
        signature = base64.b64encode(signed.signature).decode("utf-8")
        
        return {
            "x-request-sign-version": version,
            "x-request-id": request_id,
            "x-request-timestamp": str(timestamp),
            "x-request-signature": signature,
        }
    
    def get_auth_headers(self, payload: str = "") -> dict:
        """Get all headers needed for authenticated requests."""
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._token}",
        }
        if payload:
            headers.update(self.sign_request(payload))
        return headers
    
    async def _prepare_sign_in(self, client: httpx.AsyncClient, chain: str, address: str) -> str:
        """Request signature data from server."""
        url = f"{self.BASE_URL}/v1/offchain/prepare-signin?chain={chain}"
        response = await client.post(
            url,
            json={"address": address, "requestId": self._request_id},
        )
        response.raise_for_status()
        data = response.json()
        
        if not data.get("success"):
            raise RuntimeError(f"Failed to prepare sign-in: {data}")
        
        return data["signedData"]
    
    async def _login(self, client: httpx.AsyncClient, chain: str, signature: str, signed_data: str) -> dict:
        """Login with signature to get access token."""
        url = f"{self.BASE_URL}/v1/offchain/login?chain={chain}"
        response = await client.post(
            url,
            json={
                "signature": signature,
                "signedData": signed_data,
                "expiresSeconds": 604800,  # 7 days
            },
        )
        response.raise_for_status()
        return response.json()
    
    def _get_wallet_address(self, chain: str, private_key: str) -> str:
        """Get wallet address from private key."""
        if chain == "bsc":
            account = Account.from_key(private_key)
            return account.address
        else:
            raise NotImplementedError(f"Chain {chain} not implemented")
    
    def _sign_message(self, chain: str, private_key: str, message: str) -> str:
        """Sign a message with wallet."""
        if chain == "bsc":
            account = Account.from_key(private_key)
            message_encoded = encode_defunct(text=message)
            signed = account.sign_message(message_encoded)
            return "0x" + signed.signature.hex()
        else:
            raise NotImplementedError(f"Chain {chain} not implemented")
    
    @staticmethod
    def _parse_jwt(token: str) -> dict:
        """Parse JWT payload without verification."""
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid JWT format")
        
        payload_b64 = parts[1]
        # Add padding if needed
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding
        
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        return json.loads(payload_bytes)
    
    @staticmethod
    def _base58_encode(data: bytes) -> str:
        """Base58 encode bytes."""
        alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        
        # Count leading zeros
        n_pad = 0
        for b in data:
            if b == 0:
                n_pad += 1
            else:
                break
        
        # Convert to integer
        n = int.from_bytes(data, "big")
        
        # Convert to base58
        result = ""
        while n > 0:
            n, r = divmod(n, 58)
            result = alphabet[r] + result
        
        return "1" * n_pad + result
    
    @staticmethod
    def _base58_decode(encoded: str) -> bytes:
        """Base58 decode string to bytes."""
        alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        
        # Count leading '1's
        n_pad = 0
        for c in encoded:
            if c == "1":
                n_pad += 1
            else:
                break
        
        # Convert from base58 to integer
        n = 0
        for c in encoded:
            n = n * 58 + alphabet.index(c)
        
        # Convert to bytes
        if n == 0:
            result = b"\x00"
        else:
            result = n.to_bytes((n.bit_length() + 7) // 8, "big")
        
        return b"\x00" * n_pad + result