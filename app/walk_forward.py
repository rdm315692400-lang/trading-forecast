from dataclasses import dataclass,asdict
from statistics import mean,median
from .historical_store import HistoricalStore
from .snapshot_engine import SnapshotEngine
from .forecast_pipeline import forecast_snapshot
from .validation import anti_leak
from .market_clock import market_time_to_utc,session_bounds_utc

@dataclass(frozen=True)
class Sample:
    asset_id:str;market_day:str;forecast_time_utc:str;forecast_id:str;direction:str;horizon_minutes:int
    predicted_x_to_v_pct:float;x_touched:bool;v_touched_after_x:bool
    actual_x_to_v_pct:float|None;error_pct_points:float|None
    direction_realized:bool|None;post_x_mfe_pct:float|None;post_x_mae_pct:float|None
    x_time_utc:str|None;v_time_utc:str|None
    def to_dict(self):return asdict(self)

def touches(b,lo,hi):return float(b.low)<=hi and float(b.high)>=lo
def touch_price(b,lo,hi):
    c=float(b.close)
    return c if lo<=c<=hi else (lo if c<lo else hi)

def excursions(direction,entry,bars):
    if not bars or not entry:return None,None
    hi=max(float(b.high) for b in bars);lo=min(float(b.low) for b in bars)
    if direction=="LONG":
        return max(0,(hi/entry-1)*100),max(0,(1-lo/entry)*100)
    return max(0,(1-lo/entry)*100),max(0,(hi/entry-1)*100)

def evaluate(asset_id,market_day,bars,forecast_time):
    op,cl=session_bounds_utc(asset_id,market_day)
    regular=[b for b in bars if op<=b.timestamp_utc<cl]
    store=HistoricalStore();store.extend(regular)
    snap=SnapshotEngine(store).build(asset_id,forecast_time)
    if not snap.bars or not anti_leak(snap):return None
    fid,d,x,v=forecast_snapshot(snap)
    if not x or not v:return None
    if x.time_start_utc>=cl or v.time_start_utc>=cl:return None
    xe=min(x.time_end_utc,cl);vs=min(v.time_start_utc,cl);ve=min(v.time_end_utc,cl)
    later=[b for b in regular if b.received_at_utc>forecast_time and b.timestamp_utc<cl]
    xb=next((b for b in later if x.time_start_utc<=b.received_at_utc<=xe and touches(b,x.price_low,x.price_high)),None)
    xp=touch_price(xb,x.price_low,x.price_high) if xb else None
    after=[b for b in later if xb and b.received_at_utc>xb.received_at_utc and b.received_at_utc<=ve]
    vb=next((b for b in after if vs<=b.received_at_utc<=ve and touches(b,v.price_low,v.price_high)),None)
    vp=touch_price(vb,v.price_low,v.price_high) if vb else None
    actual=err=realized=None
    if xp and vp:
        signed=(vp/xp-1)*100;actual=signed if v.direction=="LONG" else -signed
        err=abs(v.expected_x_to_v_pct-actual);realized=actual>0
    mfe,mae=excursions(v.direction,xp,after) if xp else (None,None)
    return Sample(asset_id,market_day.isoformat(),forecast_time.isoformat(),fid,v.direction,
        v.source_horizon_minutes,v.expected_x_to_v_pct,bool(xb),bool(vb),actual,err,realized,mfe,mae,
        xb.received_at_utc.isoformat() if xb else None,vb.received_at_utc.isoformat() if vb else None)

def summarize(samples):
    n=len(samples);xh=[s for s in samples if s.x_touched];vh=[s for s in samples if s.v_touched_after_x]
    rr=[s for s in samples if s.actual_x_to_v_pct is not None]
    vals=lambda attr,rows:[getattr(s,attr) for s in rows if getattr(s,attr) is not None]
    by={}
    for h in sorted(set(s.horizon_minutes for s in samples)):
        hs=[s for s in samples if s.horizon_minutes==h];hr=[s for s in hs if s.actual_x_to_v_pct is not None]
        by[str(h)]={"samples":len(hs),"x_touch_rate":sum(s.x_touched for s in hs)/len(hs),
          "v_touch_after_x_rate":sum(s.v_touched_after_x for s in hs)/max(1,sum(s.x_touched for s in hs)),
          "direction_realized_rate":sum(bool(s.direction_realized) for s in hr)/len(hr) if hr else None,
          "mean_error_pct_points":mean(vals("error_pct_points",hr)) if vals("error_pct_points",hr) else None}
    return {"samples":n,"x_touch_rate":len(xh)/n if n else None,
      "v_touch_after_x_rate":len(vh)/len(xh) if xh else None,
      "direction_realized_rate":sum(bool(s.direction_realized) for s in rr)/len(rr) if rr else None,
      "mean_x_to_v_error_pct_points":mean(vals("error_pct_points",rr)) if vals("error_pct_points",rr) else None,
      "median_post_x_mfe_pct":median(vals("post_x_mfe_pct",xh)) if vals("post_x_mfe_pct",xh) else None,
      "median_post_x_mae_pct":median(vals("post_x_mae_pct",xh)) if vals("post_x_mae_pct",xh) else None,
      "by_horizon":by,"calibrated":False,"status":"DIAGNOSTIC_ONLY"}

def run_cached_walk_forward(asset_id,days,forecast_times=("10:30","12:30","14:00")):
    samples=[]
    for day in sorted(days):
        if day.weekday()>=5:continue
        for hhmm in forecast_times:
            s=evaluate(asset_id,day,list(days[day]),market_time_to_utc(asset_id,day,hhmm))
            if s:samples.append(s)
    return {"ok":True,"asset":asset_id,"summary":summarize(samples),
      "samples":[s.to_dict() for s in samples],"provider_called":False,"firestore_called":False}
