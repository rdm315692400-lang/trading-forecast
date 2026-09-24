from dataclasses import dataclass
from datetime import datetime
from typing import Tuple
from .data_types import Bar
from .historical_store import HistoricalStore

@dataclass(frozen=True)
class Snapshot:
    asset_id: str
    snapshot_time_utc: datetime
    bars: Tuple[Bar, ...]

    @property
    def latest_price(self):
        return self.bars[-1].close if self.bars else None

class SnapshotEngine:
    def __init__(self, store: HistoricalStore):
        self.store = store

    def build(self, asset_id: str, snapshot_time_utc: datetime) -> Snapshot:
        if snapshot_time_utc.tzinfo is None or snapshot_time_utc.utcoffset().total_seconds() != 0:
            raise ValueError("snapshot_time_utc must be timezone-aware UTC")
        visible = tuple(
            bar for bar in self.store.all_bars(asset_id)
            if bar.timestamp_utc <= snapshot_time_utc
            and bar.received_at_utc <= snapshot_time_utc
        )
        for bar in visible:
            if bar.timestamp_utc > snapshot_time_utc or bar.received_at_utc > snapshot_time_utc:
                raise AssertionError("Future-data leakage detected")
        return Snapshot(asset_id, snapshot_time_utc, visible)
