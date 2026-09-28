import asyncio
import math
from datetime import date,datetime,timedelta,timezone
from zoneinfo import ZoneInfo
from fastapi import APIRouter

from .asset_registry import get_asset,all_assets,provider_verified_assets
from .settings import DEFAULT_PROVIDER_LAG_DAYS,MAX_REFRESH_DAYS
from .massive_provider import fetch_minute_bars
from .historical_cache import save_bars,load_day,memory_status
from .historical_store import HistoricalStore
from .snapshot_engine import SnapshotEngine
from .forecast_pipeline import forecast_snapshot
from .validation import anti_leak
from .storage import save_frozen_forecast
from .walk_forward import run_cached_walk_forward
from .history_backfill import backfill_history
from .training_dataset import build_training_dataset, chronological_split
from .forecast_model import EmpiricalForecastModel
from .research_point1 import scan_history
from .research_trend_start import mark_history

router=APIRouter(prefix="/api/v14",tags=["V14"])

def failure(stage,asset,exc=None,**extra):
    out={"ok":False,"stage":stage,"asset":asset}
    if exc is not None: out.update({"error_type":type(exc).__name__,"error":str(exc)})
    out.update(extra); return out

def completed_weekday(lag_days):
    d=date.today()-timedelta(days=max(1,int(lag_days)))
    while d.weekday()>=5:d-=timedelta(days=1)
    return d

# Existing compact endpoints retained.
@router.get("/universe")
async def universe():
    return {"ok":True,"total":len(all_assets()),"provider_verified":len(provider_verified_assets()),
            "assets":[a.__dict__ for a in all_assets()]}

@router.get("/cache-status/{asset_id}")
async def cache_status(asset_id:str):
    try:return {"ok":True,"cache":memory_status(asset_id),"massive_called":False}
    except Exception as exc:return failure("cache_status",asset_id,exc,massive_called=False)

@router.get("/cache-refresh/{asset_id}")
async def cache_refresh(asset_id:str,calendar_days:int=1,lag_days:int=DEFAULT_PROVIDER_LAG_DAYS):
    asset_id=asset_id.upper().strip();asset=get_asset(asset_id)
    if not asset or not asset.provider_verified:return failure("asset_validation",asset_id,error="provider_mapping_not_verified")
    days=max(1,min(int(calendar_days),MAX_REFRESH_DAYS));end=completed_weekday(lag_days);start=end-timedelta(days=days-1)
    try:bars=await fetch_minute_bars(asset_id,start,end)
    except Exception as exc:return failure("provider_fetch",asset_id,exc,massive_called=True)
    if not bars:return failure("provider_fetch",asset_id,error="no_data",massive_called=True)
    try:written=save_bars(bars,asset.market_timezone)
    except Exception as exc:return failure("cache_write",asset_id,exc,massive_called=True)
    return {"ok":True,"stage":"complete","asset":asset_id,"downloaded_bars":len(bars),
            "daily_documents_written":written,"massive_called":True}

@router.get("/research-bars/{asset_id}/{market_day}")
async def research_bars(asset_id:str,market_day:str):
    asset_id=asset_id.upper().strip();asset=get_asset(asset_id)
    if not asset:return failure("research_bars",asset_id,error="unknown_asset",provider_called=False)
    bars=load_day(asset_id,market_day)
    if not bars:return failure("research_bars",asset_id,error="day_not_cached",provider_called=False)
    z=ZoneInfo(asset.market_timezone); rows=[]
    for b in sorted(bars,key=lambda x:x.timestamp_utc):
        t=b.timestamp_utc.astimezone(z);m=t.hour*60+t.minute
        if t.date().isoformat()==market_day and 570<=m<960:
            rows.append({"time":t.strftime("%H:%M"),"o":b.open,"h":b.high,"l":b.low,"c":b.close,"v":b.volume})
    return {"ok":True,"stage":"RESEARCH_BARS","asset":asset_id,"market_day":market_day,
            "bars":rows,"bar_count":len(rows),"provider_called":False,"forecast_created":False}

# Milestone 1: retrospective marking only.
_trend_start_task=None
_trend_start_state={"running":False,"finished":False,"error":None,"result":None}

async def _run_trend_start_marking(asset_id:str,reserve_last_days:int):
    global _trend_start_state
    _trend_start_state={"running":True,"finished":False,"error":None,"result":None}
    try:
        end=completed_weekday(DEFAULT_PROVIDER_LAG_DAYS);start=end-timedelta(days=729)
        result=await asyncio.to_thread(mark_history,asset_id,start,end,reserve_last_days)
        # Keep status compact; do not expose hundreds of rows in one response.
        days=result.pop("days")
        result["days_marked_count"]=len(days)
        result["preview"]=days[:10]
        _trend_start_state={"running":False,"finished":True,"error":None,"result":result}
    except Exception as exc:
        _trend_start_state={"running":False,"finished":False,
                            "error":{"type":type(exc).__name__,"message":str(exc)},"result":None}

@router.get("/research-trend-start-start/{asset_id}")
async def research_trend_start_start(asset_id:str,reserve_last_days:int=40):
    global _trend_start_task
    asset_id=asset_id.upper().strip()
    if not get_asset(asset_id):
        return failure("research_trend_start_start",asset_id,error="unknown_asset",provider_called=False)
    if _trend_start_task is not None and not _trend_start_task.done():
        return {"ok":True,"stage":"MILESTONE1_ALREADY_RUNNING","state":_trend_start_state}
    reserve_last_days=max(20,min(int(reserve_last_days),100))
    _trend_start_task=asyncio.create_task(_run_trend_start_marking(asset_id,reserve_last_days))
    return {"ok":True,"stage":"MILESTONE1_STARTED","asset":asset_id,
            "reserve_last_days":reserve_last_days,"provider_called":False,
            "forecast_created":False,"analysis_created":False,
            "note":"Retrospective marking only: first quality-trend start minute and direction."}

@router.get("/research-trend-start-status/{asset_id}")
async def research_trend_start_status(asset_id:str):
    return {"ok":True,"stage":"MILESTONE1_STATUS","asset":asset_id.upper().strip(),
            "state":_trend_start_state,"provider_called":False,"forecast_created":False,
            "analysis_created":False}
