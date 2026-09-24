import asyncio
import os
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .historical_store import HistoricalStore
from .massive_history_v13 import fetch_minute_bars
from .snapshot_engine import SnapshotEngine
from .replay_engine import ReplayEngine

UTC = timezone.utc
NY = ZoneInfo("America/New_York")


def market_time_to_utc(day: date, hour: int, minute: int) -> datetime:
    """Convert a New York market clock time to UTC using date-aware DST rules."""
    local = datetime(day.year, day.month, day.day, hour, minute, tzinfo=NY)
    return local.astimezone(UTC)


async def main():
    if not os.getenv("MASSIVE_API_KEY"):
        raise RuntimeError("MASSIVE_API_KEY is not configured")

    # Use the most recent completed weekday as a simple smoke-test target.
    day = date.today() - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)

    print("V13 real replay test")
    print("asset: AAPL")
    print("requested day:", day.isoformat())

    bars = await fetch_minute_bars("AAPL", day, day)

    if not bars:
        raise RuntimeError(
            "No minute bars returned. The selected weekday may have been a market holiday "
            "or the current Massive plan may not expose that historical interval."
        )

    store = HistoricalStore()
    store.extend(bars)
    snapshots = SnapshotEngine(store)

    # 14:00 New York market time on the historical date.
    cutoff = market_time_to_utc(day, 14, 0)
    snapshot = snapshots.build("AAPL", cutoff)

    # Hard anti-leakage assertions.
    assert all(b.timestamp_utc <= cutoff for b in snapshot.bars)
    assert all(b.received_at_utc <= cutoff for b in snapshot.bars)

    future_in_store = [b for b in store.all_bars("AAPL") if b.timestamp_utc > cutoff]

    if not future_in_store:
        raise RuntimeError(
            "The raw store contains no bars after the cutoff, so this test cannot prove "
            "that SnapshotEngine hid future rows."
        )

    # Replay three snapshots. The forecast function receives only Snapshot.
    replay = ReplayEngine(snapshots)

    def frozen_probe(s):
        latest = s.bars[-1] if s.bars else None
        return {
            "visible_rows": len(s.bars),
            "latest_bar_utc": latest.timestamp_utc.isoformat() if latest else None,
            "latest_price": latest.close if latest else None,
        }

    records = replay.run(
        "AAPL",
        market_time_to_utc(day, 13, 58),
        market_time_to_utc(day, 14, 0),
        1,
        frozen_probe,
        model_version="v13.0-real-replay-test",
    )

    print("downloaded rows:", len(bars))
    print("cutoff UTC:", cutoff.isoformat())
    print("visible at cutoff:", len(snapshot.bars))
    print("future rows present in raw store but hidden:", len(future_in_store))
    print("replay:")
    for record in records:
        print(record.forecast_time_utc.isoformat(), record.payload)

    print("PASS: real historical replay contains future raw data,")
    print("      while the 14:00 snapshot cannot access it.")


if __name__ == "__main__":
    asyncio.run(main())
