from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from fastapi import APIRouter

from .asset_registry import get_asset, all_assets, provider_verified_assets
from .settings import DEFAULT_PROVIDER_LAG_DAYS, MAX_REFRESH_DAYS
from .massive_provider import fetch_minute_bars
from .historical_cache import save_bars, load_day, memory_status
from .historical_store import HistoricalStore
from .snapshot_engine import SnapshotEngine
from .forecast_pipeline import forecast_snapshot
from .validation import anti_leak
from .storage import save_frozen_forecast

router=APIRouter(prefix="/api/v14",tags=["V14"])

def failure(stage,asset,exc=None,**extra):
    out={"ok":False,"stage":stage,"asset":asset}
    if exc is not None:
        out.update({"error_type":type(exc).__name__,"error":str(exc)})
    out.update(extra)
    return out

def completed_weekday(lag_days):
    d=date.today()-timedelta(days=max(1,int(lag_days)))
    while d.weekday()>=5:
        d-=timedelta(days=1)
    return d

@router.get("/universe")
async def universe():
    return {
        "ok":True,"total":len(all_assets()),
        "provider_verified":len(provider_verified_assets()),
        "assets":[a.__dict__ for a in all_assets()]
    }

@router.get("/cache-status/{asset_id}")
async def cache_status(asset_id:str):
    try:
        return {"ok":True,"cache":memory_status(asset_id),"massive_called":False}
    except Exception as exc:
        return failure("cache_status",asset_id,exc,massive_called=False)

@router.get("/cache-refresh/{asset_id}")
async def cache_refresh(asset_id:str,calendar_days:int=1,lag_days:int=DEFAULT_PROVIDER_LAG_DAYS):
    asset_id=asset_id.upper().strip()
    asset=get_asset(asset_id)
    if not asset or not asset.provider_verified:
        return failure("asset_validation",asset_id,error="provider_mapping_not_verified")
    days=max(1,min(int(calendar_days),MAX_REFRESH_DAYS))
    end=completed_weekday(lag_days)
    start=end-timedelta(days=days-1)
    try:
        bars=await fetch_minute_bars(asset_id,start,end)
    except Exception as exc:
        return failure("provider_fetch",asset_id,exc,massive_called=True,firestore_write_attempted=False)
    if not bars:
        return failure("provider_fetch",asset_id,error="no_data",massive_called=True,firestore_write_attempted=False)
    try:
        written=save_bars(bars,asset.market_timezone)
    except Exception as exc:
        return failure("cache_write",asset_id,exc,massive_called=True,
                       firestore_write_attempted=True,downloaded_bars=len(bars))
    return {
        "ok":True,"stage":"complete","asset":asset_id,
        "start_day":start.isoformat(),"market_day_end":end.isoformat(),
        "downloaded_bars":len(bars),"daily_documents_written":written,
        "massive_called":True,"firestore_write_attempted":True
    }

@router.get("/forecast-cache/{asset_id}/{market_day}")
async def forecast_cache(asset_id:str,market_day:str,hhmm:str="12:30"):
    asset_id=asset_id.upper().strip()
    asset=get_asset(asset_id)
    if not asset:
        return failure("asset_validation",asset_id,error="unknown_asset")
    try:
        day=date.fromisoformat(market_day)
        bars=load_day(asset_id,market_day)
        if not bars:
            return failure("cache_read",asset_id,error="day_not_cached",market_day=market_day)
        h,m=map(int,hhmm.split(":"))
        cutoff=datetime(day.year,day.month,day.day,h,m,
                        tzinfo=ZoneInfo(asset.market_timezone)).astimezone(timezone.utc)
        store=HistoricalStore();store.extend(bars)
        snapshot=SnapshotEngine(store).build(asset_id,cutoff)
        if not anti_leak(snapshot):
            return failure("anti_leak",asset_id,error="future_data_visible")
        forecast_id,d,x,v=forecast_snapshot(snapshot)
        if not x or not v:
            return failure("forecast",asset_id,error=d.status,visible_bars=len(snapshot.bars))
        payload={
            "ok":True,"forecast_id":forecast_id,"asset":asset_id,
            "market_day":market_day,"forecast_time_utc":cutoff.isoformat(),
            "reference_price":d.reference_price,"features":d.features,
            "X":x.to_dict(),"V":v.to_dict(),
            "direction":v.direction,
            "expected_future_x_to_v_pct":v.expected_x_to_v_pct,
            "calibration_status":"NOT_CALIBRATED",
            "massive_called":False,
        }
        try:
            payload["forecast_persisted"]=save_frozen_forecast(forecast_id,payload)
        except Exception as persist_exc:
            payload["forecast_persisted"]=False
            payload["persistence_error"]=str(persist_exc)
        return payload
    except Exception as exc:
        return failure("forecast_cache",asset_id,exc,massive_called=False)
