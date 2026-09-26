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
    direction_probability: float
    expected_adverse_move_pct: float
    status: str = "validation_only_not_calibrated"

    def to_dict(self):
        d=asdict(self); d["time_start_utc"]=self.time_start_utc.isoformat(); d["time_end_utc"]=self.time_end_utc.isoformat(); return d

class XForecastEngine:
    def _candidate_score(self,r):
        return max(r.expected_long_x_to_v_pct*r.probability_up,
                   r.expected_short_x_to_v_pct*r.probability_down)

    def forecast(self,distribution):
        if distribution.status!="ok" or not distribution.horizons:return None
        src=max(distribution.horizons.values(),key=self._candidate_score)
        long_score=src.expected_long_x_to_v_pct*src.probability_up
        short_score=src.expected_short_x_to_v_pct*src.probability_down
        direction="LONG" if long_score>=short_score else "SHORT"
        p=float(distribution.reference_price)
        if direction=="LONG":
            adverse=max(0.0,src.expected_long_x_adverse_pct); center=p*(1-adverse/100)
            start_min=max(1.0,src.long_x_minute_q25); end_min=max(start_min,src.long_x_minute_q75)
            # Larger adverse return means a lower LONG entry price.
            price_low=p*(1-max(0.0,src.long_x_adverse_q75)/100)
            price_high=p*(1-max(0.0,src.long_x_adverse_q25)/100)
            prob=src.probability_up
        else:
            adverse=max(0.0,src.expected_short_x_adverse_pct); center=p*(1+adverse/100)
            start_min=max(1.0,src.short_x_minute_q25); end_min=max(start_min,src.short_x_minute_q75)
            price_low=p*(1+max(0.0,src.short_x_adverse_q25)/100)
            price_high=p*(1+max(0.0,src.short_x_adverse_q75)/100)
            prob=src.probability_down
        end_min=min(float(src.horizon_minutes),end_min)
        start_min=min(end_min,start_min)
        lo,hi=sorted((price_low,price_high))
        return XForecast(direction,distribution.forecast_time_utc+timedelta(minutes=start_min),
                         distribution.forecast_time_utc+timedelta(minutes=end_min),lo,hi,center,
                         "ORDERED_FUTURE_X_THEN_V",src.horizon_minutes,prob,adverse)
