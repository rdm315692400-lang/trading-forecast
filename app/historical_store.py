from typing import Dict, List
from data_types import Bar

class HistoricalStore:
    """
    Append-only in-memory foundation.
    Persistent storage can be attached later without changing the replay contract.
    """
    def __init__(self):
        self._bars: Dict[str, List[Bar]] = {}

    def append(self, bar: Bar) -> None:
        bucket = self._bars.setdefault(bar.asset_id, [])
        if bucket and bar.timestamp_utc < bucket[-1].timestamp_utc:
            raise ValueError("Bars must be appended chronologically")
        bucket.append(bar)

    def extend(self, bars) -> None:
        for bar in bars:
            self.append(bar)

    def all_bars(self, asset_id: str):
        return tuple(self._bars.get(asset_id, []))
