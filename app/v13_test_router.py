from datetime import date, timedelta

from fastapi import APIRouter, HTTPException

from .historical_store import HistoricalStore
from .massive_history_v13 import fetch_minute_bars
from .snapshot_engine import SnapshotEngine
from .test_real_replay_v13 import market_time_to_utc

router = APIRouter(prefix="/api/v13-test", tags=["V13 Test"])


@router.get("/replay/{asset_id}")
async def replay_test(asset_id: str):
    """
    Isolated V13 smoke test.
    Does not modify V12 scanner/cache/forecast state.
    """
    asset_id = asset_id.upper()

    # Most recent completed weekday. If it was an exchange holiday,
    # the endpoint returns a clear error instead of pretending PASS.
    day = date.today() - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)

    try:
        bars = await fetch_minute_bars(asset_id, day, day)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Historical fetch failed: {exc}")

    if not bars:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No minute bars returned for {asset_id} on {day.isoformat()}. "
                "The day may be a market holiday or unavailable on the current data plan."
            ),
        )

    store = HistoricalStore()
    store.extend(bars)
    engine = SnapshotEngine(store)

    cutoff = market_time_to_utc(day, 14, 0)
    snapshot = engine.build(asset_id, cutoff)

    future_rows = [b for b in store.all_bars(asset_id) if b.timestamp_utc > cutoff]

    no_future_timestamp_leak = all(
        b.timestamp_utc <= cutoff for b in snapshot.bars
    )
    no_future_availability_leak = all(
        b.received_at_utc <= cutoff for b in snapshot.bars
    )
    future_exists_but_hidden = len(future_rows) > 0

    passed = (
        no_future_timestamp_leak
        and no_future_availability_leak
        and future_exists_but_hidden
    )

    latest = snapshot.bars[-1] if snapshot.bars else None

    return {
        "ok": passed,
        "version": "13.0-data-foundation",
        "asset": asset_id,
        "historical_day": day.isoformat(),
        "cutoff_market_time": "14:00 America/New_York",
        "cutoff_utc": cutoff.isoformat(),
        "downloaded_rows": len(bars),
        "visible_rows_at_cutoff": len(snapshot.bars),
        "future_rows_in_raw_store_hidden_from_snapshot": len(future_rows),
        "latest_visible_bar_utc": (
            latest.timestamp_utc.isoformat() if latest else None
        ),
        "checks": {
            "no_future_timestamp_leak": no_future_timestamp_leak,
            "no_future_availability_leak": no_future_availability_leak,
            "future_data_exists_in_store_but_is_hidden": future_exists_but_hidden,
        },
        "result": "PASS" if passed else "FAIL",
        "note": "This endpoint is isolated from the V12.5 scanner and ranking.",
    }


# ---------------------------------------------------------------------------
# V13 CACHE-AWARE FORECAST ENDPOINTS
# ---------------------------------------------------------------------------

from datetime import datetime, timezone

from .asset_registry import get_asset
from .future_distribution_v13 import FutureDistributionEngine
from .forecast_x_v13 import XForecastEngine
from .forecast_v_v13 import VForecastEngine
from .v13_historical_cache import cache_status, load_bars, save_bars


@router.get("/cache-status/{asset_id}")
async def v13_cache_status(asset_id: str):
    """
    Diagnostic cache-status endpoint.
    Never calls Massive. If Firestore/cache fails, return the exact error
    in JSON so it is visible from a normal browser.
    """
    asset_id = asset_id.upper().strip()
    try:
        result = cache_status(asset_id)
        return {
            "ok": True,
            "cache": result,
            "massive_called": False,
        }
    except Exception as exc:
        return {
            "ok": False,
            "stage": "v13_cache_status",
            "asset": asset_id,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "massive_called": False,
            "note": "Diagnostic response; no Massive request was made.",
        }


@router.get("/cache-refresh/{asset_id}")
@router.post("/cache-refresh/{asset_id}")
async def v13_cache_refresh(asset_id: str, calendar_days: int = 1):
    """Explicit diagnostic refresh; expected failures return JSON."""
    asset_id = asset_id.upper().strip()
    requested_days = max(1, min(int(calendar_days), 14))
    asset = get_asset(asset_id)
    if asset is None or not asset.verified:
        return {"ok": False, "stage": "asset_validation", "asset": asset_id,
                "error_type": "UnverifiedAsset",
                "error": f"{asset_id} is not verified in the V13 asset registry",
                "massive_called": False, "firestore_write_attempted": False}

    # Basic/EOD diagnostic: stay two calendar days behind today.
    # This avoids requesting a timeframe that may not yet be entitled.
    end_day = date.today() - timedelta(days=2)
    while end_day.weekday() >= 5:
        end_day -= timedelta(days=1)
    start_day = end_day - timedelta(days=requested_days - 1)

    try:
        bars = await fetch_minute_bars(asset_id, start_day, end_day)
    except Exception as exc:
        return {"ok": False, "stage": "massive_fetch", "asset": asset_id,
                "calendar_days": requested_days,
                "error_type": type(exc).__name__, "error": str(exc),
                "massive_called": True, "firestore_write_attempted": False}

    if not bars:
        return {"ok": False, "stage": "massive_fetch", "asset": asset_id,
                "calendar_days": requested_days, "error_type": "NoData",
                "error": "No minute bars returned",
                "massive_called": True, "firestore_write_attempted": False}

    try:
        written = save_bars(bars, market_timezone=asset.market_timezone)
    except Exception as exc:
        return {"ok": False, "stage": "firestore_daily_cache_write",
                "asset": asset_id, "calendar_days": requested_days,
                "downloaded_bars": len(bars),
                "error_type": type(exc).__name__, "error": str(exc),
                "massive_called": True, "firestore_write_attempted": True,
                "note": "Massive fetch succeeded; compact daily cache persistence failed."}

    try:
        status = cache_status(asset_id)
    except Exception as exc:
        status = {"status_error_type": type(exc).__name__,
                  "status_error": str(exc)}

    return {"ok": True, "stage": "complete", "asset": asset_id,
            "calendar_days": requested_days,
            "downloaded_bars": len(bars),
            "daily_documents_written": written,
            "cache": status,
            "massive_called": True, "firestore_write_attempted": True,
            "note": "Compact cache refresh completed; cache-status performs zero Firestore reads."}


@router.get("/forecast-cache/{asset_id}")
async def v13_forecast_from_cache(asset_id: str):
    """
    V13 forecast using Firestore cache only.
    This endpoint never calls Massive.
    """
    asset_id = asset_id.upper().strip()
    asset = get_asset(asset_id)
    if asset is None or not asset.verified:
        raise HTTPException(
            status_code=404,
            detail=f"{asset_id} is not verified in the V13 asset registry",
        )

    # Read one explicit daily document only.
    # No broad Firestore scan is performed.
    market_tz = __import__("zoneinfo").ZoneInfo(asset.market_timezone)

    latest_market_day = date.today() - timedelta(days=1)
    while latest_market_day.weekday() >= 5:
        latest_market_day -= timedelta(days=1)

    day_bars = load_bars(
        asset_id,
        market_days=[latest_market_day.isoformat()],
    )
    if not day_bars:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No V13 daily cache document for {asset_id} on "
                f"{latest_market_day.isoformat()}. "
                "Run cache-refresh once when Firestore quota permits."
            ),
        )

    store = HistoricalStore()
    store.extend(day_bars)
    engine = SnapshotEngine(store)

    # Historical smoke forecast at 12:30 market time.
    local_cutoff = datetime(
        latest_market_day.year,
        latest_market_day.month,
        latest_market_day.day,
        12,
        30,
        tzinfo=market_tz,
    )
    cutoff = local_cutoff.astimezone(timezone.utc)
    snapshot = engine.build(asset_id, cutoff)

    if not snapshot.bars:
        raise HTTPException(
            status_code=422,
            detail="Cached data exists but no bars were visible at cutoff",
        )

    if any(b.received_at_utc > cutoff for b in snapshot.bars):
        raise HTTPException(
            status_code=500,
            detail="Anti-leak check failed",
        )

    distribution = FutureDistributionEngine().forecast(snapshot)
    x = XForecastEngine().forecast(distribution)
    if x is None:
        raise HTTPException(status_code=422, detail="No X forecast produced")

    v = VForecastEngine().forecast(distribution, x)
    if v is None:
        raise HTTPException(status_code=422, detail="No V forecast produced")

    return {
        "ok": True,
        "version": "13.0-cache-forecast-baseline",
        "data_source": "firestore_cache",
        "massive_called": False,
        "asset": asset_id,
        "historical_day": latest_market_day.isoformat(),
        "forecast_time_utc": cutoff.isoformat(),
        "reference_price": distribution.reference_price,
        "pre_entry_path": x.path_type,
        "direction": v.direction,
        "X": {
            "time_start_utc": x.x_time_start_utc.isoformat(),
            "time_end_utc": x.x_time_end_utc.isoformat(),
            "price_low": x.x_price_low,
            "price_high": x.x_price_high,
            "price_center": x.x_price_center,
        },
        "V": {
            "time_start_utc": v.v_time_start_utc.isoformat(),
            "time_end_utc": v.v_time_end_utc.isoformat(),
            "price_low": v.v_price_low,
            "price_high": v.v_price_high,
            "price_center": v.v_price_center,
        },
        "expected_future_x_to_v_pct": v.expected_x_to_v_pct,
        "source_horizon_minutes": v.source_horizon_minutes,
        "status": v.status,
        "note": (
            "Forecast reads Firestore cache only. "
            "Baseline remains uncalibrated and isolated from V12.5 ranking."
        ),
    }
