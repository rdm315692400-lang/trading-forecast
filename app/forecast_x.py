from dataclasses import dataclass, asdict
from datetime import timedelta

@dataclass(frozen=True)
class XForecast:
    direction: str
    time_start_utc: object
    time_end_utc: object
    price_low: float
    price_high: float
    price_center: float
    path_type: str
    source_horizon_minutes: int
    status: str = "uncalibrated"

    def to_dict(self):
        d=asdict(self)
        d["time_start_utc"]=self.time_start_utc.isoformat()
        d["time_end_utc"]=self.time_end_utc.isoformat()
        return d

class XForecastEngine:
    def forecast(self, distribution):
        if distribution.status!="ok" or not distribution.horizons:
            return None
        rows=list(distribution.horizons.values())
        score=sum(r.probability_up-r.probability_down for r in rows)/len(rows)
        direction="LONG" if score>=0 else "SHORT"
        candidates=[r for r in rows if (
            r.expected_terminal_return_pct>0 if direction=="LONG"
            else r.expected_terminal_return_pct<0
        )] or rows
        src=max(candidates,key=lambda r:abs(r.expected_terminal_return_pct))
        p=distribution.reference_price
        adverse=min(p,src.predicted_price_low) if direction=="LONG" else max(p,src.predicted_price_high)
        counter=abs(adverse/p-1)*100 if p else 0.0
        center=p*(1-counter/200) if direction=="LONG" else p*(1+counter/200)
        width=max(0.02,min(0.20,max(counter,0.05)*0.25))
        start=max(1,round(src.horizon_minutes*0.20))
        end=max(start+1,round(src.horizon_minutes*0.50))
        return XForecast(
            direction,
            distribution.forecast_time_utc+timedelta(minutes=start),
            distribution.forecast_time_utc+timedelta(minutes=end),
            center*(1-width/100),center*(1+width/100),center,
            "COUNTER_MOVE_THEN_CONTINUATION" if counter>=0.03 else "DIRECT_CONTINUATION",
            src.horizon_minutes
        )
