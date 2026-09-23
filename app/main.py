import asyncio
import httpx

from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import (
    TICKERS,
    MASSIVE_STOCK_TICKERS,
    MASSIVE_API_KEY,
    MASSIVE_BASE,
    get_asset_name,
)


# =========================
# SCAN STORAGE
# =========================

scan_cache = {}
scan_position = 0
scan_running = False
last_scan_time = None


# =========================
# SCAN ONE STOCK
# =========================

async def scan_one_stock():
    global scan_position
    global last_scan_time

    symbols = MASSIVE_STOCK_TICKERS

    if not symbols:
        return None

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
                    "apiKey": MASSIVE_API_KEY
                }
            )

        if response.status_code != 200:
            return {
                "ok": False,
                "symbol": symbol,
                "status": response.status_code
            }

        rows = response.json().get(
            "results",
            []
        )

        if not rows:
            return {
                "ok": False,
                "symbol": symbol,
                "message": "אין נתונים"
            }

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

        change_percent = 0.0
        range_percent = 0.0

        if open_price > 0:

            change_percent = (
                (close_price / open_price) - 1
            ) * 100

            range_percent = (
                (high_price - low_price)
                / open_price
            ) * 100

        # ציון סינון ראשוני בלבד
        score = (
            abs(change_percent) * 0.60
            + range_percent * 0.40
        )

        scan_cache[symbol] = {
            "symbol": symbol,
            "name": get_asset_name(symbol),
            "category": "מניה",
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
            )
        }

        last_scan_time = (
            datetime.now(timezone.utc)
            .isoformat()
        )

        return {
            "ok": True,
            "symbol": symbol
        }

    except Exception as e:

        return {
            "ok": False,
            "symbol": symbol,
            "error": str(e)
        }


# =========================
# AUTOMATIC LOOP
# =========================

async def automatic_scanner():
    global scan_running

    scan_running = True

    while True:

        await scan_one_stock()

        # קריאה אחת כל 15 שניות
        await asyncio.sleep(15)


# =========================
# APP STARTUP
# =========================

@asynccontextmanager
async def lifespan(app: FastAPI):

    scanner_task = asyncio.create_task(
        automatic_scanner()
    )

    yield

    scanner_task.cancel()

    try:
        await scanner_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="Trading Forecast",
    version="9.0",
    lifespan=lifespan
)


app.mount(
    "/static",
    StaticFiles(
        directory="app/static"
    ),
    name="static"
)


# =========================
# HOME
# =========================

@app.get("/")
async def home():
    return FileResponse(
        "app/static/index.html"
    )


@app.head("/")
async def home_head():
    return {}


@app.get("/sw.js")
async def service_worker():
    return FileResponse(
        "app/static/sw.js",
        media_type="application/javascript"
    )


# =========================
# HEALTH
# =========================

@app.get("/health")
async def health():

    return {
        "ok": True,
        "version": "9.0",
        "universe": len(TICKERS),
        "stocks_connected": len(
            MASSIVE_STOCK_TICKERS
        ),
        "scanner_running": scan_running,
        "scanned_so_far": len(
            scan_cache
        ),
        "last_scan_time": last_scan_time
    }


# =========================
# MANUAL SCAN
# =========================

@app.get("/api/scan")
async def manual_scan():

    result = await scan_one_stock()

    return {
        "ok": True,
        "result": result,
        "scanned_so_far": len(
            scan_cache
        )
    }


# =========================
# LEADER
# =========================

@app.get("/api/leader")
async def current_leader():

    if not scan_cache:

        return {
            "ok": True,
            "leader": None,
            "scanned_so_far": 0,
            "stocks_connected": len(
                MASSIVE_STOCK_TICKERS
            )
        }

    ranking = sorted(
        scan_cache.values(),
        key=lambda item: item["score"],
        reverse=True
    )

    return {
        "ok": True,
        "leader": ranking[0],
        "scanned_so_far": len(
            scan_cache
        ),
        "stocks_connected": len(
            MASSIVE_STOCK_TICKERS
        ),
        "last_scan_time": last_scan_time
    }


# =========================
# FULL RANKING
# =========================

@app.get("/api/ranking")
async def current_ranking():

    ranking = sorted(
        scan_cache.values(),
        key=lambda item: item["score"],
        reverse=True
    )

    return {
        "ok": True,
        "count": len(ranking),
        "ranking": ranking
    }
