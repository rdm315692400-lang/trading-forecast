import os
from datetime import datetime, timedelta, timezone
import httpx
from .asset_registry import get_asset
from .data_types import Bar

class ProviderError(RuntimeError):
    pass

async def fetch_minute_bars(asset_id, start_date, end_date, api_key=None):
    asset = get_asset(asset_id)
    if not asset or not asset.provider_verified or not asset.provider_symbol:
        raise ProviderError(f"Provider mapping is not verified: {asset_id}")
    key = api_key or os.getenv("MASSIVE_API_KEY")
    if not key:
        raise ProviderError("MASSIVE_API_KEY is not configured")
    url = (
        f"https://api.massive.com/v2/aggs/ticker/{asset.provider_symbol}"
        f"/range/1/minute/{start_date.isoformat()}/{end_date.isoformat()}"
    )
    params = {"adjusted":"true", "sort":"asc", "limit":50000, "apiKey":key}
    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.get(url, params=params)
    if response.status_code != 200:
        raise ProviderError(
            f"Massive HTTP {response.status_code}: {response.text[:500]}"
        )
    bars = []
    for row in response.json().get("results") or []:
        if "t" not in row:
            continue
        start = datetime.fromtimestamp(int(row["t"]) / 1000, tz=timezone.utc)
        bars.append(Bar(
            asset_id=asset.asset_id,
            timestamp_utc=start,
            open=float(row["o"]), high=float(row["h"]),
            low=float(row["l"]), close=float(row["c"]),
            volume=float(row.get("v", 0.0)),
            source="massive",
            received_at_utc=start + timedelta(minutes=1),
        ))
    return bars
