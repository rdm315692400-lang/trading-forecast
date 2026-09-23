from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
import httpx

from .config import MASSIVE_API_KEY, MASSIVE_BASE


async def minute_history(ticker, days=10):
    end = date.today()
    start = end - timedelta(days=days)

    url = (
        f"{MASSIVE_BASE}/v2/aggs/ticker/{ticker}/"
        f"range/1/minute/{start}/{end}"
    )

    params = {
        "adjusted": "true",
        "sort": "asc",
        "limit": 50000,
        "apiKey": MASSIVE_API_KEY
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        rows = response.json().get("results", [])

    ny = ZoneInfo("America/New_York")
    result = []

    for row in rows:
        timestamp = row.get("t")

        if timestamp is None:
            continue

        dt = datetime.fromtimestamp(
            timestamp / 1000,
            tz=ZoneInfo("UTC")
        ).astimezone(ny)

        result.append({
            "ts": timestamp,
            "dt": dt,
            "day": dt.date(),
            "minute": dt.hour * 60 + dt.minute,
            "open": row.get("o"),
            "high": row.get("h"),
            "low": row.get("l"),
            "close": row.get("c"),
            "volume": row.get("v", 0),
            "vwap": row.get("vw")
        })

    return result
