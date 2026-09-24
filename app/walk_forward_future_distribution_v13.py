import asyncio
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List
from zoneinfo import ZoneInfo

from .asset_registry import get_asset
from .future_distribution_v13 import FutureDistributionEngine, DEFAULT_HORIZONS
from .historical_store import HistoricalStore
from .massive_history_v13 import fetch_minute_bars
from .snapshot_engine import SnapshotEngine

UTC = timezone.utc


@dataclass(frozen=True)
class ForecastEvaluation:
    market_date: str
    forecast_time_utc: str
    horizon_minutes: int
    predicted_return_pct: float
    actual_return_pct: float
    absolute_error_pct_points: float
    direction_hit: bool
    inside_predicted_range: bool


def _market_dt(day: date, hhmm: str, tz_name: str) -> datetime:
    hour, minute = map(int, hhmm.split(":"))
    return datetime(
        day.year, day.month, day.day, hour, minute,
        tzinfo=ZoneInfo(tz_name),
    ).astimezone(UTC)


def _latest_completed_bar(bars, when_utc: datetime):
    eligible = [b for b in bars if b.received_at_utc <= when_utc]
    return eligible[-1] if eligible else None


def _direction(value: float, eps: float = 1e-12) -> int:
    if value > eps:
        return 1
    if value < -eps:
        return -1
    return 0


async def run_walk_forward(
    asset_id: str = "AAPL",
    calendar_days: int = 14,
    forecast_times=("10:30", "12:30"),
) -> Dict:
    """
    Historical walk-forward evaluation for the V13 future-distribution baseline.

    At every historical forecast timestamp:
      1. build a snapshot containing only data available by that timestamp;
      2. freeze the forecast;
      3. evaluate it against bars that became available later;
      4. never evaluate beyond that same regular trading session.

    This file evaluates the forecasting layer. It does not create X/V and it
    does not use historical success as a hard gate.
    """
    if not os.getenv("MASSIVE_API_KEY"):
        raise RuntimeError("MASSIVE_API_KEY is not configured")

    asset = get_asset(asset_id)
    if asset is None or not asset.verified:
        raise RuntimeError(f"{asset_id} is not verified in V13 asset registry")

    end_day = date.today() - timedelta(days=1)
    start_day = end_day - timedelta(days=calendar_days - 1)

    # One provider request for the whole interval is preferable to repeated
    # per-day requests. The returned bars remain timestamped/availability-aware.
    bars = await fetch_minute_bars(asset.asset_id, start_day, end_day)
    if not bars:
        raise RuntimeError("No minute history returned")

    by_market_day: Dict[date, List] = {}
    market_tz = ZoneInfo(asset.market_timezone)

    for bar in bars:
        local_day = bar.timestamp_utc.astimezone(market_tz).date()
        by_market_day.setdefault(local_day, []).append(bar)

    model = FutureDistributionEngine()
    evaluations: List[ForecastEvaluation] = []

    for market_day in sorted(by_market_day):
        if market_day.weekday() >= 5:
            continue

        day_bars = sorted(
            by_market_day[market_day],
            key=lambda b: (b.timestamp_utc, b.received_at_utc),
        )

        session_open = _market_dt(
            market_day, asset.session_open, asset.market_timezone
        )
        session_close = _market_dt(
            market_day, asset.session_close, asset.market_timezone
        )

        # Keep only the regular-session day in the store used by this forecast.
        regular = [
            b for b in day_bars
            if session_open <= b.timestamp_utc < session_close
        ]
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

            # Anti-leak invariants BEFORE forecasting.
            if not snapshot.bars:
                continue
            assert all(
                b.received_at_utc <= forecast_time for b in snapshot.bars
            )
            assert all(
                session_open <= b.timestamp_utc < session_close
                for b in snapshot.bars
            )

            frozen = model.forecast(snapshot, DEFAULT_HORIZONS)
            if frozen.status != "ok":
                continue

            for h, pred in frozen.horizons.items():
                target_time = forecast_time + timedelta(minutes=h)

                # Strict day-trading rule: no overnight rescue.
                if target_time > session_close:
                    continue

                outcome_bar = _latest_completed_bar(regular, target_time)
                if outcome_bar is None:
                    continue
                if outcome_bar.received_at_utc <= forecast_time:
                    continue

                actual_return = (
                    (float(outcome_bar.close) / float(frozen.reference_price))
                    - 1.0
                ) * 100.0

                predicted_return = float(pred.expected_terminal_return_pct)

                evaluations.append(
                    ForecastEvaluation(
                        market_date=market_day.isoformat(),
                        forecast_time_utc=forecast_time.isoformat(),
                        horizon_minutes=h,
                        predicted_return_pct=predicted_return,
                        actual_return_pct=actual_return,
                        absolute_error_pct_points=abs(
                            predicted_return - actual_return
                        ),
                        direction_hit=(
                            _direction(predicted_return)
                            == _direction(actual_return)
                        ),
                        inside_predicted_range=(
                            pred.predicted_price_low
                            <= float(outcome_bar.close)
                            <= pred.predicted_price_high
                        ),
                    )
                )

    if not evaluations:
        raise RuntimeError("No forecasts could be evaluated")

    by_horizon = {}
    for h in DEFAULT_HORIZONS:
        rows = [x for x in evaluations if x.horizon_minutes == h]
        if not rows:
            continue

        by_horizon[h] = {
            "samples": len(rows),
            "direction_hit_rate": (
                sum(x.direction_hit for x in rows) / len(rows)
            ),
            "mean_absolute_error_pct_points": (
                sum(x.absolute_error_pct_points for x in rows) / len(rows)
            ),
            "range_coverage": (
                sum(x.inside_predicted_range for x in rows) / len(rows)
            ),
        }

    overall = {
        "samples": len(evaluations),
        "direction_hit_rate": (
            sum(x.direction_hit for x in evaluations) / len(evaluations)
        ),
        "mean_absolute_error_pct_points": (
            sum(x.absolute_error_pct_points for x in evaluations)
            / len(evaluations)
        ),
        "range_coverage": (
            sum(x.inside_predicted_range for x in evaluations)
            / len(evaluations)
        ),
    }

    return {
        "asset_id": asset.asset_id,
        "model": "visible_only_robust_baseline_v13",
        "period": {
            "start": start_day.isoformat(),
            "end": end_day.isoformat(),
        },
        "forecast_times_market": list(forecast_times),
        "overall": overall,
        "by_horizon": by_horizon,
        "note": (
            "This measures out-of-time historical forecasts without crossing "
            "the regular-session boundary. It is validation data, not a hard "
            "pass/fail gate and not yet an X/V forecast."
        ),
    }


async def main():
    result = await run_walk_forward()
    print("V13 FUTURE DISTRIBUTION WALK-FORWARD")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
