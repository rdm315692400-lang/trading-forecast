from datetime import timedelta
from statistics import median
from zoneinfo import ZoneInfo
from .asset_registry import get_asset
from .historical_cache import load_day

def _pct(a,b): return ((b/a)-1)*100 if a else 0.0

def _regular(asset,bars,day):
    z=ZoneInfo(asset.market_timezone); out=[]
    for b in sorted(bars,key=lambda x:x.timestamp_utc):
        t=b.timestamp_utc.astimezone(z); m=t.hour*60+t.minute
        if t.date().isoformat()==day and 570<=m<960: out.append(b)
    return out

def _metrics(asset,day,bars):
    b=_regular(asset,bars,day)
    if len(b)<30:return None
    o=float(b[0].open); c=float(b[-1].close); h=max(float(x.high) for x in b); l=min(float(x.low) for x in b)
    return {"day":day,"bars":b,"o":o,"c":c,"h":h,"l":l,"range":(h-l)/o*100,
            "net":_pct(o,c),"eff":abs(c-o)/max(h-l,1e-9)}

def _prefix(b,i,scale):
    s=b[:i+1]; o=float(s[0].open); c=float(s[-1].close); w=s[-6:]
    hs=[float(x.high) for x in w]; ls=[float(x.low) for x in w]; cs=[float(x.close) for x in w]
    return {"znet":_pct(o,c)/max(scale,1e-9),"slope6":_pct(cs[0],cs[-1]),
            "upstruct":sum(hs[j]>hs[j-1] for j in range(1,len(hs)))+sum(ls[j]>ls[j-1] for j in range(1,len(ls))),
            "dnstruct":sum(hs[j]<hs[j-1] for j in range(1,len(hs)))+sum(ls[j]<ls[j-1] for j in range(1,len(ls)))}

def _candidates(asset,m,scale):
    # Prefix-only: no bar after i is read here.
    z=ZoneInfo(asset.market_timezone); out=[]; last=None; last_i=-99
    for i in range(5,len(m["bars"])):
        f=_prefix(m["bars"],i,scale); side=None
        if f["znet"]>=.22 and f["upstruct"]>=6 and f["slope6"]>0: side="UP"
        elif f["znet"]<=-.22 and f["dnstruct"]>=6 and f["slope6"]<0: side="DOWN"
        if side and (side!=last or i-last_i>=15):
            out.append({"market_time":m["bars"][i].timestamp_utc.astimezone(z).strftime("%H:%M"),
                        "minute_index":i,"direction":side,**f})
            last,last_i=side,i
    return out

def _label(m,scale):
    # Retrospective development label only. Never fed into _candidates.
    if abs(m["net"])/max(scale,1e-9)<.28 and m["eff"]<.30:
        return {"class":2,"name":"NO_CLEAR_TREND","direction":None}
    side="UP" if m["c"]>=m["o"] else "DOWN"; pull=0.0
    if side=="UP":
        run=float(m["bars"][0].high)
        for x in m["bars"][1:]:
            run=max(run,float(x.high)); pull=max(pull,(run-float(x.low))/m["o"]*100)
        returned=m["c"]>=m["h"]-.20*(m["h"]-m["l"])
    else:
        run=float(m["bars"][0].low)
        for x in m["bars"][1:]:
            run=min(run,float(x.low)); pull=max(pull,(float(x.high)-run)/m["o"]*100)
        returned=m["c"]<=m["l"]+.20*(m["h"]-m["l"])
    pz=pull/max(scale,1e-9)
    if pz<.22: cls,name=1,"START_AND_CONTINUE_TREND"
    elif returned: cls,name=3,"TREND_CORRECTION_RETURN_TO_EXTREME_ZONE"
    else: cls,name=4,"TREND_CORRECTION_CONTINUATION_OR_NEW_LEG"
    return {"class":cls,"name":name,"direction":side,"pullback_prior_vol_units":round(pz,4)}

def scan_history(asset_id,start_day,end_day,reserve_last_days=40):
    asset=get_asset(asset_id); raw=[]; d=start_day
    if not asset: raise ValueError("unknown_asset")
    while d<=end_day:
        if d.weekday()<5:
            b=load_day(asset_id,d.isoformat())
            if b:
                m=_metrics(asset,d.isoformat(),b)
                if m:raw.append(m)
        d+=timedelta(days=1)
    raw.sort(key=lambda x:x["day"]); n=max(0,min(int(reserve_last_days),len(raw)))
    work=raw[:-n] if n else raw; reserved=raw[-n:] if n else []
    prior=[]; days=[]; counts={1:0,2:0,3:0,4:0}
    for m in work:
        scale=median(prior[-20:]) if prior else m["range"]; lab=_label(m,scale); cand=_candidates(asset,m,scale) if prior else []
        counts[lab["class"]]+=1
        days.append({"day":m["day"],"bars":len(m["bars"]),"range_pct":round(m["range"],4),"net_pct":round(m["net"],4),
                     "efficiency":round(m["eff"],4),"prior20_range_pct":round(scale,4),"retrospective_label":lab,
                     "first_causal_candidate":cand[0] if cand else None,"candidate_count":len(cand)})
        prior.append(m["range"])
    return {"asset":asset_id,"cached_days":len(raw),"analysis_days":len(work),"reserved_untouched_days":len(reserved),
            "reserved_dates":[x["day"] for x in reserved],"provisional_class_counts":counts,
            "method":{"point":"Point 1","status":"DISCOVERY_ONLY","future_used_in_candidate":False,
                      "labels_use_full_day":True,"normalization":"prior 20 sessions",
                      "note":"Thresholds/labels are hypotheses, not validated trading rules."},"days":days}
