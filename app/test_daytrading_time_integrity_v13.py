from datetime import datetime, timedelta, timezone

from .data_types import Bar
from .historical_store import HistoricalStore
from .snapshot_engine import SnapshotEngine

UTC = timezone.utc


def _bar(minute: int, price: float) -> Bar:
    start = datetime(2026, 9, 23, 14, minute, tzinfo=UTC)
    return Bar(
        asset_id="AAPL",
        timestamp_utc=start,
        open=price,
        high=price + 0.20,
        low=price - 0.20,
        close=price + 0.10,
        volume=1000,
        source="synthetic",
        received_at_utc=start + timedelta(minutes=1),
    )


def run():
    store = HistoricalStore()
    store.extend([_bar(0, 100), _bar(1, 101), _bar(2, 102)])
    engine = SnapshotEngine(store)

    at_1400 = engine.build("AAPL", datetime(2026, 9, 23, 14, 0, tzinfo=UTC))
    at_1401 = engine.build("AAPL", datetime(2026, 9, 23, 14, 1, tzinfo=UTC))
    at_1402 = engine.build("AAPL", datetime(2026, 9, 23, 14, 2, tzinfo=UTC))

    assert len(at_1400.bars) == 0
    assert len(at_1401.bars) == 1
    assert at_1401.bars[-1].timestamp_utc.minute == 0
    assert len(at_1402.bars) == 2
    assert at_1402.bars[-1].timestamp_utc.minute == 1

    print("PASS: completed minute bars are visible only after their minute closes")
    print("14:00 visible:", len(at_1400.bars))
    print("14:01 visible:", len(at_1401.bars))
    print("14:02 visible:", len(at_1402.bars))


if __name__ == "__main__":
    run()
