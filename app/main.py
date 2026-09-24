import asyncio
from fastapi import FastAPI
from fastapi.responses import FileResponse
from .config import TICKERS, MASSIVE_STOCK_TICKERS, get_asset_name
from .data import daily_history, minute_history
from .model_v12 import forecast_daily
from .timing_v12 import learn_timing
from .walk_forward import run_walk_forward
from .future_move_v12 import learn_future_xv, walk_forward_future_xv
from .cache_scanner import refresh_cycle, restore_cache, summaries, leader, status

app=FastAPI(title="Trading Forecast",version="12.5")

@app.on_event("startup")
async def startup():
    await restore_cache()
    asyncio.create_task(refresh_cycle())

@app.get("/")
async def root():
    return FileResponse("app/static/index.html")

@app.get("/health")
async def health():
    return {"ok":True,"version":"12.5","נכסים_ביקום":len(TICKERS),
            "מניות_מחוברות":len(MASSIVE_STOCK_TICKERS),
            "מדדים_וסחורות_ממתינים_לחיבור":20,"שפה":"עברית","סריקה":status(),
            "שלב":"חיזוי תנועה עתידית X→V"}

@app.get("/api/v12/{symbol}")
async def asset_forecast(symbol:str):
    symbol=symbol.upper().strip()
    if symbol not in MASSIVE_STOCK_TICKERS:
        return {"ok":False,"סמל":symbol,"הודעה":"הנכס עדיין אינו מחובר למקור נתונים מאומת"}
    try:
        daily=await daily_history(symbol)
        minute=await minute_history(symbol,10)
        f=forecast_daily(daily)
        direction=f.get("כיוון")
        return {"ok":True,"שם":get_asset_name(symbol),"סמל":symbol,
                "ימי_היסטוריה":len(daily),"תחזית":f,
                "זמנים":learn_timing(minute,direction),
                "חיזוי_XV":learn_future_xv(minute,direction)}
    except Exception as e:
        return {"ok":False,"סמל":symbol,"שגיאה":str(e)}

@app.get("/api/walk-forward/{symbol}")
async def walk_forward(symbol:str):
    symbol=symbol.upper().strip()
    if symbol not in MASSIVE_STOCK_TICKERS:
        return {"ok":False,"סמל":symbol,"הודעה":"הנכס עדיין אינו מחובר למקור נתונים מאומת"}
    try:
        daily=await daily_history(symbol)
        return {"ok":True,"שם":get_asset_name(symbol),"סמל":symbol,
                "ימי_היסטוריה":len(daily),"walk_forward":run_walk_forward(daily)}
    except Exception as e:
        return {"ok":False,"סמל":symbol,"שגיאה":str(e)}

@app.get("/api/future-xv/{symbol}")
async def future_xv(symbol:str):
    symbol=symbol.upper().strip()
    if symbol not in MASSIVE_STOCK_TICKERS:
        return {"ok":False,"סמל":symbol,"הודעה":"הנכס עדיין אינו מחובר למקור נתונים מאומת"}
    try:
        daily=await daily_history(symbol)
        minute=await minute_history(symbol,10)
        f=forecast_daily(daily)
        direction=f.get("כיוון")
        return {"ok":True,"שם":get_asset_name(symbol),"סמל":symbol,
                "כיוון_יומי":direction,
                "חיזוי_XV":learn_future_xv(minute,direction),
                "walk_forward_XV":walk_forward_future_xv(minute,direction)}
    except Exception as e:
        return {"ok":False,"סמל":symbol,"שגיאה":str(e)}

@app.get("/api/scan/status")
async def scan_status():
    return {"ok":True,"סריקה":status()}

@app.get("/api/scan/summaries")
async def scan_summaries():
    d=summaries()
    return {"ok":True,"עודכנו":len(d),"סיכומים":d}

@app.get("/api/scan/leader")
async def scan_leader():
    best=leader()
    return {"ok":True,"עודכנו":len(summaries()),"מועמד_מוביל":best,
            "הודעה":None if best else "אין כרגע מועמד שעובר את תנאי הסינון"}

@app.post("/api/scan/start")
async def scan_start():
    if not status()["רץ"]:
        asyncio.create_task(refresh_cycle())
    return {"ok":True,"סריקה":status()}

@app.get("/api/universe")
async def universe():
    return {"סהכ":len(TICKERS),"מחוברים":len(MASSIVE_STOCK_TICKERS),
            "נכסים":[{"סמל":s,"שם":get_asset_name(s),"מחובר":s in MASSIVE_STOCK_TICKERS} for s in TICKERS]}
