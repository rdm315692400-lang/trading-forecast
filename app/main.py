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
@app.get("/api/scan")
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

