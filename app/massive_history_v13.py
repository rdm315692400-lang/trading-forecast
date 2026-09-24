import asyncio
import os
from datetime import date, datetime, timezone
from typing import List

import httpx

from .asset_registry import get_asset
from .data_types import Bar
from .historical_store import HistoricalStore

MASSIVE_BASE = "https://api.massive.com"


class MassiveHistoryError(RuntimeError):
    pass


def _utc_from_ms(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, tz=timezone.utc)


async def fetch_minute_bars(
    asset_id: str,
    start_date: date,
    end_date: date,
    api_key: str | None = None,
) -> List[Bar]:
    """
    Download historical 1-minute bars for one verified V13 asset.

    Important V13 rule:
    Historical provider data is raw research data. `received_at_utc` is set to
    the bar timestamp for this historical-price feed only. News/events and
    delayed/live feeds will keep their own true availability timestamps.
    """
    asset = get_asset(asset_id)
    if asset is None or not asset.verified:
        raise MassiveHistoryError(f"Asset is not verified in V13 registry: {asset_id}")

    key = api_key or os.getenv("MASSIVE_API_KEY")
    if not key:
        raise MassiveHistoryError("MASSIVE_API_KEY is not configured")

    url = (
        f"{MASSIVE_BASE}/v2/aggs/ticker/{asset.symbol}/range/1/minute/"
        f"{start_date.isoformat()}/{end_date.isoformat()}"
    )
    params = {
        "adjusted": "true",
        "sort": "asc",
        "limit": 50000,
        "apiKey": key,
    }

    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.get(url, params=params)

    if response.status_code != 200:
        raise MassiveHistoryError(
            f"Massive returned HTTP {response.status_code}: {response.text[:300]}"
        )

    payload = response.json()
    rows = payload.get("results") or []
    bars: List[Bar] = []

    for row in rows:
        if "t" not in row:
            continue
        ts = _utc_from_ms(int(row["t"]))
        bars.append(
            Bar(
                asset_id=asset.asset_id,
                timestamp_utc=ts,
                open=float(row["o"]),
                high=float(row["h"]),
                low=float(row["l"]),
                close=float(row["c"]),
                volume=float(row.get("v", 0.0)),
                source="massive",
                received_at_utc=ts,
            )
        )

    return bars


async def load_into_store(
    store: HistoricalStore,
    asset_id: str,
    start_date: date,
    end_date: date,
    api_key: str | None = None,
) -> int:
    bars = await fetch_minute_bars(asset_id, start_date, end_date, api_key)
    store.extend(bars)
    return len(bars)


if __name__ == "__main__":
    # Local smoke test. Never prints the API key.
    async def _demo():
        end = date.today()
        start = end
        bars = await fetch_minute_bars("AAPL", start, end)
        print({
            "asset": "AAPL",
            "rows": len(bars),
            "first_utc": bars[0].timestamp_utc.isoformat() if bars else None,
            "last_utc": bars[-1].timestamp_utc.isoformat() if bars else None,
        })

    asyncio.run(_demo())
