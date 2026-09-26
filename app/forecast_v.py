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
    direction_probability: float
    status: str = "validation_only_not_calibrated"

    def to_dict(self):
        d=asdict(self); d["time_start_utc"]=self.time_start_utc.isoformat(); d["time_end_utc"]=self.time_end_utc.isoformat(); return d

class VForecastEngine:
    def forecast(self,distribution,x):
        if x is None:return None
        src=distribution.horizons.get(x.source_horizon_minutes)
        if src is None:return None
        p=float(distribution.reference_price)
        x_end=(x.time_end_utc-distribution.forecast_time_utc).total_seconds()/60
        if x.direction=="LONG":
            center=p*(1+max(0.0,src.expected_long_v_reach_pct)/100)
            start_min=max(x_end+1.0,src.long_v_minute_q25)
            end_min=max(start_min,src.long_v_minute_q75)
            price_low=p*(1+max(0.0,src.long_v_reach_q25)/100)
            price_high=p*(1+max(0.0,src.long_v_reach_q75)/100)
            potential=max(0.0,src.expected_long_x_to_v_pct); prob=src.probability_up
        else:
            center=p*(1-max(0.0,src.expected_short_v_reach_pct)/100)
            start_min=max(x_end+1.0,src.short_v_minute_q25)
            end_min=max(start_min,src.short_v_minute_q75)
            price_low=p*(1-max(0.0,src.short_v_reach_q75)/100)
            price_high=p*(1-max(0.0,src.short_v_reach_q25)/100)
            potential=max(0.0,src.expected_short_x_to_v_pct); prob=src.probability_down
        if start_min>src.horizon_minutes:return None
        end_min=min(float(src.horizon_minutes),end_min)
        lo,hi=sorted((price_low,price_high))
        return VForecast(x.direction,distribution.forecast_time_utc+timedelta(minutes=start_min),
                         distribution.forecast_time_utc+timedelta(minutes=end_min),lo,hi,center,
                         potential,src.horizon_minutes,prob)
