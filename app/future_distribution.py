from dataclasses import dataclass, asdict
from .settings import HORIZONS_MINUTES, MIN_VISIBLE_BARS
from .feature_engine import build_features

@dataclass(frozen=True)
class HorizonForecast:
    horizon_minutes: int
    expected_terminal_return_pct: float
    expected_upside_reach_pct: float
    expected_downside_reach_pct: float
    probability_up: float
    probability_down: float
    predicted_price_low: float
    predicted_price_high: float

@dataclass(frozen=True)
class FutureDistribution:
    asset_id: str
    forecast_time_utc: object
    reference_price: float
    features: dict
    horizons: dict
    status: str

    def to_dict(self):
        return {
            "asset_id":self.asset_id,
            "forecast_time_utc":self.forecast_time_utc.isoformat(),
            "reference_price":self.reference_price,
            "features":self.features,
            "horizons":{str(k):asdict(v) for k,v in self.horizons.items()},
            "status":self.status,
        }

class FutureDistributionEngine:
    """Transparent research baseline. Historical calibration replaces these coefficients later."""
    def forecast(self, snapshot):
        if len(snapshot.bars) < MIN_VISIBLE_BARS or not snapshot.latest_price:
            return FutureDistribution(
                snapshot.asset_id, snapshot.snapshot_time_utc,
                float(snapshot.latest_price or 0), {}, {}, "insufficient_history"
            )
        f = build_features(snapshot)
        if f is None:
            return FutureDistribution(snapshot.asset_id,snapshot.snapshot_time_utc,
                                      snapshot.latest_price,{},{},"insufficient_history")
        p = float(snapshot.latest_price)
        # Current state drives direction. Volatility scales magnitude.
        impulse = 0.50*f.return_5m_pct + 0.30*f.return_15m_pct + 0.20*f.return_30m_pct
        vol = max(0.02, f.realized_abs_30m_pct)
        horizons = {}
        for h in HORIZONS_MINUTES:
            scale = (h/30.0) ** 0.5
            terminal = impulse * min(1.8, scale)
            reach = max(abs(terminal), vol*scale*4.0)
            directional = max(-1.0, min(1.0, impulse/max(reach,1e-9)))
            p_up = 0.5 + 0.25*directional
            horizons[h] = HorizonForecast(
                h, terminal, reach, reach,
                max(0.01,min(0.99,p_up)), max(0.01,min(0.99,1-p_up)),
                p*(1-reach/100), p*(1+reach/100)
            )
        return FutureDistribution(
            snapshot.asset_id,snapshot.snapshot_time_utc,p,f.to_dict(),horizons,"ok"
        )
