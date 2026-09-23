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


@app.get("/api/scan-stocks")
async def scan_stocks():
    # בשלב הראשון בודקים רק 5 מניות כדי להישאר
    # בתוך מגבלת הבקשות של Massive
    symbols = MASSIVE_STOCK_TICKERS[:5]

    results = []

    async with httpx.AsyncClient(timeout=20) as client:
        for symbol in symbols:
            try:
                url = (
                    f"{MASSIVE_BASE}/v2/aggs/ticker/"
                    f"{symbol}/prev"
                )

                response = await client.get(
                    url,
                    params={
                        "adjusted": "true",
                        "apiKey": MASSIVE_API_KEY
                    }
                )

                if response.status_code != 200:
                    results.append({
                        "symbol": symbol,
                        "name": get_asset_name(symbol),
                        "status": response.status_code
                    })
                    continue

                data = response.json()
                rows = data.get("results", [])

                if not rows:
                    continue

                row = rows[0]

                open_price = float(row.get("o", 0))
                close_price = float(row.get("c", 0))

                change = 0

                if open_price:
                    change = (
                        (close_price / open_price) - 1
                    ) * 100

                results.append({
                    "symbol": symbol,
                    "name": get_asset_name(symbol),
                    "price": close_price,
                    "change_percent": round(change, 2)
                })

            except Exception as e:
                results.append({
                    "symbol": symbol,
                    "name": get_asset_name(symbol),
                    "error": str(e)
                })

    results.sort(
        key=lambda x: abs(x.get("change_percent", 0)),
        reverse=True
    )

    return {
        "scanned": len(symbols),
        "results": results
    }
