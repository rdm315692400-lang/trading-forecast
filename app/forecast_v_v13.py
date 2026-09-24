from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from .forecast_x_v13 import XForecast
from .future_distribution_v13 import FutureDistributionForecast, HorizonForecast


@dataclass(frozen=True)
class VForecast:
    asset_id: str
    forecast_time_utc: datetime
    direction: str

    x_time_start_utc: datetime
    x_time_end_utc: datetime
    x_price_low: float
    x_price_high: float
    x_price_center: float

    v_time_start_utc: datetime
    v_time_end_utc: datetime
    v_price_low: float
    v_price_high: float
    v_price_center: float

    expected_x_to_v_pct: float
    v_probability: float
    source_horizon_minutes: int
    status: str
    note: str


class VForecastEngine:
    """
    V13 baseline V forecaster.

    IMPORTANT:
    - Consumes only already-frozen forecasts.
    - Never reads realized future bars.
    - V is a forecasted future zone/window, not a hindsight high/low.
    - expected_x_to_v_pct counts only the predicted move from X to V.
    - This is an uncalibrated baseline and must not be used as a live
      trading/ranking model until validated.
    """

    def _source_row(
        self,
        future: FutureDistributionForecast,
        x: XForecast,
    ) -> Optional[HorizonForecast]:
        rows = list(future.horizons)
        if not rows:
            return None

        exact = [
            row for row in rows
            if row.horizon_minutes == x.source_horizon_minutes
        ]
        if exact:
            return exact[0]

        if x.direction_after_x == "LONG":
            candidates = [
                row for row in rows
                if row.expected_terminal_return_pct >= 0
            ]
        else:
            candidates = [
                row for row in rows
                if row.expected_terminal_return_pct <= 0
            ]

        if not candidates:
            candidates = rows

        return max(
            candidates,
            key=lambda row: abs(row.expected_terminal_return_pct),
        )

    def forecast(
        self,
        future: FutureDistributionForecast,
        x: XForecast,
    ) -> Optional[VForecast]:
        row = self._source_row(future, x)
        if row is None:
            return None

        direction = x.direction_after_x
        x_center = float(x.x_price_center)

        median = float(row.predicted_price_median)
        low_edge = float(row.predicted_price_low)
        high_edge = float(row.predicted_price_high)

        # Baseline V is intentionally inside the favorable forecast edge,
        # rather than using the most extreme predicted price.
        if direction == "LONG":
            favorable_edge = max(median, high_edge)
            v_center = (median + favorable_edge) / 2.0
            if v_center < x_center:
                v_center = x_center
        else:
            favorable_edge = min(median, low_edge)
            v_center = (median + favorable_edge) / 2.0
            if v_center > x_center:
                v_center = x_center

        signed_x_to_v = (
            ((v_center / x_center) - 1.0) * 100.0
            if x_center > 0
            else 0.0
        )

        if direction == "LONG":
            expected_x_to_v = max(0.0, signed_x_to_v)
            direction_probability = float(row.probability_up)
        else:
            expected_x_to_v = max(0.0, -signed_x_to_v)
            direction_probability = float(row.probability_down)

        forecast_time = future.forecast_time_utc
        horizon_end = row.expected_end_time_utc

        # V must be after X. This timing split is only a baseline heuristic;
        # walk-forward calibration will replace it later.
        x_end = x.x_time_end_utc
        if horizon_end <= x_end:
            v_start = x_end + timedelta(minutes=1)
            v_end = v_start
        else:
            remaining = horizon_end - x_end
            v_start = x_end + remaining * 0.55
            v_end = horizon_end

        distribution_width = max(0.0, high_edge - low_edge)
        uncertainty = max(
            abs(v_center) * 0.0001,
            distribution_width * 0.12,
        )

        v_low = max(0.0, v_center - uncertainty)
        v_high = v_center + uncertainty

        x_probability = max(
            0.0, min(1.0, float(x.x_probability))
        )
        direction_probability = max(
            0.0, min(1.0, direction_probability)
        )

        # Diagnostic only; this is NOT a calibrated probability.
        v_probability = (
            0.5 * x_probability
            + 0.5 * direction_probability
        )

        return VForecast(
            asset_id=future.asset_id,
            forecast_time_utc=forecast_time,
            direction=direction,

            x_time_start_utc=x.x_time_start_utc,
            x_time_end_utc=x.x_time_end_utc,
            x_price_low=x.x_price_low,
            x_price_high=x.x_price_high,
            x_price_center=x.x_price_center,

            v_time_start_utc=v_start,
            v_time_end_utc=v_end,
            v_price_low=v_low,
            v_price_high=v_high,
            v_price_center=v_center,

            expected_x_to_v_pct=expected_x_to_v,
            v_probability=v_probability,
            source_horizon_minutes=row.horizon_minutes,
            status="baseline_uncalibrated",
            note=(
                "V is forecast only from information frozen at forecast time. "
                "No realized future high/low is used. V timing, price zone and "
                "probability are baseline heuristics pending walk-forward "
                "calibration."
            ),
        )
