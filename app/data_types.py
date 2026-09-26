from dataclasses import dataclass
from datetime import datetime

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
            raise ValueError("Bar timestamps must be timezone-aware")
        if self.high < self.low:
            raise ValueError("high must be >= low")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("OHLC must be positive")
