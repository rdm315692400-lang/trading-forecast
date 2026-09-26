import hashlib
from .future_distribution import FutureDistributionEngine
from .forecast_x import XForecastEngine
from .forecast_v import VForecastEngine

def forecast_snapshot(snapshot, fitted_model):
    """
    Stage 3F future-only pipeline:
    current snapshot -> learned future distribution -> future X -> future V.
    A fitted TRAIN-only model is mandatory.
    """
    distribution = FutureDistributionEngine(fitted_model=fitted_model).forecast(snapshot)
    x = XForecastEngine().forecast(distribution)
    v = VForecastEngine().forecast(distribution, x) if x else None

    forecast_id = hashlib.sha256(
        f"{snapshot.asset_id}|{snapshot.snapshot_time_utc.isoformat()}|stage3f".encode()
    ).hexdigest()[:24]

    return forecast_id, distribution, x, v
