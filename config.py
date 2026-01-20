"""Configuration loader for StandX Maker Bot."""
import yaml
from pathlib import Path
from dataclasses import dataclass


@dataclass
class WalletConfig:
    chain: str
    private_key: str = None
    api_token: str = None
    api_secret: str = None


@dataclass
class Config:
    wallet: WalletConfig
    symbol: str
    order_distance_bps: int
    cancel_distance_bps: int
    rebalance_distance_bps: int
    order_size_btc: float
    max_position_btc: float
    volatility_window_sec: int
    volatility_threshold_bps: int
    
    @classmethod
    def from_dict(cls, data: dict) -> "Config":
        wallet_data = data["wallet"]
        # Allow api_token to be set if private_key is missing
        if "api_token" not in wallet_data and "private_key" not in wallet_data:
             raise ValueError("Either private_key or api_token must be provided in wallet config")
             
        return cls(
            wallet=WalletConfig(
                chain=wallet_data.get("chain", "bsc"),
                private_key=wallet_data.get("private_key"),
                api_token=wallet_data.get("api_token"),
                api_secret=wallet_data.get("api_secret")
            ),
            symbol=data["symbol"],
            order_distance_bps=data["order_distance_bps"],
            cancel_distance_bps=data["cancel_distance_bps"],
            rebalance_distance_bps=data.get("rebalance_distance_bps", 20),
            order_size_btc=data["order_size_btc"],
            max_position_btc=data["max_position_btc"],
            volatility_window_sec=data["volatility_window_sec"],
            volatility_threshold_bps=data["volatility_threshold_bps"],
        )


def load_config(path: str = "config.yaml") -> Config:
    """Load configuration from YAML file."""
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    return Config.from_dict(data)
