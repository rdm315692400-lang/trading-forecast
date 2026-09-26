from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .asset_registry import get_asset
from .historical_cache import load_day


@dataclass(frozen=True)
class TrainingExample:
    asset_id: str
    market_day: str
    snapshot_time_utc: str
    reference_price: float
    return_5m_pct: float
    return_15m_pct: float
    return_30m_pct: float
    realized_abs_30m_pct: float
    horizon_minutes: int
    future_terminal_return_pct: float
    future_upside_reach_pct: float
    future_downside_reach_pct: float

    def to_dict(self):
        return asdict(self)


def _pct(a, b):
    return 100.0 * (b / a - 1.0) if a else 0.0


def _features(bars, i):
    p = float(bars[i].close)

    def ret(n):
        j = i - n
        return _pct(float(bars[j].close), p) if j >= 0 else 0.0

    start = max(1, i - 29)
    moves = [
        abs(_pct(float(bars[j - 1].close), float(bars[j].close)))
        for j in range(start, i + 1)
        if float(bars[j - 1].close) > 0
    ]
    vol = sum(moves) / len(moves) if moves else 0.0
    return ret(5), ret(15), ret(30), vol


def _example(asset_id, market_day, bars, i, horizon_minutes):
    future_end = i + horizon_minutes
    if i < 30 or future_end >= len(bars):
        return None

    p0 = float(bars[i].close)
    if p0 <= 0:
        return None

    future = bars[i + 1:future_end + 1]
    if len(future) != horizon_minutes:
        return None

    r5, r15, r30, vol = _features(bars, i)
    terminal = _pct(p0, float(future[-1].close))
    upside = max(0.0, max(_pct(p0, float(b.high)) for b in future))
    downside = max(0.0, max(-_pct(p0, float(b.low)) for b in future))

    return TrainingExample(
        asset_id=asset_id,
        market_day=market_day,
        snapshot_time_utc=bars[i].timestamp_utc.isoformat(),
        reference_price=p0,
        return_5m_pct=r5,
        return_15m_pct=r15,
        return_30m_pct=r30,
        realized_abs_30m_pct=vol,
        horizon_minutes=horizon_minutes,
        future_terminal_return_pct=terminal,
        future_upside_reach_pct=upside,
        future_downside_reach_pct=downside,
    )


def build_training_dataset(
    asset_id,
    start_day,
    end_day,
    horizons=(15, 30, 60, 90, 120, 180),
    sample_every_minutes=15,
):
    """
    Stage 3B dataset builder.

    Reads only already-cached daily bars. Each row separates:
      X/features = information available at snapshot time.
      y/labels   = bars strictly after snapshot time, within the same market day.

    No provider call and no Firestore write are performed here.
    """
    asset_id = asset_id.upper().strip()
    asset = get_asset(asset_id)
    if not asset:
        raise ValueError("unknown_asset")

    if isinstance(start_day, str):
        start_day = date.fromisoformat(start_day)
    if isinstance(end_day, str):
        end_day = date.fromisoformat(end_day)
    if end_day < start_day:
        raise ValueError("end_day_before_start_day")

    horizons = tuple(sorted({int(h) for h in horizons if int(h) > 0}))
    step = max(1, int(sample_every_minutes))

    rows = []
    used_days = []
    missing_days = []
    day = start_day

    while day <= end_day:
        if day.weekday() < 5:
            day_s = day.isoformat()
            bars = load_day(asset_id, day_s)
            if not bars:
                missing_days.append(day_s)
            else:
                bars = sorted(bars, key=lambda b: (b.timestamp_utc, b.received_at_utc))
                used_days.append(day_s)

                # Start only after enough past bars exist; space origins to avoid
                # treating every adjacent minute as an independent example.
                for i in range(30, len(bars), step):
                    for h in horizons:
                        row = _example(asset_id, day_s, bars, i, h)
                        if row is not None:
                            rows.append(row)
        day += timedelta(days=1)

    by_horizon = {}
    for h in horizons:
        count = sum(1 for r in rows if r.horizon_minutes == h)
        by_horizon[str(h)] = count

    return {
        "ok": True,
        "stage": "3B_DATASET",
        "asset": asset_id,
        "start_day": start_day.isoformat(),
        "end_day": end_day.isoformat(),
        "cached_days_used": used_days,
        "missing_weekdays": missing_days,
        "sample_every_minutes": step,
        "horizons": list(horizons),
        "examples": len(rows),
        "examples_by_horizon": by_horizon,
        "provider_called": False,
        "firestore_write_performed": False,
        "leakage_rule": "features_at_t_labels_strictly_after_t_same_market_day",
        "rows": [r.to_dict() for r in rows],
    }


def chronological_split(dataset, train_fraction=0.70, validation_fraction=0.15):
    """
    Chronological day-level split. Days never appear in more than one partition.
    The final partition is an untouched holdout.
    """
    rows = list(dataset.get("rows", []))
    days = sorted({r["market_day"] for r in rows})
    if len(days) < 3:
        raise ValueError("not_enough_market_days_for_split")

    n = len(days)
    train_end = max(1, int(n * float(train_fraction)))
    validation_end = max(train_end + 1, int(n * (float(train_fraction) + float(validation_fraction))))
    validation_end = min(validation_end, n - 1)

    train_days = set(days[:train_end])
    validation_days = set(days[train_end:validation_end])
    holdout_days = set(days[validation_end:])

    def select(day_set):
        return [r for r in rows if r["market_day"] in day_set]

    return {
        "train": select(train_days),
        "validation": select(validation_days),
        "holdout": select(holdout_days),
        "train_days": sorted(train_days),
        "validation_days": sorted(validation_days),
        "holdout_days": sorted(holdout_days),
    }
