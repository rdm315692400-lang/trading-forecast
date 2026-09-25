from dataclasses import dataclass, asdict
from statistics import mean, median
from .historical_store import HistoricalStore
from .snapshot_engine import SnapshotEngine
from .forecast_pipeline import forecast_snapshot
from .validation import anti_leak
from .market_clock import market_time_to_utc, session_bounds_utc

@dataclass(frozen=True)
class Sample:
    asset_id: str
    market_day: str
    forecast_time_utc: str
    forecast_id: str
    direction: str
    horizon_minutes: int
    predicted_x_to_v_pct: float

    x_touched: bool
    v_touched_after_x: bool
    actual_x_to_v_pct: float | None
    error_pct_points: float | None
    direction_realized: bool | None

    post_x_mfe_pct: float | None
    post_x_mae_pct: float | None
    actual_remaining_potential_pct: float | None
    potential_error_pct_points: float | None

    predicted_x_price: float
    actual_x_price: float | None
    x_price_error_pct: float | None
    predicted_x_time_utc: str
    x_time_utc: str | None
    x_time_error_minutes: float | None

    predicted_v_price: float
    actual_v_price: float | None
    v_price_error_pct: float | None
    predicted_v_time_utc: str
    v_time_utc: str | None
    v_time_error_minutes: float | None

    def to_dict(self):
        return asdict(self)

def touches(b, lo, hi):
    return float(b.low) <= hi and float(b.high) >= lo

def touch_price(b, lo, hi):
    c = float(b.close)
    return c if lo <= c <= hi else (lo if c < lo else hi)

def pct_error(predicted, actual):
    if predicted is None or actual is None or predicted == 0:
        return None
    return abs(actual / predicted - 1) * 100

def minute_error(predicted_time, actual_time):
    if predicted_time is None or actual_time is None:
        return None
    return abs((actual_time - predicted_time).total_seconds()) / 60.0

def excursions(direction, entry, bars):
    if not bars or not entry:
        return None, None
    hi = max(float(b.high) for b in bars)
    lo = min(float(b.low) for b in bars)
    if direction == "LONG":
        return max(0.0, (hi / entry - 1) * 100), max(0.0, (1 - lo / entry) * 100)
    return max(0.0, (1 - lo / entry) * 100), max(0.0, (hi / entry - 1) * 100)

def evaluate(asset_id, market_day, bars, forecast_time):
    op, cl = session_bounds_utc(asset_id, market_day)
    regular = [b for b in bars if op <= b.timestamp_utc < cl]

    store = HistoricalStore()
    store.extend(regular)
    snap = SnapshotEngine(store).build(asset_id, forecast_time)
    if not snap.bars or not anti_leak(snap):
        return None

    fid, d, x, v = forecast_snapshot(snap)
    if not x or not v:
        return None
    if x.time_start_utc >= cl or v.time_start_utc >= cl:
        return None

    xe = min(x.time_end_utc, cl)
    vs = min(v.time_start_utc, cl)
    ve = min(v.time_end_utc, cl)

    later = [
        b for b in regular
        if b.received_at_utc > forecast_time and b.timestamp_utc < cl
    ]

    xb = next(
        (b for b in later
         if x.time_start_utc <= b.received_at_utc <= xe
         and touches(b, x.price_low, x.price_high)),
        None
    )
    xp = touch_price(xb, x.price_low, x.price_high) if xb else None

    after_x_to_close = [
        b for b in later
        if xb and b.received_at_utc > xb.received_at_utc and b.received_at_utc < cl
    ]
    after_for_v = [
        b for b in after_x_to_close
        if b.received_at_utc <= ve
    ]

    vb = next(
        (b for b in after_for_v
         if vs <= b.received_at_utc <= ve
         and touches(b, v.price_low, v.price_high)),
        None
    )
    vp = touch_price(vb, v.price_low, v.price_high) if vb else None

    actual = err = realized = None
    if xp and vp:
        signed = (vp / xp - 1) * 100
        actual = signed if v.direction == "LONG" else -signed
        err = abs(v.expected_x_to_v_pct - actual)
        realized = actual > 0

    # Remaining same-session opportunity after X, independent of whether V was touched.
    mfe, mae = excursions(v.direction, xp, after_x_to_close) if xp else (None, None)
    actual_remaining = mfe
    potential_error = (
        abs(v.expected_x_to_v_pct - actual_remaining)
        if actual_remaining is not None else None
    )

    predicted_x_time = x.time_start_utc + (x.time_end_utc - x.time_start_utc) / 2
    predicted_v_time = v.time_start_utc + (v.time_end_utc - v.time_start_utc) / 2

    return Sample(
        asset_id=asset_id,
        market_day=market_day.isoformat(),
        forecast_time_utc=forecast_time.isoformat(),
        forecast_id=fid,
        direction=v.direction,
        horizon_minutes=v.source_horizon_minutes,
        predicted_x_to_v_pct=v.expected_x_to_v_pct,

        x_touched=bool(xb),
        v_touched_after_x=bool(vb),
        actual_x_to_v_pct=actual,
        error_pct_points=err,
        direction_realized=realized,

        post_x_mfe_pct=mfe,
        post_x_mae_pct=mae,
        actual_remaining_potential_pct=actual_remaining,
        potential_error_pct_points=potential_error,

        predicted_x_price=x.price_center,
        actual_x_price=xp,
        x_price_error_pct=pct_error(x.price_center, xp),
        predicted_x_time_utc=predicted_x_time.isoformat(),
        x_time_utc=xb.received_at_utc.isoformat() if xb else None,
        x_time_error_minutes=minute_error(predicted_x_time, xb.received_at_utc) if xb else None,

        predicted_v_price=v.price_center,
        actual_v_price=vp,
        v_price_error_pct=pct_error(v.price_center, vp),
        predicted_v_time_utc=predicted_v_time.isoformat(),
        v_time_utc=vb.received_at_utc.isoformat() if vb else None,
        v_time_error_minutes=minute_error(predicted_v_time, vb.received_at_utc) if vb else None,
    )

def _values(attr, rows):
    return [getattr(s, attr) for s in rows if getattr(s, attr) is not None]

def _avg(attr, rows):
    vals = _values(attr, rows)
    return mean(vals) if vals else None

def _med(attr, rows):
    vals = _values(attr, rows)
    return median(vals) if vals else None

def summarize(samples):
    n = len(samples)
    xh = [s for s in samples if s.x_touched]
    vh = [s for s in samples if s.v_touched_after_x]
    completed = [s for s in samples if s.actual_x_to_v_pct is not None]

    by = {}
    for h in sorted(set(s.horizon_minutes for s in samples)):
        hs = [s for s in samples if s.horizon_minutes == h]
        hx = [s for s in hs if s.x_touched]
        hv = [s for s in hs if s.v_touched_after_x]
        hc = [s for s in hs if s.actual_x_to_v_pct is not None]
        by[str(h)] = {
            "samples": len(hs),
            "x_touch_rate": sum(s.x_touched for s in hs) / len(hs),
            "v_touch_after_x_rate": len(hv) / len(hx) if hx else None,
            "direction_realized_rate_on_completed_v": (
                sum(bool(s.direction_realized) for s in hc) / len(hc) if hc else None
            ),
            "mean_x_to_v_error_pct_points_on_completed_v": _avg("error_pct_points", hc),
            "median_x_price_error_pct_on_touched_x": _med("x_price_error_pct", hx),
            "median_x_time_error_minutes_on_touched_x": _med("x_time_error_minutes", hx),
            "median_v_price_error_pct_on_touched_v": _med("v_price_error_pct", hv),
            "median_v_time_error_minutes_on_touched_v": _med("v_time_error_minutes", hv),
            "median_actual_remaining_potential_pct_after_x": _med(
                "actual_remaining_potential_pct", hx
            ),
            "median_potential_error_pct_points_after_x": _med(
                "potential_error_pct_points", hx
            ),
        }

    return {
        "samples": n,
        "x_touch_rate": len(xh) / n if n else None,
        "v_touch_after_x_rate": len(vh) / len(xh) if xh else None,

        # This metric is conditional on V being touched; it is NOT overall accuracy.
        "direction_realized_rate_on_completed_v": (
            sum(bool(s.direction_realized) for s in completed) / len(completed)
            if completed else None
        ),
        "mean_x_to_v_error_pct_points_on_completed_v": _avg("error_pct_points", completed),

        "median_post_x_mfe_pct": _med("post_x_mfe_pct", xh),
        "median_post_x_mae_pct": _med("post_x_mae_pct", xh),

        "median_x_price_error_pct_on_touched_x": _med("x_price_error_pct", xh),
        "median_x_time_error_minutes_on_touched_x": _med("x_time_error_minutes", xh),
        "median_v_price_error_pct_on_touched_v": _med("v_price_error_pct", vh),
        "median_v_time_error_minutes_on_touched_v": _med("v_time_error_minutes", vh),

        "median_actual_remaining_potential_pct_after_x": _med(
            "actual_remaining_potential_pct", xh
        ),
        "median_potential_error_pct_points_after_x": _med(
            "potential_error_pct_points", xh
        ),

        "by_horizon": by,
        "calibrated": False,
        "status": "DIAGNOSTIC_ONLY",
        "notes": {
            "direction_metric_is_conditional": True,
            "actual_remaining_potential_definition": (
                "same-session MFE from actual X touch until session close"
            ),
            "time_error_reference": "midpoint of predicted X/V time window",
        },
    }

def run_cached_walk_forward(asset_id, days, forecast_times=("10:30", "12:30", "14:00")):
    samples = []
    for day in sorted(days):
        if day.weekday() >= 5:
            continue
        for hhmm in forecast_times:
            s = evaluate(
                asset_id,
                day,
                list(days[day]),
                market_time_to_utc(asset_id, day, hhmm),
            )
            if s:
                samples.append(s)

    return {
        "ok": True,
        "asset": asset_id,
        "summary": summarize(samples),
        "samples": [s.to_dict() for s in samples],
        "provider_called": False,
        # The caller may have loaded daily cache documents from Firestore before this function.
        "firestore_called_inside_walk_forward": False,
    }
