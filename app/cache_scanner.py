import asyncio, time
from .config import MASSIVE_STOCK_TICKERS, get_asset_name
from .data import daily_history, minute_history
from .model_v12 import forecast_daily
from .timing_v12 import learn_timing
from .scanner import choose_leader
from .storage import save_asset, save_forecast_history, load_assets, enabled as firestore_enabled

CACHE={}
STATE={"running":False,"last_symbol":None,"last_error":None,"completed_cycle_at":None}
REQUEST_GAP_SECONDS=15

async def restore_cache():
    if not firestore_enabled(): return 0
    try:
        stored=await asyncio.to_thread(load_assets, MASSIVE_STOCK_TICKERS)
        CACHE.update(stored)
        return len(stored)
    except Exception as e:
        STATE["last_error"]=f"Firestore restore: {e}"
        return 0

async def update_one(symbol):
    daily=await daily_history(symbol)
    await asyncio.sleep(REQUEST_GAP_SECONDS)
    minute=await minute_history(symbol,10)
    f=forecast_daily(daily)
    timing=learn_timing(minute,f.get("כיוון"))
    item={"שם":get_asset_name(symbol),"סמל":symbol,"עודכן_ב":int(time.time()),
          "ימי_היסטוריה":len(daily),"תחזית":f,"זמנים":timing}
    CACHE[symbol]=item
    if firestore_enabled():
        try:
            await asyncio.to_thread(save_asset,item)
            await asyncio.to_thread(save_forecast_history,item)
        except Exception as e:
            STATE["last_error"]=f"{symbol} Firestore: {e}"
    STATE["last_symbol"]=symbol
    return item

async def refresh_cycle():
    if STATE["running"]: return
    STATE["running"]=True
    try:
        for symbol in MASSIVE_STOCK_TICKERS:
            try: await update_one(symbol)
            except Exception as e: STATE["last_error"]=f"{symbol}: {e}"
            await asyncio.sleep(REQUEST_GAP_SECONDS)
        STATE["completed_cycle_at"]=int(time.time())
    finally:
        STATE["running"]=False

def summaries():
    return [CACHE[s] for s in MASSIVE_STOCK_TICKERS if s in CACHE]

def leader():
    return choose_leader(summaries())

def status():
    return {"רץ":STATE["running"],"עודכנו":len(CACHE),"מתוך":len(MASSIVE_STOCK_TICKERS),
            "נכס_אחרון":STATE["last_symbol"],"שגיאה_אחרונה":STATE["last_error"],
            "מחזור_אחרון_הושלם":STATE["completed_cycle_at"],
            "Firestore_מוגדר":firestore_enabled()}
