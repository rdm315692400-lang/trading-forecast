from dataclasses import dataclass
from datetime import datetime
from typing import Tuple

@dataclass(frozen=True)
class Snapshot:
    asset_id: str
    snapshot_time_utc: datetime
    bars: Tuple
    latest_price: float | None

class SnapshotEngine:
    def __init__(self, store):
        self.store = store

    def build(self, asset_id: str, snapshot_time_utc: datetime):
        visible = [
            b for b in self.store.all_bars(asset_id)
            if b.timestamp_utc <= snapshot_time_utc
            and b.received_at_utc <= snapshot_time_utc
        ]
        latest = float(visible[-1].close) if visible else None
        return Snapshot(asset_id.upper(), snapshot_time_utc, tuple(visible), latest)
