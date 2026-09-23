import os
from dotenv import load_dotenv
load_dotenv()
MASSIVE_API_KEY=os.getenv("MASSIVE_API_KEY","")
MASSIVE_BASE="https://api.massive.com"
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import TICKERS

app = FastAPI()

app.mount("/static", StaticFiles(directory="app/static"), name="static")

# כאן יישמרו בהמשך התחזיות של כל הנכסים
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
