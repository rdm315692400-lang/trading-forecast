from dataclasses import dataclass, asdict
from .settings import HORIZONS_MINUTES, MIN_VISIBLE_BARS
from .feature_engine import build_features

@dataclass(frozen=True)
class HorizonForecast:
    horizon_minutes: int
    expected_terminal_return_pct: float
    expected_upside_reach_pct: float
    expected_downside_reach_pct: float
    probability_up: float
    probability_down: float
    predicted_price_low: float
    predicted_price_high: float

@dataclass(frozen=True)
class FutureDistribution:
    asset_id: str
    forecast_time_utc: object
    reference_price: float
    features: dict
    horizons: dict
    status: str

    def to_dict(self):
        return {
            "asset_id":self.asset_id,
            "forecast_time_utc":self.forecast_time_utc.isoformat(),
            "reference_price":self.reference_price,
            "features":self.features,
            "horizons":{str(k):asdict(v) for k,v in self.horizons.items()},
            "status":self.status,
        }

class FutureDistributionEngine:
    """Stage 3A: history-derived empirical forecast; still uncalibrated."""
    def _pct(self, a, b):
        return 100.0 * (b / a - 1.0) if a else 0.0

    def _state(self, bars, i):
        p=float(bars[i].close)
        def r(n):
            return self._pct(float(bars[i-n].close),p) if i>=n else 0.0
        moves=[abs(self._pct(float(bars[j-1].close),float(bars[j].close)))
               for j in range(max(1,i-29),i+1) if float(bars[j-1].close)>0]
        return (r(5),r(15),r(30),sum(moves)/len(moves) if moves else 0.0)

    def _learn(self,bars,state_now,h):
        import math
        rows=[]
        last=len(bars)-h-1
        for i in range(30,last+1,5):
            s=self._state(bars,i)
            scales=(0.20,0.35,0.55,0.08)
            d=math.sqrt(sum(((a-b)/z)**2 for a,b,z in zip(state_now,s,scales)))
            p0=float(bars[i].close); future=bars[i+1:i+h+1]
            if p0<=0 or not future: continue
            terminal=self._pct(p0,float(future[-1].close))
            up=max(0.0,max(self._pct(p0,float(b.high)) for b in future))
            down=max(0.0,max(-self._pct(p0,float(b.low)) for b in future))
            rows.append((d,terminal,up,down))
        if len(rows)<12: return None
        rows.sort(key=lambda x:x[0])
        rows=rows[:min(80,max(12,int(math.sqrt(len(rows))*4)))]
        w=[math.exp(-min(12.0,x[0])) for x in rows]
        sw=sum(w)
        mean=lambda n:sum(x[n]*q for x,q in zip(rows,w))/sw if sw else 0.0
        uw=sum(q for x,q in zip(rows,w) if x[1]>0)
        dw=sum(q for x,q in zip(rows,w) if x[1]<0)
        return mean(1),mean(2),mean(3),uw/(uw+dw) if uw+dw else 0.5

    def forecast(self, snapshot):
        if len(snapshot.bars)<MIN_VISIBLE_BARS or not snapshot.latest_price:
            return FutureDistribution(snapshot.asset_id,snapshot.snapshot_time_utc,
                                      float(snapshot.latest_price or 0),{},{},"insufficient_history")
        f=build_features(snapshot)
        if f is None:
            return FutureDistribution(snapshot.asset_id,snapshot.snapshot_time_utc,
                                      snapshot.latest_price,{},{},"insufficient_history")
        bars=list(snapshot.bars); p=float(snapshot.latest_price)
        state_now=self._state(bars,len(bars)-1); horizons={}
        for h in HORIZONS_MINUTES:
            learned=self._learn(bars,state_now,int(h))
            if learned is None: continue
            terminal,up,down,p_up=learned
            horizons[h]=HorizonForecast(
                h,terminal,up,down,max(0.01,min(0.99,p_up)),
                max(0.01,min(0.99,1-p_up)),
                p*(1-down/100),p*(1+up/100))
        return FutureDistribution(snapshot.asset_id,snapshot.snapshot_time_utc,p,
                                  f.to_dict(),horizons,
                                  "ok" if horizons else "insufficient_empirical_history")
