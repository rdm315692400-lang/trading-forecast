import asyncio
import os
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional
from zoneinfo import ZoneInfo

from .asset_registry import get_asset
from .forecast_x_v13 import XForecastEngine
from .forecast_v_v13 import VForecastEngine
from .future_distribution_v13 import FutureDistributionEngine
from .historical_store import HistoricalStore
from .massive_history_v13 import fetch_minute_bars
from .snapshot_engine import SnapshotEngine

UTC = timezone.utc


@dataclass(frozen=True)
class XVEvaluation:
    market_date: str
    forecast_time_utc: str
    direction: str

    predicted_x_time_start_utc: str
    predicted_x_time_end_utc: str
    predicted_x_price_low: float
    predicted_x_price_high: float
    predicted_x_price_center: float

    predicted_v_time_start_utc: str
    predicted_v_time_end_utc: str
    predicted_v_price_low: float
    predicted_v_price_high: float
    predicted_v_price_center: float
    predicted_x_to_v_pct: float

    x_zone_touched: bool
    actual_x_time_utc: Optional[str]
    actual_x_price: Optional[float]

    v_zone_touched_after_x: bool
    actual_v_time_utc: Optional[str]
    actual_v_price: Optional[float]

    actual_x_to_v_pct: Optional[float]
    x_to_v_error_pct_points: Optional[float]
    direction_realized: Optional[bool]
    v_time_error_minutes: Optional[float]
    v_price_error_pct: Optional[float]

    def to_dict(self):
        return asdict(self)


def _market_dt(day: date, hhmm: str, tz_name: str) -> datetime:
    hour, minute = map(int, hhmm.split(":"))
    return datetime(
        day.year, day.month, day.day, hour, minute,
        tzinfo=ZoneInfo(tz_name),
    ).astimezone(UTC)


def _touches(bar, low: float, high: float) -> bool:
    return float(bar.low) <= high and float(bar.high) >= low


def _touch_price(bar, low: float, high: float) -> float:
    close = float(bar.close)
    if low <= close <= high:
        return close
    return low if close < low else high


def _window_error_minutes(
    actual: datetime,
    start: datetime,
    end: datetime,
) -> float:
    if start <= actual <= end:
        return 0.0
    if actual < start:
        return (start - actual).total_seconds() / 60.0
    return (actual - end).total_seconds() / 60.0


async def run_walk_forward_xv(
    asset_id: str = "AAPL",
    calendar_days: int = 14,
    forecast_times=("10:30", "12:30"),
) -> Dict:
    """
    Walk-forward evaluation of the complete frozen X -> V forecast.

    Forecast sequence:
      snapshot at t
        -> future distribution
        -> X forecast
        -> V forecast

    Only AFTER all three are frozen are later bars inspected.

    Evaluation never redefines X or V as realized future extrema.
    Everything stays inside the same regular trading session.
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
        market_day = bar.timestamp_utc.astimezone(market_tz).date()
        by_day.setdefault(market_day, []).append(bar)

    distribution_engine = FutureDistributionEngine()
    x_engine = XForecastEngine()
    v_engine = VForecastEngine()

    evaluations: List[XVEvaluation] = []

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

            # Anti-leak check before any forecast.
            assert all(
                b.received_at_utc <= forecast_time
                for b in snapshot.bars
            )

            # Freeze the complete forecast before opening the future.
            future = distribution_engine.forecast(snapshot)
            x = x_engine.forecast(future)
            if x is None:
                continue

            v = v_engine.forecast(future, x)
            if v is None:
                continue

            # Strict same-day/session invariant.
            if x.x_time_start_utc >= session_close:
                continue
            if v.v_time_start_utc >= session_close:
                continue

            x_end = min(x.x_time_end_utc, session_close)
            v_start = min(v.v_time_start_utc, session_close)
            v_end = min(v.v_time_end_utc, session_close)

            if v_end <= forecast_time:
                continue

            # Only now do we inspect later outcomes.
            later = [
                b for b in regular
                if b.received_at_utc > forecast_time
                and b.timestamp_utc < session_close
            ]

            x_candidates = [
                b for b in later
                if _touches(b, x.x_price_low, x.x_price_high)
            ]
            actual_x_bar = x_candidates[0] if x_candidates else None

            actual_x_time = (
                actual_x_bar.received_at_utc
                if actual_x_bar is not None else None
            )
            actual_x_price = (
                _touch_price(
                    actual_x_bar, x.x_price_low, x.x_price_high
                )
                if actual_x_bar is not None else None
            )

            actual_v_bar = None
            actual_v_time = None
            actual_v_price = None

            if actual_x_bar is not None:
                after_x = [
                    b for b in later
                    if b.received_at_utc > actual_x_time
                ]

                v_candidates = [
                    b for b in after_x
                    if _touches(
                        b, v.v_price_low, v.v_price_high
                    )
                ]

                if v_candidates:
                    actual_v_bar = v_candidates[0]
                    actual_v_time = actual_v_bar.received_at_utc
                    actual_v_price = _touch_price(
                        actual_v_bar,
                        v.v_price_low,
                        v.v_price_high,
                    )

            actual_move = None
            move_error = None
            direction_realized = None
            v_time_error = None
            v_price_error = None

            if (
                actual_x_price is not None
                and actual_v_price is not None
                and actual_x_price > 0
            ):
                signed = (
                    (actual_v_price / actual_x_price) - 1.0
                ) * 100.0

                actual_move = (
                    signed if v.direction == "LONG" else -signed
                )
                direction_realized = actual_move > 0

                move_error = abs(
                    float(v.expected_x_to_v_pct) - actual_move
                )

                v_time_error = _window_error_minutes(
                    actual_v_time, v_start, v_end
                )

                if v.v_price_center > 0:
                    v_price_error = abs(
                        (actual_v_price / v.v_price_center) - 1.0
                    ) * 100.0

            evaluations.append(
                XVEvaluation(
                    market_date=market_day.isoformat(),
                    forecast_time_utc=forecast_time.isoformat(),
                    direction=v.direction,

                    predicted_x_time_start_utc=(
                        x.x_time_start_utc.isoformat()
                    ),
                    predicted_x_time_end_utc=x_end.isoformat(),
                    predicted_x_price_low=x.x_price_low,
                    predicted_x_price_high=x.x_price_high,
                    predicted_x_price_center=x.x_price_center,

                    predicted_v_time_start_utc=v_start.isoformat(),
                    predicted_v_time_end_utc=v_end.isoformat(),
                    predicted_v_price_low=v.v_price_low,
                    predicted_v_price_high=v.v_price_high,
                    predicted_v_price_center=v.v_price_center,
                    predicted_x_to_v_pct=v.expected_x_to_v_pct,

                    x_zone_touched=actual_x_bar is not None,
                    actual_x_time_utc=(
                        actual_x_time.isoformat()
                        if actual_x_time else None
                    ),
                    actual_x_price=actual_x_price,

                    v_zone_touched_after_x=actual_v_bar is not None,
                    actual_v_time_utc=(
                        actual_v_time.isoformat()
                        if actual_v_time else None
                    ),
                    actual_v_price=actual_v_price,

                    actual_x_to_v_pct=actual_move,
                    x_to_v_error_pct_points=move_error,
                    direction_realized=direction_realized,
                    v_time_error_minutes=v_time_error,
                    v_price_error_pct=v_price_error,
                )
            )

    if not evaluations:
        raise RuntimeError("No X->V forecasts could be evaluated")

    x_hits = [e for e in evaluations if e.x_zone_touched]
    v_hits = [e for e in evaluations if e.v_zone_touched_after_x]
    realized = [
        e for e in evaluations
        if e.actual_x_to_v_pct is not None
    ]

    result = {
        "asset_id": asset.asset_id,
        "model": "xv_forecast_baseline_v13",
        "period": {
            "start": start_day.isoformat(),
            "end": end_day.isoformat(),
        },
        "samples": len(evaluations),
        "x_zone_touch_rate": len(x_hits) / len(evaluations),
        "v_zone_touch_after_x_rate": (
            len(v_hits) / len(x_hits) if x_hits else None
        ),
        "direction_realized_rate": (
            sum(bool(e.direction_realized) for e in realized)
            / len(realized)
            if realized else None
        ),
        "mean_x_to_v_error_pct_points": (
            sum(e.x_to_v_error_pct_points for e in realized
                if e.x_to_v_error_pct_points is not None)
            / sum(1 for e in realized
                  if e.x_to_v_error_pct_points is not None)
            if any(
                e.x_to_v_error_pct_points is not None
                for e in realized
            )
            else None
        ),
        "mean_v_time_error_minutes": (
            sum(e.v_time_error_minutes for e in realized
                if e.v_time_error_minutes is not None)
            / sum(1 for e in realized
                  if e.v_time_error_minutes is not None)
            if any(
                e.v_time_error_minutes is not None
                for e in realized
            )
            else None
        ),
        "mean_v_price_error_pct": (
            sum(e.v_price_error_pct for e in realized
                if e.v_price_error_pct is not None)
            / sum(1 for e in realized
                  if e.v_price_error_pct is not None)
            if any(
                e.v_price_error_pct is not None
                for e in realized
            )
            else None
        ),
        "evaluations": [e.to_dict() for e in evaluations],
        "note": (
            "The complete X->V forecast is frozen before later bars are "
            "evaluated. No realized future high/low is used to redefine X or V. "
            "Metrics are calibration diagnostics, not a hard pass/fail gate."
        ),
    }
    return result


async def main():
    result = await run_walk_forward_xv()
    print("V13 X->V WALK-FORWARD")
    print("asset:", result["asset_id"])
    print("samples:", result["samples"])
    print("X touch rate:", result["x_zone_touch_rate"])
    print(
        "V touch after X rate:",
        result["v_zone_touch_after_x_rate"],
    )
    print(
        "direction realized rate:",
        result["direction_realized_rate"],
    )
    print(
        "mean X->V error:",
        result["mean_x_to_v_error_pct_points"],
    )
    print(
        "mean V time error:",
        result["mean_v_time_error_minutes"],
    )
    print(
        "mean V price error %:",
        result["mean_v_price_error_pct"],
    )
    print("PASS: complete X->V forecast was frozen before evaluation.")


if __name__ == "__main__":
    asyncio.run(main())
