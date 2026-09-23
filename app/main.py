from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import TICKERS
from .data import minute_history
from .engine import forecast

app = FastAPI()

app.mount("/static", StaticFiles(directory="app/static"), name="static")


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
    return {"ok": True}


@app.get("/api/hottest")
async def hottest():
    rows = []

    # בודקים כל מניה בנפרד כדי לא להעמיס על השרת
    for ticker in TICKERS:
        try:
            data = await minute_history(ticker, days=10)
            result = forecast(ticker, data)
            rows.append(result)

        except Exception as e:
            rows.append({
                "ticker": ticker,
                "error": str(e),
                "potential": -1
            })

    rows.sort(
        key=lambda x: x.get("potential", -1),
        reverse=True
    )

    valid = [
        row for row in rows
        if row.get("potential", -1) >= 0
    ]

    return {
        "leader": valid[0] if valid else None,
        "ranking": rows
    }
