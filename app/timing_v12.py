from collections import defaultdict
from statistics import median
from .market_profiles import market_to_israel, minute_text

def learn_timing(minute_rows, direction):
    if direction not in ("קנייה","מכירה"):
        return {"סטטוס_זמנים":"לא מחושב ללא כיוון עסקה"}
    g=defaultdict(list)
    for x in minute_rows:
        if x.get("day") is not None and 570<=x.get("minute",-1)<=960:
            g[x["day"]].append(x)
    samples=[]
    for day in sorted(g):
        c=sorted(g[day],key=lambda x:x["minute"])
        if len(c)<100: continue
        # אות בזמן אמת: פריצת טווח 30 הדקות הראשונות, לא שימוש בשפל/שיא בדיעבד.
        first=[x for x in c if 570<=x["minute"]<600]
        later=[x for x in c if x["minute"]>=600]
        if not first or not later: continue
        hi=max(float(x.get("high") or 0) for x in first)
        lo=min(float(x.get("low") or 0) for x in first if float(x.get("low") or 0)>0)
        entry=None
        for x in later:
            close=float(x.get("close") or 0)
            if direction=="קנייה" and close>hi:
                entry=x; break
            if direction=="מכירה" and close<lo:
                entry=x; break
        if not entry: continue
        after=[x for x in later if x["minute"]>=entry["minute"]]
        if direction=="קנייה":
            best=max(after,key=lambda x:float(x.get("high") or 0))
        else:
            best=min(after,key=lambda x:float(x.get("low") or 10**18))
        if best["minute"]<=entry["minute"]: continue
        samples.append((day,entry["minute"],best["minute"]))
    if len(samples)<3:
        return {"סטטוס_זמנים":"אין מספיק דגימות","מספר_דגימות":len(samples)}
    em=int(median([x[1] for x in samples])); xm=int(median([x[2] for x in samples]))
    ref_day=samples[-1][0]
    return {
        "סטטוס_זמנים":"נלמד מאות כניסה שניתן לזהות בזמן אמת",
        "מספר_דגימות":len(samples),
        "שעת_כניסה_שוק":minute_text(em),
        "שעת_כניסה_ישראל":market_to_israel(ref_day,em),
        "שעת_יציאה_שוק":minute_text(xm),
        "שעת_יציאה_ישראל":market_to_israel(ref_day,xm),
        "הערה_זמנים":"השעה בישראל מומרת לפי אזור הזמן והתאריך; נדרש אימות walk-forward."
    }
