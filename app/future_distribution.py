from dataclasses import dataclass, asdict
from .settings import HORIZONS_MINUTES
from .feature_engine import build_features
from .asset_registry import get_asset
from .historical_store import HistoricalStore
from .snapshot_engine import SnapshotEngine
from .market_clock import session_bounds_utc
from zoneinfo import ZoneInfo

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
    expected_upside_peak_minute: float
    expected_downside_peak_minute: float
    expected_long_x_adverse_pct: float
    expected_long_x_minute: float
    expected_long_v_reach_pct: float
    expected_long_v_minute: float
    expected_long_x_to_v_pct: float
    expected_short_x_adverse_pct: float
    expected_short_x_minute: float
    expected_short_v_reach_pct: float
    expected_short_v_minute: float
    expected_short_x_to_v_pct: float
    long_x_adverse_q25: float
    long_x_adverse_q75: float
    long_x_minute_q25: float
    long_x_minute_q75: float
    long_v_reach_q25: float
    long_v_reach_q75: float
    long_v_minute_q25: float
    long_v_minute_q75: float
    short_x_adverse_q25: float
    short_x_adverse_q75: float
    short_x_minute_q25: float
    short_x_minute_q75: float
    short_v_reach_q25: float
    short_v_reach_q75: float
    short_v_minute_q25: float
    short_v_minute_q75: float
    status: str = "uncalibrated"

@dataclass(frozen=True)
class FutureDistribution:
    asset_id: str
    forecast_time_utc: object
    reference_price: float
    features: dict
    horizons: dict
    status: str
    model_stage: str = "3F"

    def to_dict(self):
        return {
            "asset_id": self.asset_id,
            "forecast_time_utc": self.forecast_time_utc.isoformat(),
            "reference_price": self.reference_price,
            "features": self.features,
            "horizons": {str(k): asdict(v) for k, v in self.horizons.items()},
            "status": self.status,
            "model_stage": self.model_stage,
        }

class FutureDistributionEngine:
    """
    Stage 3F adapter.
    A fitted model must be supplied from the chronological TRAIN partition.
    The live/current snapshot contributes FEATURES ONLY; future labels never enter here.
    """
    def __init__(self, fitted_model=None):
        self.model = fitted_model

    def forecast(self, snapshot):
        p = float(snapshot.latest_price or 0.0)
        if p <= 0:
            return FutureDistribution(snapshot.asset_id, snapshot.snapshot_time_utc, p, {}, {},
                                      "invalid_reference_price")

        if self.model is None:
            return FutureDistribution(snapshot.asset_id, snapshot.snapshot_time_utc, p, {}, {},
                                      "model_not_supplied")

        # Match training exactly: live features use regular-session bars only.
        asset = get_asset(snapshot.asset_id)
        local_day = snapshot.snapshot_time_utc.astimezone(
            ZoneInfo(asset.market_timezone)
        ).date()
        op, cl = session_bounds_utc(snapshot.asset_id, local_day)
        regular = [b for b in snapshot.bars if op <= b.timestamp_utc < cl]
        rs = HistoricalStore()
        rs.extend(regular)
        feature_snapshot = SnapshotEngine(rs).build(snapshot.asset_id, snapshot.snapshot_time_utc)
        f = build_features(feature_snapshot)
        if f is None:
            return FutureDistribution(snapshot.asset_id, snapshot.snapshot_time_utc, p, {}, {},
                                      "insufficient_visible_features")

        features = f.to_dict()
        horizons = {}
        fitted = set(self.model.fitted_horizons())

        remaining_minutes = max(0.0, (cl - snapshot.snapshot_time_utc).total_seconds() / 60.0)

        for h in HORIZONS_MINUTES:
            h = int(h)
            if h not in fitted or h > remaining_minutes:
                continue
            pred = self.model.predict(features, h)
            if pred.status != "ok":
                continue

            up = max(0.0, float(pred.expected_upside_reach_pct))
            down = max(0.0, float(pred.expected_downside_reach_pct))
            horizons[h] = HorizonForecast(
                horizon_minutes=h,
                expected_terminal_return_pct=float(pred.expected_terminal_return_pct),
                expected_upside_reach_pct=up,
                expected_downside_reach_pct=down,
                probability_up=float(pred.probability_up),
                probability_down=float(pred.probability_down),
                predicted_price_low=p * (1.0 - down / 100.0),
                predicted_price_high=p * (1.0 + up / 100.0),
                expected_upside_peak_minute=float(pred.expected_upside_peak_minute),
                expected_downside_peak_minute=float(pred.expected_downside_peak_minute),
                expected_long_x_adverse_pct=float(pred.expected_long_x_adverse_pct),
                expected_long_x_minute=float(pred.expected_long_x_minute),
                expected_long_v_reach_pct=float(pred.expected_long_v_reach_pct),
                expected_long_v_minute=float(pred.expected_long_v_minute),
                expected_long_x_to_v_pct=float(pred.expected_long_x_to_v_pct),
                expected_short_x_adverse_pct=float(pred.expected_short_x_adverse_pct),
                expected_short_x_minute=float(pred.expected_short_x_minute),
                expected_short_v_reach_pct=float(pred.expected_short_v_reach_pct),
                expected_short_v_minute=float(pred.expected_short_v_minute),
                expected_short_x_to_v_pct=float(pred.expected_short_x_to_v_pct),
                long_x_adverse_q25=float(pred.long_x_adverse_q25),
                long_x_adverse_q75=float(pred.long_x_adverse_q75),
                long_x_minute_q25=float(pred.long_x_minute_q25),
                long_x_minute_q75=float(pred.long_x_minute_q75),
                long_v_reach_q25=float(pred.long_v_reach_q25),
                long_v_reach_q75=float(pred.long_v_reach_q75),
                long_v_minute_q25=float(pred.long_v_minute_q25),
                long_v_minute_q75=float(pred.long_v_minute_q75),
                short_x_adverse_q25=float(pred.short_x_adverse_q25),
                short_x_adverse_q75=float(pred.short_x_adverse_q75),
                short_x_minute_q25=float(pred.short_x_minute_q25),
                short_x_minute_q75=float(pred.short_x_minute_q75),
                short_v_reach_q25=float(pred.short_v_reach_q25),
                short_v_reach_q75=float(pred.short_v_reach_q75),
                short_v_minute_q25=float(pred.short_v_minute_q25),
                short_v_minute_q75=float(pred.short_v_minute_q75),
                status="validation_model_not_calibrated",
            )

        return FutureDistribution(
            snapshot.asset_id, snapshot.snapshot_time_utc, p, features, horizons,
            "ok" if horizons else "no_fitted_horizon"
        )
