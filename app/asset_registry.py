from dataclasses import dataclass, asdict
from typing import Dict, Optional

@dataclass(frozen=True)
class AssetProfile:
    asset_id: str
    name_he: str
    symbol: str
    asset_type: str
    market_timezone: str
    session_open: str
    session_close: str
    provider: str = "massive"
    verified: bool = True

    def to_dict(self):
        return asdict(self)

# V13.0 starts only with already-connected US stocks.
# The registry is intentionally small until every additional feed is verified.
ASSETS: Dict[str, AssetProfile] = {
    "AAPL": AssetProfile("AAPL", "אפל", "AAPL", "stock", "America/New_York", "09:30", "16:00"),
    "NVDA": AssetProfile("NVDA", "אנבידיה", "NVDA", "stock", "America/New_York", "09:30", "16:00"),
    "MSFT": AssetProfile("MSFT", "מיקרוסופט", "MSFT", "stock", "America/New_York", "09:30", "16:00"),
    "KO": AssetProfile("KO", "קוקה קולה", "KO", "stock", "America/New_York", "09:30", "16:00"),
}

def get_asset(asset_id: str) -> Optional[AssetProfile]:
    return ASSETS.get(asset_id.upper())

def verified_assets():
    return [a for a in ASSETS.values() if a.verified]
