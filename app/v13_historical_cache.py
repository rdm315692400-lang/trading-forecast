from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable, List, Optional
from zoneinfo import ZoneInfo

from .data_types import Bar
from .storage import _client

COLLECTION = "v13_daily_bar_cache"

# Process-local hot cache. Firestore is persistence, not the per-request data path.
_MEMORY = {}


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _day_key(asset_id: str, market_day: str) -> str:
    return f"{asset_id.upper()}_{market_day}"


def _serialize_bar(bar: Bar) -> dict:
    return {
        "t": _utc(bar.timestamp_utc).isoformat(),
        "o": float(bar.open),
        "h": float(bar.high),
        "l": float(bar.low),
        "c": float(bar.close),
        "v": float(bar.volume),
        "s": bar.source,
        "r": _utc(bar.received_at_utc).isoformat(),
    }


def _parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return _utc(dt)


def _deserialize_bar(asset_id: str, row: dict) -> Bar:
    return Bar(
        asset_id=asset_id.upper(),
        timestamp_utc=_parse_dt(row["t"]),
        open=float(row["o"]),
        high=float(row["h"]),
        low=float(row["l"]),
        close=float(row["c"]),
        volume=float(row.get("v", 0.0)),
        source=row.get("s", "v13_daily_cache"),
        received_at_utc=_parse_dt(row["r"]),
    )


def _market_day(bar: Bar, timezone_name: str) -> str:
    return bar.timestamp_utc.astimezone(
        ZoneInfo(timezone_name)
    ).date().isoformat()


def enabled() -> bool:
    return _client() is not None


def save_bars(
    bars: Iterable[Bar],
    market_timezone: str = "America/New_York",
) -> int:
    """
    Persist bars as ONE Firestore document per asset + market day.

    A normal US regular session therefore uses one document instead of
    roughly 390 minute documents.

    Returns number of daily documents written, not number of bars.
    """
    db = _client()
    if db is None:
        return 0

    grouped = defaultdict(list)
    for bar in bars:
        day = _market_day(bar, market_timezone)
        grouped[(bar.asset_id.upper(), day)].append(bar)

    documents_written = 0

    for (asset_id, day), day_bars in grouped.items():
        day_bars.sort(
            key=lambda b: (b.timestamp_utc, b.received_at_utc)
        )

        # Deduplicate by bar start time before persistence.
        deduped = {}
        for bar in day_bars:
            deduped[_utc(bar.timestamp_utc).isoformat()] = bar
        day_bars = list(deduped.values())
        day_bars.sort(key=lambda b: b.timestamp_utc)

        payload = {
            "asset_id": asset_id,
            "market_day": day,
            "market_timezone": market_timezone,
            "bar_count": len(day_bars),
            "bars": [_serialize_bar(b) for b in day_bars],
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "schema_version": 2,
        }

        doc_id = _day_key(asset_id, day)
        db.collection(COLLECTION).document(doc_id).set(payload)

        _MEMORY[doc_id] = day_bars
        documents_written += 1

    return documents_written


def load_day(
    asset_id: str,
    market_day: str,
) -> List[Bar]:
    """
    Load one asset/day. Memory first, Firestore second.
    At most one Firestore document read for a cache miss.
    """
    asset_id = asset_id.upper().strip()
    doc_id = _day_key(asset_id, market_day)

    if doc_id in _MEMORY:
        return list(_MEMORY[doc_id])

    db = _client()
    if db is None:
        return []

    snap = db.collection(COLLECTION).document(doc_id).get()
    if not snap.exists:
        return []

    data = snap.to_dict()
    bars = [
        _deserialize_bar(asset_id, row)
        for row in data.get("bars", [])
    ]
    bars.sort(key=lambda b: (b.timestamp_utc, b.received_at_utc))
    _MEMORY[doc_id] = bars
    return list(bars)


def load_bars(
    asset_id: str,
    start_utc: Optional[datetime] = None,
    end_utc: Optional[datetime] = None,
    market_days: Optional[Iterable[str]] = None,
) -> List[Bar]:
    """
    Load selected daily documents.

    IMPORTANT: callers should pass market_days whenever possible.
    This deliberately avoids a Firestore query that scans many minute docs.
    """
    asset_id = asset_id.upper().strip()

    if market_days is None:
        # No broad Firestore query here. It prevents accidental read explosions.
        # Return only matching days already present in process memory.
        prefix = f"{asset_id}_"
        keys = sorted(k for k in _MEMORY if k.startswith(prefix))
        bars = [bar for k in keys for bar in _MEMORY[k]]
    else:
        bars = []
        for day in market_days:
            bars.extend(load_day(asset_id, str(day)))

    if start_utc is not None:
        start = _utc(start_utc)
        bars = [b for b in bars if b.timestamp_utc >= start]

    if end_utc is not None:
        end = _utc(end_utc)
        bars = [b for b in bars if b.timestamp_utc <= end]

    bars.sort(key=lambda b: (b.timestamp_utc, b.received_at_utc))
    return bars


def cache_status(
    asset_id: str,
    market_day: Optional[str] = None,
) -> dict:
    """
    Cheap status.

    Without market_day: memory-only, ZERO Firestore reads.
    With market_day: at most ONE Firestore document read.
    """
    asset_id = asset_id.upper().strip()

    if market_day:
        bars = load_day(asset_id, market_day)
        return {
            "asset_id": asset_id,
            "market_day": market_day,
            "cached_bars": len(bars),
            "source": (
                "memory_or_single_daily_document"
                if bars else "not_found"
            ),
            "first_bar_utc": (
                bars[0].timestamp_utc.isoformat() if bars else None
            ),
            "last_bar_utc": (
                bars[-1].timestamp_utc.isoformat() if bars else None
            ),
        }

    prefix = f"{asset_id}_"
    keys = sorted(k for k in _MEMORY if k.startswith(prefix))
    bars = [bar for k in keys for bar in _MEMORY[k]]

    return {
        "asset_id": asset_id,
        "cached_days_in_memory": len(keys),
        "cached_bars_in_memory": len(bars),
        "firestore_reads_performed": 0,
        "first_bar_utc": (
            bars[0].timestamp_utc.isoformat() if bars else None
        ),
        "last_bar_utc": (
            bars[-1].timestamp_utc.isoformat() if bars else None
        ),
    }


def clear_memory_cache() -> None:
    _MEMORY.clear()
