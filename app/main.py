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

app = FastAPI()

app.mount("/static", StaticFiles(directory="app/static"), name="static")

forecast_cache = {}


@app.get("/")
async def home():
    return FileResponse("app/static/index.html")


@app.head("/")
async def home_head():
    return {}


@app.get("/sw.js")
async def sw():
    return FileResponse(
        "app/static/sw.js",
        media_type="application/javascript"
    )


@app.get("/health")
async def health():
    return {
        "ok": True,
        "assets": len(TICKERS)
    }

async def scan_all_assets():
    """
    סורק מאוחד:
    45 מניות + 10 מדדים + 10 סחורות.
    בסוף מוחזר מועמד מוביל אחד.
    """

    candidates = []

    # כרגע סריקת המניות בלבד מחוברת ל-Massive.
    # המדדים והסחורות יחוברו למקורות הנתונים
    # המתאימים בלי לשנות את מבנה הסורק.
    symbols = MASSIVE_STOCK_TICKERS

    url = (
        f"{MASSIVE_BASE}/v2/snapshot/locale/us/"
        f"markets/stocks/tickers"
    )

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                url,
                params={
                    "tickers": ",".join(symbols),
                    "include_otc": "false",
                    "apiKey": MASSIVE_API_KEY
                }
            )

        if response.status_code != 200:
            return {
                "ok": False,
                "status": response.status_code,
                "message": "שגיאה בקבלת נתוני הסריקה"
            }

        data = response.json()

        for item in data.get("tickers", []):
            symbol = item.get("ticker")

            day = item.get("day") or {}

            price = float(day.get("c") or 0)
            volume = float(day.get("v") or 0)
            change = float(
                item.get("todaysChangePerc") or 0
            )

            # ציון ראשוני בלבד.
            # בהמשך יוחלף במודל המלא.
            score = abs(change)

            candidates.append({
                "symbol": symbol,
                "name": get_asset_name(symbol),
                "category": "מניה",
                "price": price,
                "change_percent": round(change, 2),
                "volume": volume,
                "score": round(score, 2)
            })

        candidates.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        leader = (
            candidates[0]
            if candidates
            else None
        )

        return {
            "ok": True,

            # היעד הקבוע של המערכת
            "universe": 65,

            # כמה נכסים מחוברים כרגע בפועל
            "currently_scanned": len(candidates),

            # בסוף תמיד מועמד אחד
            "leader": leader,

            # נשאיר את הדירוג לצורך עבודת המנוע
            "ranking": candidates
        }

    except Exception as e:
        return {
            "ok": False,
            "error": str(e)
        }

scan_cache = {}
scan_position = 0


@app.get("/api/scan")
async def scan_next_asset():
    global scan_position

    # בשלב הראשון: 45 המניות שיש להן מקור נתונים פעיל
    symbols = MASSIVE_STOCK_TICKERS

    if not symbols:
        return {
            "ok": False,
            "message": "אין נכסים לסריקה"
        }

    symbol = symbols[scan_position % len(symbols)]
    scan_position += 1

    url = f"{MASSIVE_BASE}/v2/aggs/ticker/{symbol}/prev"

    try:
        async with httpx.AsyncClient(timeout=20) as client:
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
                "status": response.status_code,
                "cached": len(scan_cache)
            }

        data = response.json()
        rows = data.get("results", [])

        if not rows:
            return {
                "ok": False,
                "symbol": symbol,
                "message": "אין נתונים"
            }

        row = rows[0]

        open_price = float(row.get("o") or 0)
        close_price = float(row.get("c") or 0)
        high_price = float(row.get("h") or 0)
        low_price = float(row.get("l") or 0)
        volume = float(row.get("v") or 0)

        change = 0.0
        range_percent = 0.0

        if open_price > 0:
            change = (
                (close_price / open_price) - 1
            ) * 100

            range_percent = (
                (high_price - low_price) / open_price
            ) * 100

        # ציון ראשוני לסינון בלבד
        score = (
            abs(change) * 0.60
            + range_percent * 0.40
        )

        scan_cache[symbol] = {
            "symbol": symbol,
            "name": get_asset_name(symbol),
            "category": "מניה",
            "price": round(close_price, 3),
            "change_percent": round(change, 2),
            "range_percent": round(range_percent, 2),
            "volume": volume,
            "score": round(score, 2)
        }

        ranking = sorted(
            scan_cache.values(),
            key=lambda x: x["score"],
            reverse=True
        )

        return {
            "ok": True,
            "universe": 65,
            "connected_now": 45,
            "scanned_so_far": len(scan_cache),
            "just_scanned": get_asset_name(symbol),
            "leader": ranking[0] if ranking else None
        }

    except Exception as e:
        return {
            "ok": False,
            "symbol": symbol,
            "error": str(e)
    }
