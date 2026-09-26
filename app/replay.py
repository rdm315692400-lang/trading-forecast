from .historical_store import HistoricalStore
from .snapshot_engine import SnapshotEngine
from .forecast_pipeline import forecast_snapshot
from .validation import anti_leak, evaluate_frozen_xv

def replay_at(asset_id,bars,forecast_time_utc,fitted_model):
    store=HistoricalStore();store.extend(bars)
    snapshot=SnapshotEngine(store).build(asset_id,forecast_time_utc)
    if not anti_leak(snapshot):
        raise RuntimeError("anti-leak invariant failed")
    forecast_id,d,x,v=forecast_snapshot(snapshot,fitted_model)
    result={"forecast_id":forecast_id,"anti_leak":True,"visible_bars":len(snapshot.bars)}
    if not x or not v:
        result["forecast_available"]=False
        return result
    result.update({
        "forecast_available":True,
        "distribution":d.to_dict(),"X":x.to_dict(),"V":v.to_dict(),
        "outcome":evaluate_frozen_xv(bars,forecast_time_utc,x,v),
    })
    return result
