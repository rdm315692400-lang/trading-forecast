import asyncio
import os
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from .asset_registry import get_asset
from .forecast_x_v13 import XForecastEngine
from .future_distribution_v13 import FutureDistributionEngine
from .historical_store import HistoricalStore
from .massive_history_v13 import fetch_minute_bars
from .snapshot_engine import SnapshotEngine

UTC = timezone.utc


@dataclass(frozen=True)
class XEvaluation:
    market_date: str
    forecast_time_utc: str
    direction_after_x: str
    path_type: str

    predicted_x_time_start_utc: str
    predicted_x_time_end_utc: str
    predicted_x_price_low: float
    predicted_x_price_high: float
    predicted_x_price_center: float

    zone_touched: bool
    first_zone_touch_utc: Optional[str]
    first_zone_touch_price: Optional[float]
    time_error_minutes: Optional[float]
    price_error_pct: Optional[float]

    continuation_observed: bool
    continuation_return_pct: Optional[float]

    def to_dict(self):
        return asdict(self)


def _market_dt(day: date, hhmm: str, tz_name: str) -> datetime:
    hour, minute = map(int, hhmm.split(":"))
    return datetime(
        day.year, day.month, day.day, hour, minute,
        tzinfo=ZoneInfo(tz_name),
    ).astimezone(UTC)


def _bar_touches_zone(bar, low: float, high: float) -> bool:
    return float(bar.low) <= high and float(bar.high) >= low


def _representative_touch_price(bar, low: float, high: float) -> float:
    close = float(bar.close)
    if low <= close <= high:
        return close
    if close < low:
        return low
    return high


def _minutes_from_window(
    actual_time: datetime,
    start: datetime,
    end: datetime,
) -> float:
    if start <= actual_time <= end:
        return 0.0
    if actual_time < start:
        return (start - actual_time).total_seconds() / 60.0
    return (actual_time - end).total_seconds() / 60.0


async def run_walk_forward_x(
    asset_id: str = "AAPL",
    calendar_days: int = 14,
    forecast_times=("10:30", "12:30"),
    continuation_minutes: int = 30,
) -> Dict:
    """
    Evaluate frozen X forecasts against later same-session bars.

    Important:
    - X is forecast BEFORE future bars are inspected.
    - Evaluation does not redefine X as the realized low/high.
    - A zone touch means a later bar traded through the predicted price zone.
    - Continuation is measured AFTER the first zone touch.
    - No horizon is allowed to cross the regular-session close.
    """
    if not os.getenv("MASSIVE_API_KEY"):
        raise RuntimeError("MASSIVE_API_KEY is not configured")

    asset = get_asset(asset_id)
    if asset is None or not asset.verified:
        raise RuntimeError(f"{asset_id} is not verified in V13 asset registry")

    end_day = date.today() - timedelta(days=1)
    start_day = end_day - timedelta(days=calendar_days - 1)

    bars = await fetch_minute_bars(asset.asset_id, start_day, end_day)
    if not bars:
        raise RuntimeError("No minute history returned")

    market_tz = ZoneInfo(asset.market_timezone)
    by_day: Dict[date, List] = {}
    for bar in bars:
        d = bar.timestamp_utc.astimezone(market_tz).date()
        by_day.setdefault(d, []).append(bar)

    distribution_engine = FutureDistributionEngine()
    x_engine = XForecastEngine()
    evaluations: List[XEvaluation] = []

    for market_day in sorted(by_day):
        if market_day.weekday() >= 5:
            continue

        session_open = _market_dt(
            market_day, asset.session_open, asset.market_timezone
        )
        session_close = _market_dt(
            market_day, asset.session_close, asset.market_timezone
        )

        regular = sorted(
            [
                b for b in by_day[market_day]
                if session_open <= b.timestamp_utc < session_close
            ],
            key=lambda b: (b.timestamp_utc, b.received_at_utc),
        )
        if not regular:
            continue

        store = HistoricalStore()
        store.extend(regular)
        snapshots = SnapshotEngine(store)

        for hhmm in forecast_times:
            forecast_time = _market_dt(
                market_day, hhmm, asset.market_timezone
            )
            if not (session_open < forecast_time < session_close):
                continue

            snapshot = snapshots.build(asset.asset_id, forecast_time)
            if not snapshot.bars:
                continue

            # Freeze all model outputs before reading future outcomes.
            future = distribution_engine.forecast(snapshot)
            x = x_engine.forecast(future)
            if x is None:
                continue

            assert all(
                b.received_at_utc <= forecast_time for b in snapshot.bars
            )

            # X itself must remain inside the same trading session.
            if x.x_time_start_utc >= session_close:
                continue

            predicted_end = min(x.x_time_end_utc, session_close)

            future_bars = [
                b for b in regular
                if b.received_at_utc > forecast_time
                and b.timestamp_utc < session_close
            ]

            touched = [
                b for b in future_bars
                if _bar_touches_zone(
                    b, x.x_price_low, x.x_price_high
                )
            ]

            first_touch = touched[0] if touched else None
            touch_time = (
                first_touch.received_at_utc if first_touch else None
            )
            touch_price = (
                _representative_touch_price(
                    first_touch, x.x_price_low, x.x_price_high
                )
                if first_touch else None
            )

            time_error = (
                _minutes_from_window(
                    touch_time,
                    x.x_time_start_utc,
                    predicted_end,
                )
                if touch_time else None
            )

            price_error = None
            if touch_price is not None and x.x_price_center > 0:
                price_error = abs(
                    (touch_price / x.x_price_center) - 1.0
                ) * 100.0

            continuation_observed = False
            continuation_return = None

            if first_touch and touch_price and touch_price > 0:
                continuation_end = min(
                    touch_time + timedelta(minutes=continuation_minutes),
                    session_close,
                )
                later = [
                    b for b in regular
                    if b.received_at_utc > touch_time
                    and b.received_at_utc <= continuation_end
                ]

                if later:
                    end_price = float(later[-1].close)
                    raw_return = (
                        (end_price / touch_price) - 1.0
                    ) * 100.0

                    continuation_return = (
                        raw_return
                        if x.direction_after_x == "LONG"
                        else -raw_return
                    )
                    continuation_observed = continuation_return > 0

            evaluations.append(
                XEvaluation(
                    market_date=market_day.isoformat(),
                    forecast_time_utc=forecast_time.isoformat(),
                    direction_after_x=x.direction_after_x,
                    path_type=x.path_type,
                    predicted_x_time_start_utc=(
                        x.x_time_start_utc.isoformat()
                    ),
                    predicted_x_time_end_utc=predicted_end.isoformat(),
                    predicted_x_price_low=x.x_price_low,
                    predicted_x_price_high=x.x_price_high,
                    predicted_x_price_center=x.x_price_center,
                    zone_touched=first_touch is not None,
                    first_zone_touch_utc=(
                        touch_time.isoformat() if touch_time else None
                    ),
                    first_zone_touch_price=touch_price,
                    time_error_minutes=time_error,
                    price_error_pct=price_error,
                    continuation_observed=continuation_observed,
                    continuation_return_pct=continuation_return,
                )
            )

    if not evaluations:
        raise RuntimeError("No X forecasts could be evaluated")

    touched = [x for x in evaluations if x.zone_touched]
    continued = [x for x in touched if x.continuation_observed]

    result = {
        "asset_id": asset.asset_id,
        "model": "x_forecast_baseline_v13",
        "period": {
            "start": start_day.isoformat(),
            "end": end_day.isoformat(),
        },
        "samples": len(evaluations),
        "zone_touch_rate": len(touched) / len(evaluations),
        "continuation_after_touch_rate": (
            len(continued) / len(touched) if touched else None
        ),
        "mean_time_error_minutes": (
            sum(x.time_error_minutes for x in touched
                if x.time_error_minutes is not None)
            / sum(1 for x in touched if x.time_error_minutes is not None)
            if any(x.time_error_minutes is not None for x in touched)
            else None
        ),
        "mean_price_error_pct": (
            sum(x.price_error_pct for x in touched
                if x.price_error_pct is not None)
            / sum(1 for x in touched if x.price_error_pct is not None)
            if any(x.price_error_pct is not None for x in touched)
            else None
        ),
        "evaluations": [x.to_dict() for x in evaluations],
        "note": (
            "X forecasts are frozen before outcomes. Evaluation never "
            "redefines X using the realized future low/high. Results are "
            "diagnostic calibration data, not a hard trading gate."
        ),
    }
    return result


async def main():
    result = await run_walk_forward_x()
    print("V13 X WALK-FORWARD")
    print("asset:", result["asset_id"])
    print("samples:", result["samples"])
    print("zone touch rate:", result["zone_touch_rate"])
    print(
        "continuation after touch rate:",
        result["continuation_after_touch_rate"],
    )
    print("mean time error:", result["mean_time_error_minutes"])
    print("mean price error %:", result["mean_price_error_pct"])
    print("PASS: X was forecast before future outcomes were evaluated.")


if __name__ == "__main__":
    asyncio.run(main())
