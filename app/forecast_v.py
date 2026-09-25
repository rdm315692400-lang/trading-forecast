from dataclasses import dataclass, asdict
from datetime import timedelta

@dataclass(frozen=True)
class VForecast:
    direction: str
    time_start_utc: object
    time_end_utc: object
    price_low: float
    price_high: float
    price_center: float
    expected_x_to_v_pct: float
    source_horizon_minutes: int
    status: str = "uncalibrated"

    def to_dict(self):
        d=asdict(self)
        d["time_start_utc"]=self.time_start_utc.isoformat()
        d["time_end_utc"]=self.time_end_utc.isoformat()
        return d

class VForecastEngine:
    def forecast(self, distribution, x):
        if x is None:
            return None
        src=distribution.horizons[x.source_horizon_minutes]
        target=distribution.reference_price*(1+src.expected_terminal_return_pct/100)
        center=max(x.price_center,target) if x.direction=="LONG" else min(x.price_center,target)
        signed=(center/x.price_center-1)*100 if x.price_center else 0.0
        potential=max(0.0,signed if x.direction=="LONG" else -signed)
        width=max(0.02,potential*0.20)
        start=max(1,round(src.horizon_minutes*0.55))
        end=max(start+1,src.horizon_minutes)
        return VForecast(
            x.direction,
            distribution.forecast_time_utc+timedelta(minutes=start),
            distribution.forecast_time_utc+timedelta(minutes=end),
            center*(1-width/100),center*(1+width/100),center,
            potential,src.horizon_minutes
        )
