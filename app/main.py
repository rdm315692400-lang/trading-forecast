import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI

from .config import (
    TICKERS,
    MASSIVE_STOCK_TICKERS,
    MASSIVE_API_KEY,
    MASSIVE_BASE,
    get_asset_name,
)

from .data import minute_history
from .engine import forecast


# ==========================================
# STORAGE
# ==========================================

scan_cache = {}
scan_position = 0
scanner_running = False
last_scan_time = None


# ==========================================
# EXISTING STABLE SCANNER
# ==========================================

async def scan_one_stock():
    global scan_position
    global last_scan_time

    symbols = MASSIVE_STOCK_TICKERS

    if not symbols:
        return

    symbol = symbols[
        scan_position % len(symbols)
    ]

    scan_position += 1

    url = (
        f"{MASSIVE_BASE}/v2/aggs/"
        f"ticker/{symbol}/prev"
    )

    try:
        async with httpx.AsyncClient(
            timeout=20
        ) as client:
            response = await client.get(
                url,
                params={
                    "adjusted": "true",
                    "apiKey": MASSIVE_API_KEY,
                },
            )

        if response.status_code != 200:
            return

        rows = response.json().get(
            "results",
            []
        )

        if not rows:
            return

        row = rows[0]

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

        volume = float(
            row.get("v") or 0
        )

        if open_price <= 0:
            return

        change_percent = (
            (close_price / open_price) - 1
        ) * 100

        range_percent = (
            (high_price - low_price)
            / open_price
        ) * 100

        # הציון הזה נשאר זמנית
        # רק כדי שהסריקה הקיימת תמשיך לעבוד.
        score = (
            abs(change_percent) * 0.60
            + range_percent * 0.40
        )

        scan_cache[symbol] = {
            "symbol": symbol,
            "name": get_asset_name(symbol),
            "price": round(
                close_price,
                3
            ),
            "change_percent": round(
                change_percent,
                2
            ),
            "range_percent": round(
                range_percent,
                2
            ),
            "volume": volume,
            "score": round(
                score,
                2
            ),
        }

        last_scan_time = (
            datetime.now(
                timezone.utc
            ).isoformat()
        )

    except Exception:
        return


# ==========================================
# AUTOMATIC SCANNER
# ==========================================

async def automatic_scanner():
    global scanner_running

    scanner_running = True

    while True:
        await scan_one_stock()
        await asyncio.sleep(15)


# ==========================================
# LIFESPAN
# ==========================================

@asynccontextmanager
async def lifespan(app: FastAPI):

    task = asyncio.create_task(
        automatic_scanner()
    )

    yield

    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass


# ==========================================
# APP
# ==========================================

app = FastAPI(
    title="Trading Forecast",
    version="10.1",
    lifespan=lifespan,
)


# ==========================================
# ROOT
# ==========================================

@app.get("/")
async def root():

    return {
        "ok": True,
        "name": "Trading Forecast",
        "version": "10.1",
    }


# ==========================================
# HEALTH
# ==========================================

@app.get("/health")
async def health():

    return {
        "ok": True,
        "version": "10.1",
        "universe": len(TICKERS),
        "stocks_connected": len(
            MASSIVE_STOCK_TICKERS
        ),
        "scanner_running": scanner_running,
        "scanned_so_far": len(
            scan_cache
        ),
        "last_scan_time": last_scan_time,
    }


# ==========================================
# OLD LEADER
# TEMPORARY INFRASTRUCTURE CHECK
# ==========================================

@app.get("/api/leader")
async def leader():

    if not scan_cache:
        return {
            "ok": True,
            "leader": None,
            "scanned_so_far": 0,
        }

    ranking = sorted(
        scan_cache.values(),
        key=lambda item: item["score"],
        reverse=True,
    )

    return {
        "ok": True,
        "leader": ranking[0],
        "scanned_so_far": len(
            scan_cache
        ),
        "note": (
            "זהו דירוג הסריקה הישן בלבד, "
            "לא תחזית המסחר החדשה"
        ),
    }


# ==========================================
# FORECAST TEST
# ==========================================

@app.get("/api/forecast/{symbol}")
async def forecast_symbol(symbol: str):

    symbol = symbol.upper().strip()

    if symbol not in MASSIVE_STOCK_TICKERS:
        return {
            "ok": False,
            "message": "המניה אינה ברשימת המניות",
            "symbol": symbol,
        }

    try:
        rows = await minute_history(
            symbol,
            days=10
        )

        if not rows:
            return {
                "ok": False,
                "symbol": symbol,
                "message": "לא התקבלו נתוני דקות",
            }

        result = forecast(
            symbol,
            rows
        )

        return {
            "ok": True,
            "name": get_asset_name(symbol),
            "symbol": symbol,
            "forecast": result,
        }

    except Exception as e:
        return {
            "ok": False,
            "symbol": symbol,
            "name": get_asset_name(symbol),
            "error": str(e),
        }
