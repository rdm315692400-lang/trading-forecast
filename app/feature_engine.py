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


def _pct(a, b):
    return ((float(b) / float(a)) - 1.0) * 100.0 if float(a) else 0.0


def _ret(bars, i, n):
    if i < n:
        return 0.0
    return _pct(float(bars[i-n].close), float(bars[i].close))


def _abs_move(bars, i, n):
    start=max(1,i-n+1)
    moves=[abs(_pct(float(bars[j-1].close),float(bars[j].close))) for j in range(start,i+1) if float(bars[j-1].close)>0]
    return median(moves) if moves else 0.0


def _range_position(bars,i,n):
    window=bars[max(0,i-n+1):i+1]
    high=max(float(b.high) for b in window); low=min(float(b.low) for b in window)
    price=float(bars[i].close)
    rng=_pct(low,high) if low else 0.0
    pos=(price-low)/(high-low) if high>low else 0.5
    return rng,pos


def _structure_ratio(bars,i,n,field):
    vals=[float(getattr(b,field)) for b in bars[max(0,i-n+1):i+1]]
    if len(vals)<2:return 0.5
    return sum(1 for j in range(1,len(vals)) if vals[j]>vals[j-1])/(len(vals)-1)


def build_features(snapshot):
    bars=list(snapshot.bars)
    if len(bars)<61:
        return None
    i=len(bars)-1
    price=float(bars[i].close)
    r1,r5,r15,r30,r60=(_ret(bars,i,n) for n in (1,5,15,30,60))
    abs15,abs30,abs60=(_abs_move(bars,i,n) for n in (15,30,60))
    one=[_pct(float(bars[j-1].close),float(bars[j].close)) for j in range(max(1,i-29),i+1) if float(bars[j-1].close)>0]
    vol30=pstdev(one) if len(one)>1 else 0.0
    range15,_=_range_position(bars,i,15)
    range30,pos30=_range_position(bars,i,30)
    range60,pos60=_range_position(bars,i,60)
    vols=[float(b.volume) for b in bars[max(0,i-59):i+1]]
    recent=vols[-30:]; prior=vols[:-30]; base=median(prior) if prior else 0.0
    volume_ratio=median(recent)/base if base>0 and recent else 1.0
    visible=bars[:i+1]
    visible_open=float(visible[0].open); visible_high=max(float(b.high) for b in visible); visible_low=min(float(b.low) for b in visible)
    return MarketFeatures(
        price,r1,r5,r15,r30,r60,r5-(r30/6.0),abs15,abs30,abs60,vol30,
        range15,range30,range60,volume_ratio,pos30,pos60,
        _pct(visible_open,price) if visible_open else 0.0,
        _pct(visible_high,price) if visible_high else 0.0,
        _pct(visible_low,price) if visible_low else 0.0,
        _structure_ratio(bars,i,15,'high'),_structure_ratio(bars,i,15,'low')
    )
