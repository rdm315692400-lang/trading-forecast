from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Dict, Iterable
from .historical_store import HistoricalStore
from .snapshot_engine import Snapshot

DEFAULT_HORIZONS = (15, 30, 60, 90, 120, 180)

@dataclass(frozen=True)
class HorizonTarget:
    horizon_minutes: int
    start_time_utc: datetime
    target_end_time_utc: datetime
    start_price: float
    end_price: float
    terminal_return_pct: float
    future_max_return_pct: float
    future_min_return_pct: float
    long_mfe_pct: float
    long_mae_pct: float
    short_mfe_pct: float
    short_mae_pct: float
    observed_future_bars: int
    def to_dict(self):
        return asdict(self)

def _pct(a, b):
    if a <= 0: raise ValueError("start price must be positive")
    return ((b / a) - 1.0) * 100.0

class FutureTargetEngine:
    """LABEL-ONLY: future bars create targets, never live model features."""
    def __init__(self, store: HistoricalStore):
        self.store = store

    def build(self, snapshot: Snapshot, horizons: Iterable[int] = DEFAULT_HORIZONS) -> Dict[int, HorizonTarget]:
        if not snapshot.bars or not snapshot.latest_price:
            return {}
        start=float(snapshot.latest_price)
        future=tuple(b for b in self.store.all_bars(snapshot.asset_id)
                     if b.timestamp_utc > snapshot.snapshot_time_utc)
        out={}
        for h in sorted(set(int(x) for x in horizons if int(x)>0)):
            requested=snapshot.snapshot_time_utc + timedelta(minutes=h)
            ends=[b for b in future if b.timestamp_utc >= requested]
            if not ends: continue
            end=ends[0]
            if end.timestamp_utc-requested > timedelta(minutes=2): continue
            path=tuple(b for b in future if b.timestamp_utc <= end.timestamp_utc)
            if not path: continue
            ep=float(end.close)
            hi=max(float(b.high) for b in path)
            lo=min(float(b.low) for b in path)
            terminal=_pct(start,ep); up=_pct(start,hi); down=_pct(start,lo)
            out[h]=HorizonTarget(
                h,snapshot.snapshot_time_utc,end.timestamp_utc,start,ep,
                terminal,up,down,max(0.0,up),max(0.0,-down),
                max(0.0,-down),max(0.0,up),len(path))
        return out
