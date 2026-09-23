from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo

import httpx

from .config import (
    MASSIVE_API_KEY,
    MASSIVE_BASE,
)


# ==========================================
# SETTINGS
# ==========================================

NY_TIMEZONE = ZoneInfo("America/New_York")
UTC_TIMEZONE = ZoneInfo("UTC")


# ==========================================
# HTTP REQUEST
# ==========================================

async def massive_get(url, params=None):
    if params is None:
        params = {}

    params["apiKey"] = MASSIVE_API_KEY

    async with httpx.AsyncClient(
        timeout=30
    ) as client:

        response = await client.get(
            url,
            params=params,
        )

        response.raise_for_status()

        return response.json()


# ==========================================
# MINUTE HISTORY
# Used for intraday timing
# ==========================================

async def minute_history(
    ticker,
    days=10,
):
    end = date.today()
    start = end - timedelta(
        days=days
    )

    url = (
        f"{MASSIVE_BASE}/v2/aggs/"
        f"ticker/{ticker}/"
        f"range/1/minute/"
        f"{start}/{end}"
    )

    data = await massive_get(
        url,
        {
            "adjusted": "true",
            "sort": "asc",
            "limit": 50000,
        },
    )

    rows = data.get(
        "results",
        []
    )

    result = []

    for row in rows:

        timestamp = row.get("t")

        if timestamp is None:
            continue

        dt = datetime.fromtimestamp(
            timestamp / 1000,
            tz=UTC_TIMEZONE,
        ).astimezone(
            NY_TIMEZONE
        )

        result.append({
            "ts": timestamp,
            "dt": dt,
            "day": dt.date(),
            "minute":
                dt.hour * 60
                + dt.minute,
            "open": row.get("o"),
            "high": row.get("h"),
            "low": row.get("l"),
            "close": row.get("c"),
            "volume": row.get(
                "v",
                0,
            ),
            "vwap": row.get("vw"),
        })

    return result


# ==========================================
# DAILY HISTORY
# Used for long-term learning
# ==========================================

async def daily_history(
    ticker,
    calendar_days=420,
):
    """
    Pull enough calendar history to obtain
    roughly 250 trading sessions.
    """

    end = date.today()

    start = end - timedelta(
        days=calendar_days
    )

    url = (
        f"{MASSIVE_BASE}/v2/aggs/"
        f"ticker/{ticker}/"
        f"range/1/day/"
        f"{start}/{end}"
    )

    data = await massive_get(
        url,
        {
            "adjusted": "true",
            "sort": "asc",
            "limit": 50000,
        },
    )

    rows = data.get(
        "results",
        []
    )

    result = []

    for row in rows:

        timestamp = row.get("t")

        if timestamp is None:
            continue

        dt = datetime.fromtimestamp(
            timestamp / 1000,
            tz=UTC_TIMEZONE,
        ).astimezone(
            NY_TIMEZONE
        )

        open_price = float(
            row.get("o") or 0
        )

        high_price = float(
            row.get("h") or 0
        )

        low_price = float(
            row.get("l") or 0
        )

        close_price = float(
            row.get("c") or 0
        )

        if (
            open
