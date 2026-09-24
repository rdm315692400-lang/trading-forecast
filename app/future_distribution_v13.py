from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from math import sqrt
from statistics import median
from typing import Dict, Iterable, List, Optional, Tuple

from .snapshot_engine import Snapshot

DEFAULT_HORIZONS = (15, 30, 60, 90, 120, 180)


@dataclass(frozen=True)
class HorizonForecast:
    horizon_minutes: int
    forecast_time_utc: datetime
    expected_end_time_utc: datetime
    reference_price: float

    # Forecast distribution, not a trading instruction.
    expected_terminal_return_pct: float
    expected_upside_reach_pct: float
    expected_downside_reach_pct: float

    probability_up: float
    probability_down: float
    probability_near_flat: float

    predicted_price_median: float
    predicted_price_low: float
    predicted_price_high: float

    sample_size: int
    method: str

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class FutureDistributionForecast:
    asset_id: str
    forecast_time_utc: datetime
    reference_price: float
    horizons: Dict[int, HorizonForecast]
    status: str
    note: str

    def to_dict(self):
        return {
            "asset_id": self.asset_id,
            "forecast_time_utc": self.forecast_time_utc.isoformat(),
            "reference_price": self.reference_price,
            "horizons": {k: v.to_dict() for k, v in self.horizons.items()},
            "status": self.status,
            "note": self.note,
        }


def _pct(a: float, b: float) -> float:
    if a <= 0:
        raise ValueError("price must be positive")
    return ((b / a) - 1.0) * 100.0


def _quantile(values: List[float], q: float) -> float:
    if not values:
        raise ValueError("empty values")
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(xs) - 1)
    frac = pos - lo
    return xs[lo] * (1.0 - frac) + xs[hi] * frac


class FutureDistributionEngine:
    """
    First V13 predictive layer.

    IMPORTANT:
    - Receives Snapshot only. It cannot inspect future bars.
    - This initial baseline forecasts a distribution from volatility/momentum
      visible at forecast time.
    - It intentionally does NOT invent X/V yet.
    - Later trained models can replace this baseline behind the same interface
      after walk-forward/holdout validation.
    """

    def __init__(self, min_returns: int = 30, flat_band_pct: float = 0.05):
        self.min_returns = min_returns
        self.flat_band_pct = flat_band_pct

    def forecast(
        self,
        snapshot: Snapshot,
        horizons: Iterable[int] = DEFAULT_HORIZONS,
    ) -> FutureDistributionForecast:
        bars = tuple(snapshot.bars)
        if len(bars) < self.min_returns + 1:
            return FutureDistributionForecast(
                asset_id=snapshot.asset_id,
                forecast_time_utc=snapshot.snapshot_time_utc,
                reference_price=float(snapshot.latest_price or 0.0),
                horizons={},
                status="insufficient_history",
                note="Not enough information visible at forecast time.",
            )

        closes = [float(b.close) for b in bars]
        reference = closes[-1]

        # Only past/visible one-bar returns.
        returns = [_pct(closes[i - 1], closes[i]) for i in range(1, len(closes))]
        recent = returns[-min(120, len(returns)):]

        # Robust center and dispersion from information already visible at t.
        center = median(recent)
        med = center
        abs_dev = [abs(x - med) for x in recent]
        robust_sigma = max(0.0001, 1.4826 * median(abs_dev))

        # Short visible momentum is deliberately weakly shrunk toward zero.
        short = returns[-min(15, len(returns)):]
        short_momentum = median(short) if short else 0.0
        one_min_drift = 0.25 * short_momentum + 0.75 * center

        out: Dict[int, HorizonForecast] = {}

        for h in sorted(set(int(x) for x in horizons if int(x) > 0)):
            # Baseline scaling. This is a forecast baseline to validate,
            # not a claim that market returns are normally distributed.
            expected = one_min_drift * h
            scale = robust_sigma * sqrt(h)

            low_return = expected - 1.2816 * scale
            high_return = expected + 1.2816 * scale

            # Smooth directional probabilities from expected move vs uncertainty.
            strength = expected / max(scale, 1e-9)
            p_up = 1.0 / (1.0 + pow(2.718281828, -strength))
            p_down = 1.0 - p_up

            # Explicit near-flat mass increases when expected movement is small.
            flat_ratio = max(
                0.0,
                1.0 - abs(expected) / max(self.flat_band_pct + scale, 1e-9),
            )
            p_flat = min(0.50, 0.35 * flat_ratio)
            directional_mass = 1.0 - p_flat
            p_up *= directional_mass
            p_down *= directional_mass

            predicted_median = reference * (1.0 + expected / 100.0)
            predicted_low = reference * (1.0 + low_return / 100.0)
            predicted_high = reference * (1.0 + high_return / 100.0)

            out[h] = HorizonForecast(
                horizon_minutes=h,
                forecast_time_utc=snapshot.snapshot_time_utc,
                expected_end_time_utc=snapshot.snapshot_time_utc + timedelta(minutes=h),
                reference_price=reference,
                expected_terminal_return_pct=expected,
                expected_upside_reach_pct=max(0.0, high_return),
                expected_downside_reach_pct=max(0.0, -low_return),
                probability_up=p_up,
                probability_down=p_down,
                probability_near_flat=p_flat,
                predicted_price_median=predicted_median,
                predicted_price_low=min(predicted_low, predicted_high),
                predicted_price_high=max(predicted_low, predicted_high),
                sample_size=len(recent),
                method="visible_only_robust_baseline_v13",
            )

        return FutureDistributionForecast(
            asset_id=snapshot.asset_id,
            forecast_time_utc=snapshot.snapshot_time_utc,
            reference_price=reference,
            horizons=out,
            status="ok",
            note=(
                "Baseline forecast using only information visible at forecast time. "
                "It must beat simple baselines out-of-sample before being used for X/V or ranking."
            ),
        )
