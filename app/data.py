from datetime import date,timedelta
import httpx,pandas as pd
from .config import MASSIVE_API_KEY,MASSIVE_BASE
async def minute_history(ticker,days=30):
    end=date.today(); start=end-timedelta(days=days)
    url=f"{MASSIVE_BASE}/v2/aggs/ticker/{ticker}/range/1/minute/{start}/{end}"
    params={"adjusted":"true","sort":"asc","limit":50000,"apiKey":MASSIVE_API_KEY}
    async with httpx.AsyncClient(timeout=60) as client:
        r=await client.get(url,params=params); r.raise_for_status(); rows=r.json().get("results",[])
    if not rows:return pd.DataFrame()
    x=pd.DataFrame(rows).rename(columns={"t":"ts","o":"open","h":"high","l":"low","c":"close","v":"volume","vw":"vwap"})
    x["dt"]=pd.to_datetime(x.ts,unit="ms",utc=True).dt.tz_convert("America/New_York")
    x["day"]=x.dt.dt.date; x["minute"]=x.dt.dt.hour*60+x.dt.dt.minute
    return x
