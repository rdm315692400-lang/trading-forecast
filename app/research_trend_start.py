from datetime import timedelta
from statistics import median
from zoneinfo import ZoneInfo
from .asset_registry import get_asset
from .historical_cache import load_day

def _pct(a,b):
    return ((b/a)-1)*100 if a else 0.0

def _regular(asset,bars,day):
    z=ZoneInfo(asset.market_timezone); out=[]
    for b in sorted(bars,key=lambda x:x.timestamp_utc):
        t=b.timestamp_utc.astimezone(z); m=t.hour*60+t.minute
        if t.date().isoformat()==day and 570<=m<960: out.append(b)
    return out

def _row(asset,day,bars):
    b=_regular(asset,bars,day)
    if len(b)<30:return None
    o=float(b[0].open); h=max(float(x.high) for x in b); l=min(float(x.low) for x in b)
    return {"day":day,"bars":b,"range_pct":(h-l)/o*100 if o else 0.0}

def _excursion(bars,i):
    p=float(bars[i].open); future=bars[i:]
    up=max(_pct(p,float(x.high)) for x in future)
    dn=max(-_pct(p,float(x.low)) for x in future)
    return max(0.0,up),max(0.0,dn)

def _quality(bars,i,side):
    p=float(bars[i].open)
    if p<=0:return None
    best=p; fav=0.0; retr=0.0
    for x in bars[i:]:
        if side=="UP":
            best=max(best,float(x.high)); fav=max(fav,_pct(p,best))
            retr=max(retr,(best-float(x.low))/p*100)
        else:
            best=min(best,float(x.low)); fav=max(fav,-_pct(p,best))
            retr=max(retr,(float(x.high)-best)/p*100)
    return fav,retr

def _mark(asset,row,prior_scale):
    bars=row["bars"]; z=ZoneInfo(asset.market_timezone)
    scale=max(float(prior_scale),1e-9)
    # Multiple retrospective sensitivities prevent one arbitrary cutoff
    # from silently becoming the definition of "trend".
    levels=(0.30,0.40,0.50,0.60)
    starts=[]
    for q in levels:
        need=q*scale; found=None
        for i in range(len(bars)):
            up,dn=_excursion(bars,i)
            opts=[]
            if up>=need:opts.append(("UP",up))
            if dn>=need:opts.append(("DOWN",dn))
            if not opts:continue
            opts.sort(key=lambda x:x[1],reverse=True)
            if len(opts)==2 and opts[0][1]<opts[1][1]*1.35:continue
            side=opts[0][0]; qr=_quality(bars,i,side)
            if not qr:continue
            fav,retr=qr
            if fav<max(need,retr*1.35):continue
            found=(i,side);break
        if found:starts.append(found)
    if not starts:
        return {"status":"NO_STABLE_FIRST_TREND_START","trend_start_time":None,"direction":None,"agreement":0}
    votes={}
    for x in starts:votes[x]=votes.get(x,0)+1
    (i,side),agree=max(votes.items(),key=lambda kv:(kv[1],-kv[0][0]))
    if agree<2:
        return {"status":"AMBIGUOUS_START","trend_start_time":None,"direction":None,"agreement":agree}
    t=bars[i].timestamp_utc.astimezone(z)
    return {"status":"MARKED","trend_start_time":t.strftime("%H:%M"),"direction":side,
            "minute_index":i,"start_price":round(float(bars[i].open),6),"agreement":agree}

def mark_history(asset_id,start_day,end_day,reserve_last_days=40):
    asset=get_asset(asset_id)
    if not asset:raise ValueError("unknown_asset")
    raw=[];d=start_day
    while d<=end_day:
        if d.weekday()<5:
            bars=load_day(asset_id,d.isoformat())
            if bars:
                r=_row(asset,d.isoformat(),bars)
                if r:raw.append(r)
        d+=timedelta(days=1)
    raw.sort(key=lambda x:x["day"])
    n=max(0,min(int(reserve_last_days),len(raw)))
    work=raw[:-n] if n else raw; reserved=raw[-n:] if n else []
    prior=[];days=[];counts={"MARKED":0,"AMBIGUOUS_START":0,"NO_STABLE_FIRST_TREND_START":0}
    for r in work:
        scale=median(prior[-20:]) if prior else r["range_pct"]
        m=_mark(asset,r,scale);counts[m["status"]]+=1
        days.append({"day":r["day"],"trend_start_time":m.get("trend_start_time"),
                     "direction":m.get("direction"),"status":m["status"],
                     "minute_index":m.get("minute_index"),"start_price":m.get("start_price"),
                     "agreement":m.get("agreement")})
        prior.append(r["range_pct"])
    return {"asset":asset_id,"milestone":"1_FIRST_TREND_START_MINUTE",
            "status":"RETROSPECTIVE_MARKING_FIRST_PASS","cached_days":len(raw),
            "analysis_days":len(work),"reserved_untouched_days":len(reserved),
            "reserved_dates":[x["day"] for x in reserved],"counts":counts,
            "note":"Marking only: no cause analysis, no feature research, no forecast. Audit before ground truth.",
            "days":days}
