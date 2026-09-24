import asyncio
import os
from datetime import date, datetime, timedelta, timezone
from typing import List

import httpx

from .asset_registry import get_asset
from .data_types import Bar
from .historical_store import HistoricalStore

MASSIVE_BASE = "https://api.massive.com"
BAR_SIZE = timedelta(minutes=1)


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
    Historical 1-minute aggregates.

    V13 time-integrity rule:
    `timestamp_utc` is the aggregate window START.
    A completed 1-minute OHLC bar is not available at that instant, so for
    historical replay its earliest availability is modeled as start + 1 minute.

    This is deliberately conservative and prevents a replay snapshot at 14:00
    from seeing the completed 14:00-14:00:59 OHLC bar.

    A future live/delayed collector must store the provider's real receive time
    instead of this historical replay approximation.
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

    rows = (response.json().get("results") or [])
    bars: List[Bar] = []

    for row in rows:
        if "t" not in row:
            continue
        bar_start = _utc_from_ms(int(row["t"]))
        bars.append(
            Bar(
                asset_id=asset.asset_id,
                timestamp_utc=bar_start,
                open=float(row["o"]),
                high=float(row["h"]),
                low=float(row["l"]),
                close=float(row["c"]),
                volume=float(row.get("v", 0.0)),
                source="massive",
                received_at_utc=bar_start + BAR_SIZE,
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
    async def _demo():
        day = date.today()
        bars = await fetch_minute_bars("AAPL", day, day)
        print({
            "asset": "AAPL",
            "rows": len(bars),
            "first_bar_start_utc": bars[0].timestamp_utc.isoformat() if bars else None,
            "first_available_utc": bars[0].received_at_utc.isoformat() if bars else None,
        })

    asyncio.run(_demo())
