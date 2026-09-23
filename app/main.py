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


