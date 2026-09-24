from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

from .future_distribution_v13 import FutureDistributionForecast


@dataclass(frozen=True)
class XForecast:
    """
    Forecast of the FUTURE entry zone X.

    X is not the current price and is not a hindsight low/high.
    It is a probabilistic future time/price zone inferred from the
    already-frozen future-distribution forecast.
    """
    asset_id: str
    forecast_time_utc: datetime
    direction_after_x: str

    x_time_start_utc: datetime
    x_time_end_utc: datetime
    x_price_low: float
    x_price_high: float
    x_price_center: float

    expected_counter_move_pct: float
    x_probability: float
    path_type: str
    source_horizon_minutes: int
    status: str
    note: str

    def to_dict(self):
        d = asdict(self)
        for key in (
            "forecast_time_utc",
            "x_time_start_utc",
            "x_time_end_utc",
        ):
            d[key] = d[key].isoformat()
        return d


class XForecastEngine:
    """
    V13 first X-forecast layer.

    The engine consumes a FutureDistributionForecast only.
    Therefore it cannot inspect realized future bars.

    This is deliberately a baseline:
    - detects whether the frozen distribution suggests LONG or SHORT;
    - estimates whether an opposite move may occur before continuation;
    - returns an X time WINDOW and price RANGE;
    - never selects the realized future minimum/maximum.

    Historical validation must later calibrate these estimates.
    """

    def __init__(
        self,
        min_direction_probability: float = 0.50,
        min_counter_move_pct: float = 0.03,
    ):
        self.min_direction_probability = min_direction_probability
        self.min_counter_move_pct = min_counter_move_pct

    @staticmethod
    def _direction_score(forecast: FutureDistributionForecast) -> float:
        weighted = []
        for h, row in forecast.horizons.items():
            # Longer horizons receive mildly more weight without becoming
            # an arbitrary pass/fail rule.
            weight = max(1.0, h / 30.0)
            signed_prob = row.probability_up - row.probability_down
            weighted.append((weight, signed_prob))

        if not weighted:
            return 0.0

        total_weight = sum(w for w, _ in weighted)
        return sum(w * s for w, s in weighted) / total_weight

    @staticmethod
    def _choose_horizon(
        forecast: FutureDistributionForecast,
        direction: str,
    ):
        candidates = list(forecast.horizons.values())
        if direction == "LONG":
            candidates = [
                x for x in candidates
                if x.expected_terminal_return_pct > 0
            ]
        else:
            candidates = [
                x for x in candidates
                if x.expected_terminal_return_pct < 0
            ]

        if not candidates:
            return None

        # Choose the horizon with the largest predicted absolute terminal move.
        # This is still future forecast magnitude, not historical realized move.
        return max(
            candidates,
            key=lambda x: abs(x.expected_terminal_return_pct),
        )

    def forecast(
        self,
        future: FutureDistributionForecast,
    ) -> Optional[XForecast]:
        if future.status != "ok" or not future.horizons:
            return None

        score = self._direction_score(future)
        direction = "LONG" if score >= 0 else "SHORT"
        direction_probability = 0.5 + min(0.5, abs(score) / 2.0)

        source = self._choose_horizon(future, direction)
        if source is None:
            return None

        reference = float(future.reference_price)

        if direction == "LONG":
            # The lower edge of the frozen forecast distribution represents
            # possible adverse movement before a later LONG continuation.
            adverse_price = min(reference, source.predicted_price_low)
            counter_move_pct = max(
                0.0, ((reference - adverse_price) / reference) * 100.0
            )
            center = reference * (1.0 - counter_move_pct / 200.0)
        else:
            adverse_price = max(reference, source.predicted_price_high)
            counter_move_pct = max(
                0.0, ((adverse_price - reference) / reference) * 100.0
            )
            center = reference * (1.0 + counter_move_pct / 200.0)

        has_counter_move = counter_move_pct >= self.min_counter_move_pct

        if has_counter_move:
            # Initial timing hypothesis: X is expected in the early-middle
            # portion of the selected future horizon. It is a window, not a
            # claimed exact turning minute.
            start_minutes = max(1, round(source.horizon_minutes * 0.20))
            end_minutes = max(
                start_minutes + 1,
                round(source.horizon_minutes * 0.50),
            )
            path_type = "COUNTER_MOVE_THEN_CONTINUATION"

            half_width_pct = max(
                0.02,
                min(0.25, counter_move_pct * 0.25),
            )
        else:
            # Direct continuation: X is near the forecast origin but still
            # represented as a future window, never as "enter now".
            start_minutes = 1
            end_minutes = max(2, min(10, source.horizon_minutes // 4))
            path_type = "DIRECT_CONTINUATION"
            half_width_pct = 0.05

        x_low = center * (1.0 - half_width_pct / 100.0)
        x_high = center * (1.0 + half_width_pct / 100.0)

        # Baseline probability: directional support adjusted by how clearly
        # the distribution contains an adverse excursion. This is NOT yet a
        # calibrated trading probability.
        excursion_support = min(
            1.0,
            counter_move_pct / max(
                source.expected_upside_reach_pct
                + source.expected_downside_reach_pct,
                1e-9,
            ),
        )
        x_probability = max(
            0.0,
            min(
                1.0,
                0.75 * direction_probability
                + 0.25 * excursion_support,
            ),
        )

        return XForecast(
            asset_id=future.asset_id,
            forecast_time_utc=future.forecast_time_utc,
            direction_after_x=direction,
            x_time_start_utc=(
                future.forecast_time_utc + timedelta(minutes=start_minutes)
            ),
            x_time_end_utc=(
                future.forecast_time_utc + timedelta(minutes=end_minutes)
            ),
            x_price_low=min(x_low, x_high),
            x_price_high=max(x_low, x_high),
            x_price_center=center,
            expected_counter_move_pct=counter_move_pct,
            x_probability=x_probability,
            path_type=path_type,
            source_horizon_minutes=source.horizon_minutes,
            status="baseline_uncalibrated",
            note=(
                "Future X forecast from a frozen distribution only. "
                "No realized future extrema are used. Time/price/probability "
                "must be calibrated by walk-forward testing before live use."
            ),
        )
