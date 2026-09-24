from statistics import median

def pct(a,b):
    return ((b/a)-1)*100 if a else 0.0

def med(v):
    return median(v) if v else 0.0

def quantile(values, q):
    if not values: return 0.0
    s=sorted(values)
    pos=(len(s)-1)*q
    lo=int(pos); hi=min(lo+1,len(s)-1); w=pos-lo
    return s[lo]*(1-w)+s[hi]*w

def features(rows):
    out=[]
    for i in range(2,len(rows)):
        a,b,c=rows[i-2],rows[i-1],rows[i]
        out.append({
            "date":c["date"],
            "prior_change":pct(a["open"],a["close"]),
            "prev_change":pct(b["open"],b["close"]),
            "prev_range":pct(b["low"],b["high"]),
            "gap":pct(b["close"],c["open"]),
            "body":pct(c["open"],c["close"]),
            "range":pct(c["low"],c["high"]),
            "open":c["open"],"close":c["close"]
        })
    return out

def forecast_daily(rows):
    if len(rows)<80:
        return {"status":"אין מספיק היסטוריה"}
    f=features(rows)
    last,prev=rows[-1],rows[-2]
    target={"prior_change":pct(prev["open"],prev["close"]),
            "prev_change":pct(last["open"],last["close"]),
            "prev_range":pct(last["low"],last["high"])}
    ranked=[]
    for x in f[:-1]:
        d=(abs(x["prev_change"]-target["prev_change"])*.45+
           abs(x["prev_range"]-target["prev_range"])*.35+
           abs(x["prior_change"]-target["prior_change"])*.20)
        ranked.append((d,x))
    matches=[x for _,x in sorted(ranked,key=lambda z:z[0])[:20]]
    gaps=[x["gap"] for x in matches]
    bodies=[x["body"] for x in matches]
    historical_abs_gaps=[abs(x["gap"]) for x in f[:-1]]
    near_threshold=max(0.05,quantile(historical_abs_gaps,.35))
    eg=med(gaps); eb=med(bodies)
    up=sum(v>0 for v in bodies); down=sum(v<0 for v in bodies); n=len(matches)
    direction="קנייה" if up/n>=.60 else "מכירה" if down/n>=.60 else "ללא עסקה"
    raw=max(up,down)/n*100
    open_price=last["close"]*(1+eg/100)
    exit_price=open_price*(1+eb/100)
    opening="קפיצה למעלה" if eg>near_threshold else "נפילה למטה" if eg<-near_threshold else "סביב שער הסגירה"
    after="המשך" if eg*eb>0 else "היפוך" if eg*eb<0 else "ניטרלי"
    return {
        "status":"תקין","כיוון":direction,"תחזית_פתיחה":opening,
        "פער_פתיחה_צפוי_אחוז":round(eg,2),"סף_פתיחה_אישי_אחוז":round(near_threshold,2),
        "שער_פתיחה_משוער":round(open_price,3),"שער_כניסה_משוער":round(open_price,3),
        "שער_יציאה_משוער":round(exit_price,3),"פוטנציאל_משוער_אחוז":round(abs(eb),2),
        "לאחר_הפתיחה":after,"ביטחון_גולמי_אחוז":round(raw,1),"מספר_מצבים_דומים":n,
        "הערה":"הביטחון גולמי ואינו הסתברות מכוילת; נדרש walk-forward לפני שימוש מסחרי."
    }
