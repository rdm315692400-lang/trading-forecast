from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, List, Any
from .snapshot_engine import SnapshotEngine, Snapshot

@dataclass(frozen=True)
class FrozenForecast:
    asset_id: str
    forecast_time_utc: datetime
    model_version: str
    payload: Any

class ReplayEngine:
    """Replays historical time sequentially without exposing future store data."""
    def __init__(self, snapshot_engine: SnapshotEngine):
        self.snapshot_engine = snapshot_engine

    def run(self, asset_id: str, start_utc: datetime, end_utc: datetime,
            step_minutes: int, forecast_fn: Callable[[Snapshot], Any],
            model_version: str = "v13.0-foundation") -> List[FrozenForecast]:
        if step_minutes <= 0:
            raise ValueError("step_minutes must be positive")
        out = []
        t = start_utc
        while t <= end_utc:
            snapshot = self.snapshot_engine.build(asset_id, t)
            payload = forecast_fn(snapshot)
            out.append(FrozenForecast(asset_id, t, model_version, payload))
            t += timedelta(minutes=step_minutes)
        return out
