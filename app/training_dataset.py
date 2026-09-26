from dataclasses import dataclass, asdict
from datetime import date, datetime, time, timedelta
from statistics import median, pstdev
from zoneinfo import ZoneInfo

from .asset_registry import get_asset
from .historical_cache import load_day


@dataclass(frozen=True)
class TrainingExample:
    asset_id: str
    market_day: str
    snapshot_time_utc: str
    reference_price: float

    return_1m_pct: float
    return_5m_pct: float
    return_15m_pct: float
    return_30m_pct: float
    return_60m_pct: float
    momentum_acceleration_pct: float

    realized_abs_15m_pct: float
    realized_abs_30m_pct: float
    realized_abs_60m_pct: float
    volatility_30m_pct: float

    range_15m_pct: float
    range_30m_pct: float
    range_60m_pct: float
    volume_ratio_30m: float
    position_in_30m_range: float
    position_in_60m_range: float

    distance_from_visible_open_pct: float
    distance_from_visible_high_pct: float
    distance_from_visible_low_pct: float
    higher_highs_15m: float
    higher_lows_15m: float

    horizon_minutes: int
    future_terminal_return_pct: float
    future_upside_reach_pct: float
    future_downside_reach_pct: float
    future_upside_peak_minute: int
    future_downside_peak_minute: int

    # Ordered path targets. X is constrained to occur at/before its direction's V.
    future_long_x_adverse_pct: float
    future_long_x_minute: int
    future_long_v_reach_pct: float
    future_long_v_minute: int
    future_long_x_to_v_pct: float
    future_short_x_adverse_pct: float
    future_short_x_minute: int
    future_short_v_reach_pct: float
    future_short_v_minute: int
    future_short_x_to_v_pct: float

    def to_dict(self):
        return asdict(self)


def _parse_hhmm(value):
    h, m = map(int, str(value).split(":"))
    return time(hour=h, minute=m)


def _regular_session_bars(asset, market_day, bars):
    """
    Keep only bars whose exchange-local timestamp is inside the asset's
    configured regular session. This prevents pre-market/after-hours bars
    from becoming forecast origins or future labels.
    """
    tz = ZoneInfo(asset.market_timezone)
    session_open = _parse_hhmm(asset.session_open)
    session_close = _parse_hhmm(asset.session_close)

    filtered = []
    for bar in bars:
        local_dt = bar.timestamp_utc.astimezone(tz)
        if local_dt.date().isoformat() != market_day:
            continue
        local_t = local_dt.time().replace(tzinfo=None)
        if session_open <= local_t < session_close:
            filtered.append(bar)
    return filtered


def _pct(a, b):
    return 100.0 * (b / a - 1.0) if a else 0.0


def _ret(bars, i, n):
    j = i - n
    return _pct(float(bars[j].close), float(bars[i].close)) if j >= 0 else 0.0


def _abs_move(bars, i, n):
    start = max(1, i - n + 1)
    moves = [
        abs(_pct(float(bars[j - 1].close), float(bars[j].close)))
        for j in range(start, i + 1)
        if float(bars[j - 1].close) > 0
    ]
    return median(moves) if moves else 0.0


def _range_position(bars, i, n):
    start = max(0, i - n + 1)
    window = bars[start:i + 1]
    high = max(float(b.high) for b in window)
    low = min(float(b.low) for b in window)
    price = float(bars[i].close)
    rng = _pct(low, high) if low else 0.0
    pos = (price - low) / (high - low) if high > low else 0.5
    return rng, pos


def _structure_ratio(bars, i, n, field):
    start = max(0, i - n + 1)
    vals = [float(getattr(b, field)) for b in bars[start:i + 1]]
    if len(vals) < 2:
        return 0.5
    wins = sum(1 for j in range(1, len(vals)) if vals[j] > vals[j - 1])
    return wins / (len(vals) - 1)


def _features(bars, i):
    # IMPORTANT: every slice ends at i. Nothing after snapshot t is visible here.
    price = float(bars[i].close)

    r1 = _ret(bars, i, 1)
    r5 = _ret(bars, i, 5)
    r15 = _ret(bars, i, 15)
    r30 = _ret(bars, i, 30)
    r60 = _ret(bars, i, 60)

    abs15 = _abs_move(bars, i, 15)
    abs30 = _abs_move(bars, i, 30)
    abs60 = _abs_move(bars, i, 60)

    start30 = max(1, i - 29)
    one_minute_returns = [
        _pct(float(bars[j - 1].close), float(bars[j].close))
        for j in range(start30, i + 1)
        if float(bars[j - 1].close) > 0
    ]
    vol30 = pstdev(one_minute_returns) if len(one_minute_returns) > 1 else 0.0

    range15, _ = _range_position(bars, i, 15)
    range30, pos30 = _range_position(bars, i, 30)
    range60, pos60 = _range_position(bars, i, 60)

    vol_start = max(0, i - 59)
    vols = [float(bars[j].volume) for j in range(vol_start, i + 1)]
    recent = vols[-30:]
    prior = vols[:-30]
    base = median(prior) if prior else 0.0
    volume_ratio = median(recent) / base if base > 0 and recent else 1.0

    # "Visible" means visible up to t only, never the completed day's future.
    visible = bars[:i + 1]
    visible_open = float(visible[0].open)
    visible_high = max(float(b.high) for b in visible)
    visible_low = min(float(b.low) for b in visible)

    return {
        "return_1m_pct": r1,
        "return_5m_pct": r5,
        "return_15m_pct": r15,
        "return_30m_pct": r30,
        "return_60m_pct": r60,
        "momentum_acceleration_pct": r5 - (r30 / 6.0),
        "realized_abs_15m_pct": abs15,
        "realized_abs_30m_pct": abs30,
        "realized_abs_60m_pct": abs60,
        "volatility_30m_pct": vol30,
        "range_15m_pct": range15,
        "range_30m_pct": range30,
        "range_60m_pct": range60,
        "volume_ratio_30m": volume_ratio,
        "position_in_30m_range": pos30,
        "position_in_60m_range": pos60,
        "distance_from_visible_open_pct": _pct(visible_open, price) if visible_open else 0.0,
        "distance_from_visible_high_pct": _pct(visible_high, price) if visible_high else 0.0,
        "distance_from_visible_low_pct": _pct(visible_low, price) if visible_low else 0.0,
        "higher_highs_15m": _structure_ratio(bars, i, 15, "high"),
        "higher_lows_15m": _structure_ratio(bars, i, 15, "low"),
    }


def _example(asset_id, market_day, bars, i, horizon_minutes):
    future_end = i + horizon_minutes
    if i < 60 or future_end >= len(bars):
        return None

    p0 = float(bars[i].close)
    if p0 <= 0:
        return None

    future = bars[i + 1:future_end + 1]
    if len(future) != horizon_minutes:
        return None

    f = _features(bars, i)
    terminal = _pct(p0, float(future[-1].close))

    upside_path = [max(0.0, _pct(p0, float(b.high))) for b in future]
    downside_path = [max(0.0, -_pct(p0, float(b.low))) for b in future]

    upside = max(upside_path) if upside_path else 0.0
    downside = max(downside_path) if downside_path else 0.0

    # First minute at which the future extreme is reached. These are LABELS only:
    # they are never part of the feature vector available at snapshot t.
    upside_peak_minute = (upside_path.index(upside) + 1) if upside_path else horizon_minutes
    downside_peak_minute = (downside_path.index(downside) + 1) if downside_path else horizon_minutes

    # Ordered t -> X -> V targets.
    # LONG: V is the future high; X is the lowest low observed no later than that V.
    long_v_idx = upside_path.index(upside) if upside_path else 0
    long_prefix = future[:long_v_idx + 1]
    long_x_bar = min(enumerate(long_prefix), key=lambda z: float(z[1].low))
    long_x_idx, long_x_obj = long_x_bar
    long_x_price = float(long_x_obj.low)
    long_v_price = float(future[long_v_idx].high)
    long_x_adverse = max(0.0, -_pct(p0, long_x_price))
    long_x_to_v = max(0.0, _pct(long_x_price, long_v_price)) if long_x_price > 0 else 0.0

    # SHORT: V is the future low; X is the highest high observed no later than that V.
    short_v_idx = downside_path.index(downside) if downside_path else 0
    short_prefix = future[:short_v_idx + 1]
    short_x_bar = max(enumerate(short_prefix), key=lambda z: float(z[1].high))
    short_x_idx, short_x_obj = short_x_bar
    short_x_price = float(short_x_obj.high)
    short_v_price = float(future[short_v_idx].low)
    short_x_adverse = max(0.0, _pct(p0, short_x_price))
    short_x_to_v = max(0.0, -_pct(short_x_price, short_v_price)) if short_x_price > 0 else 0.0

    return TrainingExample(
        asset_id=asset_id,
        market_day=market_day,
        snapshot_time_utc=bars[i].timestamp_utc.isoformat(),
        reference_price=p0,
        **f,
        horizon_minutes=horizon_minutes,
        future_terminal_return_pct=terminal,
        future_upside_reach_pct=upside,
        future_downside_reach_pct=downside,
        future_upside_peak_minute=upside_peak_minute,
        future_downside_peak_minute=downside_peak_minute,
        future_long_x_adverse_pct=long_x_adverse,
        future_long_x_minute=long_x_idx + 1,
        future_long_v_reach_pct=upside,
        future_long_v_minute=long_v_idx + 1,
        future_long_x_to_v_pct=long_x_to_v,
        future_short_x_adverse_pct=short_x_adverse,
        future_short_x_minute=short_x_idx + 1,
        future_short_v_reach_pct=downside,
        future_short_v_minute=short_v_idx + 1,
        future_short_x_to_v_pct=short_x_to_v,
    )


def build_training_dataset(
    asset_id,
    start_day,
    end_day,
    horizons=(15, 30, 60, 90, 120, 180),
    sample_every_minutes=15,
):
    """
    Stage 3 Final dataset builder with ordered future t->X->V path labels.

    Features use bars at or before snapshot t only.
    Labels use bars strictly after t within the same cached market day.
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
                bars = _regular_session_bars(asset, day_s, bars)
                if not bars:
                    missing_days.append(day_s)
                    day += timedelta(days=1)
                    continue

                used_days.append(day_s)

                for i in range(60, len(bars), step):
                    for h in horizons:
                        row = _example(asset_id, day_s, bars, i, h)
                        if row is not None:
                            rows.append(row)
        day += timedelta(days=1)

    by_horizon = {}
    for h in horizons:
        by_horizon[str(h)] = sum(1 for r in rows if r.horizon_minutes == h)

    return {
        "ok": True,
        "stage": "3E_DATASET",
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
        "leakage_rule": "regular_session_only_features_at_or_before_t_labels_and_peak_times_strictly_after_t_same_session",
        "rows": [r.to_dict() for r in rows],
    }


def chronological_split(dataset, train_fraction=0.70, validation_fraction=0.15):
    """Chronological day-level Train / Validation / untouched Holdout split."""
    rows = list(dataset.get("rows", []))
    days = sorted({r["market_day"] for r in rows})
    if len(days) < 3:
        raise ValueError("not_enough_market_days_for_split")

    n = len(days)
    train_end = max(1, int(n * float(train_fraction)))
    validation_end = max(
        train_end + 1,
        int(n * (float(train_fraction) + float(validation_fraction))),
    )
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
