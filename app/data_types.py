from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

@dataclass(frozen=True)
class Bar:
    asset_id: str
    timestamp_utc: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str
    received_at_utc: datetime

    def __post_init__(self):
        if self.timestamp_utc.tzinfo is None or self.received_at_utc.tzinfo is None:
            raise ValueError("V13 requires timezone-aware UTC timestamps")
        if self.timestamp_utc.utcoffset().total_seconds() != 0:
            raise ValueError("timestamp_utc must be UTC")
        if self.received_at_utc.utcoffset().total_seconds() != 0:
            raise ValueError("received_at_utc must be UTC")

    def to_dict(self):
        d = asdict(self)
        d["timestamp_utc"] = self.timestamp_utc.isoformat()
        d["received_at_utc"] = self.received_at_utc.isoformat()
        return d
