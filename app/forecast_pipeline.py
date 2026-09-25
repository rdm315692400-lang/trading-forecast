import hashlib
from .future_distribution import FutureDistributionEngine
from .forecast_x import XForecastEngine
from .forecast_v import VForecastEngine

def forecast_snapshot(snapshot):
    distribution=FutureDistributionEngine().forecast(snapshot)
    x=XForecastEngine().forecast(distribution)
    v=VForecastEngine().forecast(distribution,x) if x else None
    forecast_id=hashlib.sha256(
        f"{snapshot.asset_id}|{snapshot.snapshot_time_utc.isoformat()}".encode()
    ).hexdigest()[:24]
    return forecast_id,distribution,x,v
