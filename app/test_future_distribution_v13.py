import asyncio
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .asset_registry import get_asset
from .future_distribution_v13 import FutureDistributionEngine, DEFAULT_HORIZONS
from .historical_store import HistoricalStore
from .massive_history_v13 import fetch_minute_bars
from .snapshot_engine import SnapshotEngine

UTC = timezone.utc


def _market_dt(day: date, hhmm: str, tz_name: str) -> datetime:
    hour, minute = map(int, hhmm.split(":"))
    return datetime(
        day.year, day.month, day.day, hour, minute,
        tzinfo=ZoneInfo(tz_name),
    ).astimezone(UTC)


def _latest_completed_price(bars, when_utc: datetime):
    eligible = [
        b for b in bars
        if b.received_at_utc <= when_utc
    ]
    return eligible[-1].close if eligible else None


async def main():
    if not os.getenv("MASSIVE_API_KEY"):
        raise RuntimeError("MASSIVE_API_KEY is not configured")

    asset = get_asset("AAPL")
    if asset is None or not asset.verified:
        raise RuntimeError("AAPL is not verified")

    # Try recent completed weekdays until a day with provider data is found.
    day = date.today() - timedelta(days=1)
    bars = []
    for _ in range(7):
        if day.weekday() < 5:
            bars = await fetch_minute_bars(asset.asset_id, day, day)
            if bars:
                break
        day -= timedelta(days=1)

    if not bars:
        raise RuntimeError("No recent AAPL minute history returned")

    store = HistoricalStore()
    store.extend(bars)
    snapshot_engine = SnapshotEngine(store)
    model = FutureDistributionEngine()

    session_open = _market_dt(day, asset.session_open, asset.market_timezone)
    session_close = _market_dt(day, asset.session_close, asset.market_timezone)

    # Forecast well inside the regular session so all requested horizons
    # can be evaluated without crossing the trading-day boundary.
    forecast_time = _market_dt(day, "12:30", asset.market_timezone)
    snapshot = snapshot_engine.build(asset.asset_id, forecast_time)

    # Freeze the forecast BEFORE reading any outcome.
    forecast = model.forecast(snapshot, DEFAULT_HORIZONS)

    if forecast.status != "ok":
        raise RuntimeError(f"Forecast unavailable: {forecast.status}")

    rows = []
    for h, pred in forecast.horizons.items():
        target_time = forecast_time + timedelta(minutes=h)

        # Day-trading invariant: never evaluate a horizon beyond session close.
        if target_time > session_close:
            continue

        actual_price = _latest_completed_price(bars, target_time)
        if actual_price is None:
            continue

        actual_return = (
            (float(actual_price) / float(forecast.reference_price)) - 1.0
        ) * 100.0

        predicted_return = pred.expected_terminal_return_pct
        abs_error = abs(predicted_return - actual_return)

        predicted_direction = (
            "UP" if predicted_return > 0
            else "DOWN" if predicted_return < 0
            else "FLAT"
        )
        actual_direction = (
            "UP" if actual_return > 0
            else "DOWN" if actual_return < 0
            else "FLAT"
        )

        rows.append({
            "horizon_minutes": h,
            "forecast_time_utc": forecast_time.isoformat(),
            "target_time_utc": target_time.isoformat(),
            "reference_price": round(forecast.reference_price, 6),
            "predicted_return_pct": round(predicted_return, 6),
            "actual_return_pct": round(actual_return, 6),
            "absolute_error_pct_points": round(abs_error, 6),
            "predicted_direction": predicted_direction,
            "actual_direction": actual_direction,
            "direction_hit": predicted_direction == actual_direction,
            "predicted_low": round(pred.predicted_price_low, 6),
            "predicted_median": round(pred.predicted_price_median, 6),
            "predicted_high": round(pred.predicted_price_high, 6),
            "actual_price": round(float(actual_price), 6),
            "inside_predicted_range":
                pred.predicted_price_low <= actual_price <= pred.predicted_price_high,
        })

    if not rows:
        raise RuntimeError("No horizons could be evaluated")

    # Integrity checks: these are more important than a good-looking result.
    assert all(b.received_at_utc <= forecast_time for b in snapshot.bars)
    assert all(b.timestamp_utc <= forecast_time for b in snapshot.bars)
    assert forecast_time >= session_open
    assert forecast_time < session_close
    assert all(
        datetime.fromisoformat(r["target_time_utc"]) <= session_close
        for r in rows
    )

    hits = sum(1 for r in rows if r["direction_hit"])
    range_hits = sum(1 for r in rows if r["inside_predicted_range"])
    mean_abs_error = sum(
        r["absolute_error_pct_points"] for r in rows
    ) / len(rows)

    print("V13 FUTURE DISTRIBUTION TEST")
    print("asset:", asset.asset_id)
    print("historical day:", day.isoformat())
    print("forecast time UTC:", forecast_time.isoformat())
    print("reference price:", forecast.reference_price)
    print("evaluated horizons:", len(rows))
    print("direction hits:", f"{hits}/{len(rows)}")
    print("range hits:", f"{range_hits}/{len(rows)}")
    print("mean absolute return error:", round(mean_abs_error, 6), "pct points")
    print()
    for row in rows:
        print(row)

    print()
    print("PASS: forecast was frozen before outcomes were evaluated.")
    print("NOTE: one day is only an integrity test, not evidence of predictive edge.")


if __name__ == "__main__":
    asyncio.run(main())
