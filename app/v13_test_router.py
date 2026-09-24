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
