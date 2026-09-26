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

router=APIRouter(prefix="/api/v14",tags=["V14"])

def failure(stage,asset,exc=None,**extra):
    out={"ok":False,"stage":stage,"asset":asset}
    if exc is not None:
        out.update({"error_type":type(exc).__name__,"error":str(exc)})
    out.update(extra)
    return out

def completed_weekday(lag_days):
    d=date.today()-timedelta(days=max(1,int(lag_days)))
    while d.weekday()>=5:d-=timedelta(days=1)
    return d

@router.get("/universe")
async def universe():
    return {"ok":True,"total":len(all_assets()),
            "provider_verified":len(provider_verified_assets()),
            "assets":[a.__dict__ for a in all_assets()]}

@router.get("/cache-status/{asset_id}")
async def cache_status(asset_id:str):
    try:return {"ok":True,"cache":memory_status(asset_id),"massive_called":False}
    except Exception as exc:return failure("cache_status",asset_id,exc,massive_called=False)

@router.get("/cache-refresh/{asset_id}")
async def cache_refresh(asset_id:str,calendar_days:int=1,lag_days:int=DEFAULT_PROVIDER_LAG_DAYS):
    asset_id=asset_id.upper().strip();asset=get_asset(asset_id)
    if not asset or not asset.provider_verified:
        return failure("asset_validation",asset_id,error="provider_mapping_not_verified")
    days=max(1,min(int(calendar_days),MAX_REFRESH_DAYS))
    end=completed_weekday(lag_days);start=end-timedelta(days=days-1)
    try:bars=await fetch_minute_bars(asset_id,start,end)
    except Exception as exc:
        return failure("provider_fetch",asset_id,exc,massive_called=True,firestore_write_attempted=False)
    if not bars:
        return failure("provider_fetch",asset_id,error="no_data",massive_called=True,firestore_write_attempted=False)
    try:written=save_bars(bars,asset.market_timezone)
    except Exception as exc:
        return failure("cache_write",asset_id,exc,massive_called=True,
                       firestore_write_attempted=True,downloaded_bars=len(bars))
    return {"ok":True,"stage":"complete","asset":asset_id,
            "start_day":start.isoformat(),"market_day_end":end.isoformat(),
            "downloaded_bars":len(bars),"daily_documents_written":written,
            "massive_called":True,"firestore_write_attempted":True}

@router.get("/forecast-cache/{asset_id}/{market_day}")
async def forecast_cache(asset_id:str,market_day:str,hhmm:str="12:30"):
    asset_id=asset_id.upper().strip();asset=get_asset(asset_id)
    if not asset:return failure("asset_validation",asset_id,error="unknown_asset")
    try:
        day=date.fromisoformat(market_day);bars=load_day(asset_id,market_day)
        if not bars:return failure("cache_read",asset_id,error="day_not_cached",market_day=market_day)
        h,m=map(int,hhmm.split(":"))
        cutoff=datetime(day.year,day.month,day.day,h,m,
                        tzinfo=ZoneInfo(asset.market_timezone)).astimezone(timezone.utc)
        store=HistoricalStore();store.extend(bars)
        snapshot=SnapshotEngine(store).build(asset_id,cutoff)
        if not anti_leak(snapshot):return failure("anti_leak",asset_id,error="future_data_visible")
        forecast_id,d,x,v=forecast_snapshot(snapshot)
        if not x or not v:
            return failure("forecast",asset_id,error=d.status,visible_bars=len(snapshot.bars))
        payload={"ok":True,"forecast_id":forecast_id,"asset":asset_id,
                 "market_day":market_day,"forecast_time_utc":cutoff.isoformat(),
                 "reference_price":d.reference_price,"features":d.features,
                 "X":x.to_dict(),"V":v.to_dict(),"direction":v.direction,
                 "expected_future_x_to_v_pct":v.expected_x_to_v_pct,
                 "calibration_status":"NOT_CALIBRATED","massive_called":False}
        try:payload["forecast_persisted"]=save_frozen_forecast(forecast_id,payload)
        except Exception as e:
            payload["forecast_persisted"]=False;payload["persistence_error"]=str(e)
        return payload
    except Exception as exc:return failure("forecast_cache",asset_id,exc,massive_called=False)

@router.get("/walk-forward/{asset_id}")
async def walk_forward(asset_id:str,end_day:str|None=None,calendar_days:int=1):
    """
    Cache-only frozen walk-forward diagnostic.
    No Massive/provider call is made here.
    Only explicitly requested daily cache documents are read.
    """
    asset_id=asset_id.upper().strip();asset=get_asset(asset_id)
    if not asset:return failure("asset_validation",asset_id,error="unknown_asset")
    days=max(1,min(int(calendar_days),730))
    try:
        end=date.fromisoformat(end_day) if end_day else completed_weekday(DEFAULT_PROVIDER_LAG_DAYS)
        start=end-timedelta(days=days-1)
    except Exception as exc:
        return failure("walk_forward_date",asset_id,exc,provider_called=False)
    requested=[]
    cursor=start
    while cursor<=end:
        if cursor.weekday()<5:requested.append(cursor)
        cursor+=timedelta(days=1)
    cached={}
    missing=[]
    try:
        for d in sorted(requested):
            bars=load_day(asset_id,d.isoformat())
            if bars:cached[d]=bars
            else:missing.append(d.isoformat())
    except Exception as exc:
        return failure("walk_forward_cache_read",asset_id,exc,provider_called=False)
    if not cached:
        return failure("walk_forward_cache_read",asset_id,error="no_requested_days_cached",
                       requested_days=[d.isoformat() for d in sorted(requested)],
                       missing_days=missing,provider_called=False)
    try:
        result=run_cached_walk_forward(asset_id,cached)
    except Exception as exc:
        return failure("walk_forward",asset_id,exc,provider_called=False)
    result["requested_calendar_days"]=days
    result["requested_start_day"]=start.isoformat()
    result["requested_end_day"]=end.isoformat()
    result["requested_days"]=[d.isoformat() for d in sorted(requested)]
    result["cached_days_used"]=[d.isoformat() for d in sorted(cached)]
    result["missing_days"]=missing
    result["provider_called"]=False
    result["calibration_status"]="DIAGNOSTIC_ONLY_NOT_CALIBRATED"
    return result

@router.get("/history-backfill/{asset_id}")
async def history_backfill(asset_id: str, days: int = 90, dry_run: bool = True):
    asset_id = asset_id.upper().strip()
    try:
        days = max(1, min(int(days), 730))
        end = completed_weekday(DEFAULT_PROVIDER_LAG_DAYS)
        start = end - timedelta(days=days - 1)
        result = await backfill_history(asset_id=asset_id, start_day=start, end_day=end, window_calendar_days=14, pause_seconds=13.0, dry_run=dry_run)
    except Exception as exc:
        return failure("history_backfill", asset_id, exc, provider_called=False if dry_run else None)
    result["requested_calendar_days"] = days
    result["endpoint_dry_run_default"] = True
    if dry_run:
        result["provider_called"] = False
    return result

@router.get("/history-backfill-window-run/{asset_id}/{window_number}")
async def history_backfill_window_run(asset_id: str, window_number: int):
    """Fetch exactly one 14-calendar-day window from the current 90-day range."""
    asset_id = asset_id.upper().strip()
    try:
        window_number = int(window_number)
        if window_number < 1 or window_number > 7:
            raise ValueError("window_number must be between 1 and 7")
        overall_end = completed_weekday(DEFAULT_PROVIDER_LAG_DAYS)
        overall_start = overall_end - timedelta(days=89)
        window_start = overall_start + timedelta(days=(window_number - 1) * 14)
        if window_start > overall_end:
            raise ValueError("window starts after the current backfill range")
        window_end = min(window_start + timedelta(days=13), overall_end)
        result = await backfill_history(asset_id=asset_id, start_day=window_start, end_day=window_end, window_calendar_days=14, pause_seconds=0.0, dry_run=False)
    except Exception as exc:
        return failure("history_backfill_window", asset_id, exc, provider_called=None)
    result["window_number"] = window_number
    result["window_start"] = window_start.isoformat()
    result["window_end"] = window_end.isoformat()
    result["overall_backfill_calendar_days"] = 90
    result["single_window_only"] = True
    return result


@router.get("/training-dataset/{asset_id}")
async def training_dataset(asset_id: str, calendar_days: int = 90):
    """Stage 3B: build a cache-only historical learning dataset and return summary only."""
    asset_id = asset_id.upper().strip()
    if not get_asset(asset_id):
        return failure("training_dataset", asset_id, error="unknown_asset", provider_called=False)
    try:
        days = max(1, min(int(calendar_days), 730))
        end = completed_weekday(DEFAULT_PROVIDER_LAG_DAYS)
        start = end - timedelta(days=days - 1)
        dataset = build_training_dataset(asset_id, start, end)
        split = chronological_split(dataset)
        return {
            "ok": True,
            "stage": "3B_DATASET",
            "asset": asset_id,
            "requested_calendar_days": days,
            "start_day": start.isoformat(),
            "end_day": end.isoformat(),
            "cached_days_used_count": len(dataset["cached_days_used"]),
            "cached_days_used": dataset["cached_days_used"],
            "missing_weekdays": dataset["missing_weekdays"],
            "sample_every_minutes": dataset["sample_every_minutes"],
            "horizons": dataset["horizons"],
            "examples": dataset["examples"],
            "examples_by_horizon": dataset["examples_by_horizon"],
            "train_examples": len(split["train"]),
            "validation_examples": len(split["validation"]),
            "holdout_examples": len(split["holdout"]),
            "train_days": split["train_days"],
            "validation_days": split["validation_days"],
            "holdout_days": split["holdout_days"],
            "provider_called": False,
            "firestore_write_performed": False,
            "leakage_rule": dataset["leakage_rule"],
        }
    except Exception as exc:
        return failure("training_dataset", asset_id, exc, provider_called=False)


@router.get("/model-validation/{asset_id}")
async def model_validation(asset_id: str, calendar_days: int = 90):
    """Stage 3C: fit on TRAIN only and evaluate on VALIDATION only. Holdout is untouched."""
    asset_id = asset_id.upper().strip()
    if not get_asset(asset_id):
        return failure("model_validation", asset_id, error="unknown_asset", provider_called=False)

    try:
        days = max(1, min(int(calendar_days), 730))
        end = completed_weekday(DEFAULT_PROVIDER_LAG_DAYS)
        start = end - timedelta(days=days - 1)

        dataset = build_training_dataset(asset_id, start, end)
        split = chronological_split(dataset)
        train_rows = split["train"]
        validation_rows = split["validation"]

        if not train_rows or not validation_rows:
            return failure(
                "model_validation",
                asset_id,
                error="insufficient_train_or_validation_rows",
                provider_called=False,
            )

        model = EmpiricalForecastModel().fit(train_rows)

        total = 0
        direction_correct = 0
        abs_terminal_errors = []
        abs_upside_errors = []
        abs_downside_errors = []
        by_horizon = {}

        for row in validation_rows:
            features = {
                "return_5m_pct": row["return_5m_pct"],
                "return_15m_pct": row["return_15m_pct"],
                "return_30m_pct": row["return_30m_pct"],
                "realized_abs_30m_pct": row["realized_abs_30m_pct"],
            }
            h = int(row["horizon_minutes"])
            pred = model.predict(features, h)
            if pred.status != "ok":
                continue

            actual_terminal = float(row["future_terminal_return_pct"])
            actual_upside = float(row["future_upside_reach_pct"])
            actual_downside = float(row["future_downside_reach_pct"])

            predicted_direction = 1 if pred.expected_terminal_return_pct > 0 else (-1 if pred.expected_terminal_return_pct < 0 else 0)
            actual_direction = 1 if actual_terminal > 0 else (-1 if actual_terminal < 0 else 0)

            correct = int(predicted_direction == actual_direction and actual_direction != 0)
            terminal_error = abs(pred.expected_terminal_return_pct - actual_terminal)
            upside_error = abs(pred.expected_upside_reach_pct - actual_upside)
            downside_error = abs(pred.expected_downside_reach_pct - actual_downside)

            total += 1
            direction_correct += correct
            abs_terminal_errors.append(terminal_error)
            abs_upside_errors.append(upside_error)
            abs_downside_errors.append(downside_error)

            bucket = by_horizon.setdefault(h, {
                "samples": 0,
                "direction_correct": 0,
                "terminal_abs_errors": [],
                "upside_abs_errors": [],
                "downside_abs_errors": [],
            })
            bucket["samples"] += 1
            bucket["direction_correct"] += correct
            bucket["terminal_abs_errors"].append(terminal_error)
            bucket["upside_abs_errors"].append(upside_error)
            bucket["downside_abs_errors"].append(downside_error)

        def mean(xs):
            return sum(xs) / len(xs) if xs else None

        horizon_summary = {}
        for h, b in sorted(by_horizon.items()):
            horizon_summary[str(h)] = {
                "samples": b["samples"],
                "direction_accuracy": b["direction_correct"] / b["samples"] if b["samples"] else None,
                "mean_abs_terminal_error_pct_points": mean(b["terminal_abs_errors"]),
                "mean_abs_upside_reach_error_pct_points": mean(b["upside_abs_errors"]),
                "mean_abs_downside_reach_error_pct_points": mean(b["downside_abs_errors"]),
            }

        return {
            "ok": True,
            "stage": "3C_MODEL_VALIDATION",
            "asset": asset_id,
            "requested_calendar_days": days,
            "train_examples": len(train_rows),
            "validation_examples": len(validation_rows),
            "validation_predictions_scored": total,
            "train_days": split["train_days"],
            "validation_days": split["validation_days"],
            "holdout_days_reserved": split["holdout_days"],
            "holdout_examples_reserved": len(split["holdout"]),
            "holdout_used": False,
            "model": model.metadata(),
            "validation_summary": {
                "direction_accuracy": direction_correct / total if total else None,
                "mean_abs_terminal_error_pct_points": mean(abs_terminal_errors),
                "mean_abs_upside_reach_error_pct_points": mean(abs_upside_errors),
                "mean_abs_downside_reach_error_pct_points": mean(abs_downside_errors),
            },
            "by_horizon": horizon_summary,
            "provider_called": False,
            "firestore_write_performed": False,
            "calibration_status": "VALIDATION_ONLY_NOT_CALIBRATED",
        }
    except Exception as exc:
        return failure("model_validation", asset_id, exc, provider_called=False)
