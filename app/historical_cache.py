from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
from .data_types import Bar
from .storage import client
from .settings import CACHE_COLLECTION

_MEMORY = {}

def _key(asset_id, day):
    return f"{asset_id.upper()}_{day}"

def _serialize(b):
    return {
        "t": b.timestamp_utc.isoformat(), "o": b.open, "h": b.high,
        "l": b.low, "c": b.close, "v": b.volume,
        "r": b.received_at_utc.isoformat()
    }

def _deserialize(asset_id, row):
    return Bar(
        asset_id.upper(), datetime.fromisoformat(row["t"]),
        float(row["o"]), float(row["h"]), float(row["l"]), float(row["c"]),
        float(row.get("v",0)), "cache", datetime.fromisoformat(row["r"])
    )

def save_bars(bars, market_timezone):
    grouped = defaultdict(list)
    tz = ZoneInfo(market_timezone)
    for b in bars:
        day = b.timestamp_utc.astimezone(tz).date().isoformat()
        grouped[(b.asset_id.upper(), day)].append(b)
    db = client()
    for (asset_id, day), rows in grouped.items():
        dedup = {b.timestamp_utc.isoformat(): b for b in rows}
        rows = sorted(dedup.values(), key=lambda b:b.timestamp_utc)
        _MEMORY[_key(asset_id,day)] = rows
        if db is not None:
            db.collection(CACHE_COLLECTION).document(_key(asset_id,day)).set({
                "asset_id": asset_id, "market_day": day,
                "market_timezone": market_timezone,
                "bar_count": len(rows), "bars": [_serialize(b) for b in rows],
                "schema_version": 1,
            })
    return len(grouped)

def load_day(asset_id, market_day):
    k = _key(asset_id, market_day)
    if k in _MEMORY:
        return list(_MEMORY[k])
    db = client()
    if db is None:
        return []
    snap = db.collection(CACHE_COLLECTION).document(k).get()
    if not snap.exists:
        return []
    rows = [_deserialize(asset_id, x) for x in snap.to_dict().get("bars",[])]
    rows.sort(key=lambda b:(b.timestamp_utc,b.received_at_utc))
    _MEMORY[k] = rows
    return list(rows)

def memory_status(asset_id):
    prefix = asset_id.upper() + "_"
    keys = [k for k in _MEMORY if k.startswith(prefix)]
    return {
        "asset": asset_id.upper(),
        "memory_days": len(keys),
        "memory_bars": sum(len(_MEMORY[k]) for k in keys),
        "firestore_reads_performed": 0,
    }
