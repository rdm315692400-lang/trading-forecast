from collections import defaultdict
from statistics import median
OPEN, CLOSE = 570, 960

def pct(a,b):
    return ((b/a)-1)*100 if a else 0.0

def sessions(rows):
    g = defaultdict(list)
    for x in rows:
        if x.get("day") is not None and OPEN <= x.get("minute",-1) <= CLOSE:
            g[x["day"]].append(x)
    out=[]
    for day in sorted(g):
        cs=sorted(g[day],key=lambda x:x["minute"])
        if len(cs)<20: continue
        o=float(cs[0].get("open") or 0); c=float(cs[-1].get("close") or 0)
        hs=[float(x.get("high") or 0) for x in cs]
        ls=[float(x.get("low") or 0) for x in cs if float(x.get("low") or 0)>0]
        if o<=0 or c<=0 or not hs or not ls: continue
        out.append({"day":day,"open":o,"high":max(hs),"low":min(ls),"close":c,"change":pct(o,c),"range":(max(hs)-min(ls))/o*100})
    return out

def forecast(symbol, rows):
    s=sessions(rows)
    if len(s)<4: return {"symbol":symbol,"status":"אין מספיק היסטוריה"}
    cur=s[-1]; cand=[]
    for i in range(len(s)-2):
        old,nxt=s[i],s[i+1]
        d=abs(old["change"]-cur["change"])*.6+abs(old["range"]-cur["range"])*.4
        cand.append((d,nxt))
    m=[x[1] for x in sorted(cand,key=lambda x:x[0])[:10]]
    ch=[x["change"] for x in m]; n=len(ch)
    lp=sum(v>0 for v in ch)/n*100 if n else 0
    sp=sum(v<0 for v in ch)/n*100 if n else 0
    direction="LONG" if lp>=60 else "SHORT" if sp>=60 else "ללא עסקה"
    confidence=lp if direction=="LONG" else sp if direction=="SHORT" else max(lp,sp)
    exp=median(ch) if ch else 0
    trend="עלייה" if exp>.25 else "ירידה" if exp<-.25 else "ניטרלי"
    return {"symbol":symbol,"trend_forecast":trend,"direction":direction,"model_confidence":round(confidence,1),"historical_matches":n,"expected_next_change":round(exp,2),"current_reference_price":round(cur["close"],3)}

def opening_forecast(rows):
    if len(rows)<30: return {"status":"אין מספיק היסטוריה"}
    obs=[]
    for i in range(1,len(rows)):
        prev,cur=rows[i-1],rows[i]
        obs.append((pct(prev["close"],cur["open"]),pct(cur["open"],cur["close"])))
    threshold=max(.10, median([abs(g) for g,_ in obs])*.5)
    up=sum(g>threshold for g,_ in obs); down=sum(g<-threshold for g,_ in obs)
    near=len(obs)-up-down; cont=sum((g>threshold and b>0) or (g<-threshold and b<0) for g,b in obs)
    rev=sum((g>threshold and b<0) or (g<-threshold and b>0) for g,b in obs); n=len(obs)
    return {"near_close_threshold_percent":round(threshold,2),"gap_up_frequency":round(up/n*100,1),"gap_down_frequency":round(down/n*100,1),"near_close_frequency":round(near/n*100,1),"continuation_frequency":round(cont/n*100,1),"reversal_frequency":round(rev/n*100,1),"samples":n,"note":"התפלגות היסטורית; עדיין אינה הסתברות מכוילת ליום הבא"}
