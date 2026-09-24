from fastapi import FastAPI
from .config import TICKERS, MASSIVE_STOCK_TICKERS, get_asset_name
from .data import minute_history, daily_history
from .engine import forecast, opening_forecast

app = FastAPI(title="Trading Forecast", version="11.0")

@app.get("/health")
async def health():
    return {"ok":True,"version":"11.0","universe":len(TICKERS),"stocks_connected":len(MASSIVE_STOCK_TICKERS),"background_scanner":False}

@app.get("/api/forecast/{symbol}")
async def forecast_symbol(symbol:str):
    symbol=symbol.upper().strip()
    if symbol not in MASSIVE_STOCK_TICKERS:
        return {"ok":False,"symbol":symbol,"message":"המניה אינה מחוברת כרגע"}
    try:
        rows=await minute_history(symbol,10)
        return {"ok":True,"symbol":symbol,"name":get_asset_name(symbol),"data_rows":len(rows),"forecast":forecast(symbol,rows)}
    except Exception as e:
        return {"ok":False,"symbol":symbol,"error":str(e)}

@app.get("/api/opening/{symbol}")
async def opening(symbol:str):
    symbol=symbol.upper().strip()
    if symbol not in MASSIVE_STOCK_TICKERS:
        return {"ok":False,"symbol":symbol,"message":"המניה אינה מחוברת כרגע"}
    try:
        rows=await daily_history(symbol)
        return {"ok":True,"symbol":symbol,"name":get_asset_name(symbol),"daily_sessions":len(rows),"opening_model":opening_forecast(rows)}
    except Exception as e:
        return {"ok":False,"symbol":symbol,"error":str(e)}
