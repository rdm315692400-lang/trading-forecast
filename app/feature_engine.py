from dataclasses import dataclass, asdict
from statistics import median

@dataclass(frozen=True)
class MarketFeatures:
    latest_price: float
    return_5m_pct: float
    return_15m_pct: float
    return_30m_pct: float
    realized_abs_30m_pct: float
    range_30m_pct: float
    volume_ratio_30m: float
    position_in_30m_range: float

    def to_dict(self):
        return asdict(self)

def _ret(closes, n):
    if len(closes) <= n or closes[-n-1] == 0:
        return 0.0
    return (closes[-1] / closes[-n-1] - 1.0) * 100.0

def build_features(snapshot):
    bars = list(snapshot.bars)
    if len(bars) < 31:
        return None
    closes = [float(b.close) for b in bars]
    recent = bars[-30:]
    changes = [
        abs((closes[i]/closes[i-1]-1)*100)
        for i in range(max(1,len(closes)-30), len(closes))
        if closes[i-1]
    ]
    high = max(float(b.high) for b in recent)
    low = min(float(b.low) for b in recent)
    price = closes[-1]
    rng = ((high/low)-1)*100 if low else 0.0
    pos = (price-low)/(high-low) if high>low else 0.5
    vols = [float(b.volume) for b in bars[-60:]]
    base = median(vols[:-30]) if len(vols)>30 and vols[:-30] else 0.0
    vr = (median(vols[-30:])/base) if base>0 else 1.0
    return MarketFeatures(
        price, _ret(closes,5), _ret(closes,15), _ret(closes,30),
        median(changes) if changes else 0.0, rng, vr, pos
    )
