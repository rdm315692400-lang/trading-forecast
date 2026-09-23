import httpx

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


app = FastAPI(
    title="Trading Forecast",
    version="8.0"
)

app.mount(
    "/static",
    StaticFiles(directory="app/static"),
    name="static"
)


# =========================
# CACHE
# =========================

scan_cache = {}
scan_position = 0


# =========================
# HOME
# =========================

@app.get("/")
async def home():
    return FileResponse("app/static/index.html")


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
        "version": "8.0",
        "assets": len(TICKERS),
        "stocks_connected": len(MASSIVE_STOCK_TICKERS)
    }


# =========================
# SCAN ONE ASSET
# =========================

@app.get("/api/scan")
async def scan_next_asset():
    global scan_position

    symbols = MASSIVE_STOCK_TICKERS

    if not symbols:
        return {
            "ok": False,
            "message": "אין נכסים מחוברים לסריקה"
        }

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
                "name": get_asset_name(symbol),
                "status": response.status_code,
                "scanned_so_far": len(scan_cache)
            }

        data = response.json()

        rows = data.get(
            "results",
            []
        )

        if not rows:
            return {
                "ok": False,
                "symbol": symbol,
                "name": get_asset_name(symbol),
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
                (close_price / open_price)
                - 1
            ) * 100

            range_percent = (
                (high_price - low_price)
                / open_price
            ) * 100


        # ציון ראשוני בלבד לסינון.
        # בהמשך נחבר את מנוע התחזית המלא.
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


        ranking = sorted(
            scan_cache.values(),
            key=lambda item: item["score"],
            reverse=True
        )


        leader = (
            ranking[0]
            if ranking
            else None
        )


        return {
            "ok": True,

            # היקום המלא שהגדרנו
            "universe": len(TICKERS),

            # כרגע מקור הנתונים הפעיל
            # מחובר ל-45 המניות
            "connected_now": len(
                MASSIVE_STOCK_TICKERS
            ),

            "scanned_so_far": len(
                scan_cache
            ),

            "just_scanned": {
                "symbol": symbol,
                "name": get_asset_name(symbol)
            },

            "leader": leader
        }


    except Exception as e:

        return {
            "ok": False,
            "symbol": symbol,
            "name": get_asset_name(symbol),
            "error": str(e)
        }


# =========================
# CURRENT
