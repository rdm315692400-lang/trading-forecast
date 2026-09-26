from dataclasses import dataclass, asdict
from statistics import median, pstdev


@dataclass(frozen=True)
class MarketFeatures:
    latest_price: float
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

    def to_dict(self):
        return asdict(self)


def _ret(closes, n):
    if len(closes) <= n or closes[-n-1] == 0:
        return 0.0
    return (closes[-1] / closes[-n-1] - 1.0) * 100.0


def _abs_move(closes, n):
    start = max(1, len(closes) - n)
    vals = [
        abs((closes[i] / closes[i-1] - 1.0) * 100.0)
        for i in range(start, len(closes))
        if closes[i-1]
    ]
    return median(vals) if vals else 0.0


def _range_pct(bars):
    if not bars:
        return 0.0, 0.5
    high = max(float(b.high) for b in bars)
    low = min(float(b.low) for b in bars)
    price = float(bars[-1].close)
    rng = ((high / low) - 1.0) * 100.0 if low else 0.0
    pos = (price - low) / (high - low) if high > low else 0.5
    return rng, pos


def _structure_ratio(bars, field):
    if len(bars) < 3:
        return 0.5
    vals = [float(getattr(b, field)) for b in bars]
    comparisons = [1.0 if vals[i] > vals[i-1] else 0.0 for i in range(1, len(vals))]
    return sum(comparisons) / len(comparisons) if comparisons else 0.5


def build_features(snapshot):
    bars = list(snapshot.bars)
    if len(bars) < 61:
        return None

    closes = [float(b.close) for b in bars]
    price = closes[-1]

    r15, _ = _range_pct(bars[-15:])
    r30, p30 = _range_pct(bars[-30:])
    r60, p60 = _range_pct(bars[-60:])

    one_minute_returns = [
        ((closes[i] / closes[i-1]) - 1.0) * 100.0
        for i in range(max(1, len(closes)-30), len(closes))
        if closes[i-1]
    ]
    vol30 = pstdev(one_minute_returns) if len(one_minute_returns) > 1 else 0.0

    vols = [float(b.volume) for b in bars[-60:]]
    base = median(vols[:-30]) if len(vols) > 30 and vols[:-30] else 0.0
    volume_ratio = median(vols[-30:]) / base if base > 0 else 1.0

    visible_open = float(bars[0].open)
    visible_high = max(float(b.high) for b in bars)
    visible_low = min(float(b.low) for b in bars)

    return_5 = _ret(closes, 5)
    return_15 = _ret(closes, 15)
    return_30 = _ret(closes, 30)

    return MarketFeatures(
        latest_price=price,
        return_1m_pct=_ret(closes, 1),
        return_5m_pct=return_5,
        return_15m_pct=return_15,
        return_30m_pct=return_30,
        return_60m_pct=_ret(closes, 60),
        momentum_acceleration_pct=return_5 - (return_30 / 6.0),
        realized_abs_15m_pct=_abs_move(closes, 15),
        realized_abs_30m_pct=_abs_move(closes, 30),
        realized_abs_60m_pct=_abs_move(closes, 60),
        volatility_30m_pct=vol30,
        range_15m_pct=r15,
        range_30m_pct=r30,
        range_60m_pct=r60,
        volume_ratio_30m=volume_ratio,
        position_in_30m_range=p30,
        position_in_60m_range=p60,
        distance_from_visible_open_pct=((price / visible_open) - 1.0) * 100.0 if visible_open else 0.0,
        distance_from_visible_high_pct=((price / visible_high) - 1.0) * 100.0 if visible_high else 0.0,
        distance_from_visible_low_pct=((price / visible_low) - 1.0) * 100.0 if visible_low else 0.0,
        higher_highs_15m=_structure_ratio(bars[-15:], "high"),
        higher_lows_15m=_structure_ratio(bars[-15:], "low"),
    )
