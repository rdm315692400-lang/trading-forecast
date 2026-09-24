from datetime import datetime, timezone
from data_types import Bar
from historical_store import HistoricalStore
from snapshot_engine import SnapshotEngine
from replay_engine import ReplayEngine

UTC = timezone.utc

def dt(hour, minute):
    return datetime(2026, 9, 1, hour, minute, tzinfo=UTC)

store = HistoricalStore()

# Available normally.
store.append(Bar("AAPL", dt(13, 58), 100, 101, 99, 100.5, 1000, "test", dt(13, 58)))
store.append(Bar("AAPL", dt(13, 59), 100.5, 101, 100, 100.8, 1200, "test", dt(13, 59)))

# Timestamp is 14:00, but provider did not make it available until 14:02.
store.append(Bar("AAPL", dt(14, 0), 100.8, 102, 100.7, 101.7, 1500, "test", dt(14, 2)))

# Truly future bar.
store.append(Bar("AAPL", dt(14, 1), 101.7, 103, 101.5, 102.8, 1800, "test", dt(14, 1)))

engine = SnapshotEngine(store)

s1400 = engine.build("AAPL", dt(14, 0))
assert [b.timestamp_utc for b in s1400.bars] == [dt(13, 58), dt(13, 59)]
assert s1400.latest_price == 100.8

s1401 = engine.build("AAPL", dt(14, 1))
assert [b.timestamp_utc for b in s1401.bars] == [dt(13, 58), dt(13, 59), dt(14, 1)]

s1402 = engine.build("AAPL", dt(14, 2))
assert [b.timestamp_utc for b in s1402.bars] == [dt(13, 58), dt(13, 59), dt(14, 0), dt(14, 1)]

# Replay forecast function can see only the frozen snapshot.
def forecast(snapshot):
    return {
        "rows_visible": len(snapshot.bars),
        "latest_price": snapshot.latest_price,
    }

replay = ReplayEngine(engine)
records = replay.run("AAPL", dt(14, 0), dt(14, 2), 1, forecast)

assert records[0].payload["rows_visible"] == 2
assert records[1].payload["rows_visible"] == 3
assert records[2].payload["rows_visible"] == 4

print("PASS: V13.0 future-leakage test")
print("14:00 visible rows:", records[0].payload["rows_visible"])
print("14:01 visible rows:", records[1].payload["rows_visible"])
print("14:02 visible rows:", records[2].payload["rows_visible"])
