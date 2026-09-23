from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import asyncio
from .config import TICKERS
from .data import minute_history
from .engine import forecast
app=FastAPI()
app.mount("/static",StaticFiles(directory="app/static"),name="static")
@app.get("/")
async def home(): return FileResponse("app/static/index.html")
@app.get("/sw.js")
async def sw(): return FileResponse("app/static/sw.js",media_type="application/javascript")
@app.get("/api/hottest")
async def hottest():
    async def one(t):
        try:return forecast(t,await minute_history(t))
        except Exception as e:return {"ticker":t,"error":str(e),"potential":-1}
    rows=await asyncio.gather(*[one(t) for t in TICKERS]); rows.sort(key=lambda x:x.get("potential",-1),reverse=True)
    return {"leader":rows[0],"ranking":rows}
@app.get("/health")
async def health(): return {"ok":True}
