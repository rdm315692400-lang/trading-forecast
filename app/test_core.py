from datetime import datetime,timedelta,timezone
from .data_types import Bar
from .historical_store import HistoricalStore
from .snapshot_engine import SnapshotEngine
from .validation import anti_leak

def test_no_future_leak():
    t=datetime(2026,1,2,15,0,tzinfo=timezone.utc)
    bars=[
        Bar("AAPL",t-timedelta(minutes=1),100,101,99,100,1,"test",t),
        Bar("AAPL",t,100,102,99,101,1,"test",t+timedelta(minutes=1)),
    ]
    store=HistoricalStore();store.extend(bars)
    snapshot=SnapshotEngine(store).build("AAPL",t)
    assert len(snapshot.bars)==1
    assert anti_leak(snapshot)
