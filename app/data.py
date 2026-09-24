from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
import httpx
from .config import MASSIVE_API_KEY, MASSIVE_BASE

UTC = ZoneInfo("UTC")
NY = ZoneInfo("America/New_York")

async def _get(url, params):
    p = dict(params)
    p["apiKey"] = MASSIVE_API_KEY
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, params=p)
        r.raise_for_status()
        return r.json()

async def minute_history(ticker, days=10):
    end = date.today()
    start = end - timedelta(days=days)
    url = f"{MASSIVE_BASE}/v2/aggs/ticker/{ticker}/range/1/minute/{start}/{end}"
    data = await _get(url, {"adjusted":"true","sort":"asc","limit":50000})
    out=[]
    for x in data.get("results",[]):
        ts=x.get("t")
        if ts is None: continue
        dt=datetime.fromtimestamp(ts/1000,tz=UTC).astimezone(NY)
        out.append({"ts":ts,"dt":dt,"day":dt.date(),"minute":dt.hour*60+dt.minute,
                    "open":x.get("o"),"high":x.get("h"),"low":x.get("l"),"close":x.get("c"),
                    "volume":x.get("v",0),"vwap":x.get("vw")})
    return out

async def daily_history(ticker, calendar_days=420):
    end=date.today()
    start=end-timedelta(days=calendar_days)
    url=f"{MASSIVE_BASE}/v2/aggs/ticker/{ticker}/range/1/day/{start}/{end}"
    data=await _get(url,{"adjusted":"true","sort":"asc","limit":50000})
    out=[]
    for x in data.get("results",[]):
        ts=x.get("t")
        if ts is None: continue
        dt=datetime.fromtimestamp(ts/1000,tz=UTC).astimezone(NY)
        o,h,l,c=[float(x.get(k) or 0) for k in ("o","h","l","c")]
        if min(o,h,l,c)<=0: continue
        out.append({"ts":ts,"date":dt.date(),"open":o,"high":h,"low":l,"close":c,
                    "volume":float(x.get("v") or 0),"vwap":x.get("vw")})
    return out[-250:]
