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
# V13 FORECAST TEST ENDPOINTS
# These endpoints are isolated from the V12.5 scanner/cache/ranking.
# ---------------------------------------------------------------------------

from .asset_registry import get_asset
from .future_distribution_v13 import FutureDistributionEngine
from .forecast_x_v13 import XForecastEngine
from .forecast_v_v13 import VForecastEngine
from .walk_forward_future_distribution_v13 import run_walk_forward
from .walk_forward_xv_v13 import run_walk_forward_xv


def _latest_completed_market_day():
    day = date.today() - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


@router.get("/forecast/{asset_id}")
async def forecast_test(asset_id: str):
    """
    Isolated historical V13 forecast smoke test.

    Builds a forecast at 12:30 market time using only information that was
    available by that timestamp, then returns the frozen:
      future distribution -> X -> V -> expected X-to-V percentage.

    This endpoint does not modify V12.5 state.
    """
    asset_id = asset_id.upper().strip()
    asset = get_asset(asset_id)
    if asset is None or not asset.verified:
        raise HTTPException(
            status_code=404,
            detail=f"{asset_id} is not verified in the V13 asset registry",
        )

    day = _latest_completed_market_day()

    try:
        bars = await fetch_minute_bars(asset_id, day, day)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Historical fetch failed: {exc}",
        )

    if not bars:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No minute bars returned for {asset_id} on "
                f"{day.isoformat()}. The day may be a market holiday "
                "or unavailable on the current data plan."
            ),
        )

    store = HistoricalStore()
    store.extend(bars)
    snapshot_engine = SnapshotEngine(store)

    forecast_time = market_time_to_utc(
        day,
        12,
        30,
        asset.market_timezone,
    )
    snapshot = snapshot_engine.build(asset_id, forecast_time)

    if not snapshot.bars:
        raise HTTPException(
            status_code=422,
            detail="No bars were visible at the forecast timestamp",
        )

    if any(b.received_at_utc > forecast_time for b in snapshot.bars):
        raise HTTPException(
            status_code=500,
            detail="Anti-leak check failed before forecast",
        )

    distribution = FutureDistributionEngine().forecast(snapshot)
    if distribution.status != "ok":
        return {
            "ok": False,
            "asset": asset_id,
            "historical_day": day.isoformat(),
            "forecast_time_utc": forecast_time.isoformat(),
            "stage": "future_distribution",
            "status": distribution.status,
            "note": distribution.note,
        }

    x = XForecastEngine().forecast(distribution)
    if x is None:
        return {
            "ok": False,
            "asset": asset_id,
            "historical_day": day.isoformat(),
            "forecast_time_utc": forecast_time.isoformat(),
            "stage": "X",
            "message": "No X forecast was produced",
        }

    v = VForecastEngine().forecast(distribution, x)
    if v is None:
        return {
            "ok": False,
            "asset": asset_id,
            "historical_day": day.isoformat(),
            "forecast_time_utc": forecast_time.isoformat(),
            "stage": "V",
            "message": "No V forecast was produced",
        }

    return {
        "ok": True,
        "version": "13.0-forecast-baseline",
        "asset": asset_id,
        "historical_day": day.isoformat(),
        "forecast_time_utc": forecast_time.isoformat(),
        "reference_price": distribution.reference_price,
        "pre_entry_path": x.path_type,
        "direction": v.direction,
        "X": {
            "time_start_utc": x.x_time_start_utc.isoformat(),
            "time_end_utc": x.x_time_end_utc.isoformat(),
            "price_low": x.x_price_low,
            "price_high": x.x_price_high,
            "price_center": x.x_price_center,
            "expected_counter_move_pct": x.expected_counter_move_pct,
            "baseline_probability": x.x_probability,
        },
        "V": {
            "time_start_utc": v.v_time_start_utc.isoformat(),
            "time_end_utc": v.v_time_end_utc.isoformat(),
            "price_low": v.v_price_low,
            "price_high": v.v_price_high,
            "price_center": v.v_price_center,
            "baseline_probability": v.v_probability,
        },
        "expected_future_x_to_v_pct": v.expected_x_to_v_pct,
        "source_horizon_minutes": v.source_horizon_minutes,
        "anti_leak": {
            "all_visible_bars_received_by_forecast_time": True,
        },
        "status": v.status,
        "note": (
            "Historical frozen V13 forecast test. Baseline is uncalibrated "
            "and is not connected to the live V12.5 scanner/ranking."
        ),
    }


@router.get("/walk-forward-distribution/{asset_id}")
async def distribution_walk_forward_test(asset_id: str):
    asset_id = asset_id.upper().strip()
    try:
        return {
            "ok": True,
            "walk_forward": await run_walk_forward(asset_id=asset_id),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/walk-forward-xv/{asset_id}")
async def xv_walk_forward_test(asset_id: str):
    asset_id = asset_id.upper().strip()
    try:
        return {
            "ok": True,
            "walk_forward": await run_walk_forward_xv(asset_id=asset_id),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
