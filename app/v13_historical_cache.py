from datetime import datetime, timezone
from typing import Iterable, List, Optional

from .data_types import Bar
from .storage import _client

COLLECTION = "v13_minute_cache"


def _doc_id(bar: Bar) -> str:
    stamp = bar.timestamp_utc.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{bar.asset_id.upper()}_{stamp}"


def _serialize(bar: Bar) -> dict:
    return {
        "asset_id": bar.asset_id.upper(),
        "timestamp_utc": bar.timestamp_utc.astimezone(timezone.utc).isoformat(),
        "open": float(bar.open),
        "high": float(bar.high),
        "low": float(bar.low),
        "close": float(bar.close),
        "volume": float(bar.volume),
        "source": bar.source,
        "received_at_utc": bar.received_at_utc.astimezone(timezone.utc).isoformat(),
        "cached_at_utc": datetime.now(timezone.utc).isoformat(),
    }


def _parse_dt(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _deserialize(data: dict) -> Bar:
    return Bar(
        asset_id=data["asset_id"],
        timestamp_utc=_parse_dt(data["timestamp_utc"]),
        open=float(data["open"]),
        high=float(data["high"]),
        low=float(data["low"]),
        close=float(data["close"]),
        volume=float(data.get("volume", 0.0)),
        source=data.get("source", "v13_cache"),
        received_at_utc=_parse_dt(data["received_at_utc"]),
    )


def enabled() -> bool:
    return _client() is not None


def save_bars(bars: Iterable[Bar]) -> int:
    """
    Upsert minute bars into Firestore.

    Deterministic document IDs make repeated downloads idempotent:
    the same asset/minute is replaced rather than duplicated.
    """
    db = _client()
    if db is None:
        return 0

    rows = list(bars)
    if not rows:
        return 0

    written = 0

    # Firestore batch limit is 500 writes. Stay conservatively below it.
    chunk_size = 400
    for start in range(0, len(rows), chunk_size):
        batch = db.batch()
        chunk = rows[start:start + chunk_size]

        for bar in chunk:
            ref = db.collection(COLLECTION).document(_doc_id(bar))
            batch.set(ref, _serialize(bar))
            written += 1

        batch.commit()

    return written


def load_bars(
    asset_id: str,
    start_utc: Optional[datetime] = None,
    end_utc: Optional[datetime] = None,
) -> List[Bar]:
    """
    Load cached bars only. This function never calls Massive.
    """
    db = _client()
    if db is None:
        return []

    asset_id = asset_id.upper().strip()

    query = (
        db.collection(COLLECTION)
        .where("asset_id", "==", asset_id)
    )

    docs = query.stream()
    result: List[Bar] = []

    for doc in docs:
        bar = _deserialize(doc.to_dict())

        if start_utc is not None:
            start = start_utc.astimezone(timezone.utc)
            if bar.timestamp_utc < start:
                continue

        if end_utc is not None:
            end = end_utc.astimezone(timezone.utc)
            if bar.timestamp_utc > end:
                continue

        result.append(bar)

    result.sort(key=lambda b: (b.timestamp_utc, b.received_at_utc))
    return result


def cache_status(asset_id: str) -> dict:
    bars = load_bars(asset_id)
    if not bars:
        return {
            "asset_id": asset_id.upper(),
            "cached_bars": 0,
            "first_bar_utc": None,
            "last_bar_utc": None,
        }

    return {
        "asset_id": asset_id.upper(),
        "cached_bars": len(bars),
        "first_bar_utc": bars[0].timestamp_utc.isoformat(),
        "last_bar_utc": bars[-1].timestamp_utc.isoformat(),
    }
