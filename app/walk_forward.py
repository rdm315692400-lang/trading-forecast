from .model_v12 import forecast_daily

def run_walk_forward(rows, min_train=80):
    tests=[]
    for end in range(min_train, len(rows)-1):
        train=rows[:end+1]
        target=rows[end+1]
        pred=forecast_daily(train)
        direction=pred.get("כיוון")
        if direction not in ("קנייה","מכירה"):
            continue
        body=((target["close"]/target["open"])-1)*100 if target["open"] else 0
        actual="קנייה" if body>0 else "מכירה" if body<0 else "ללא עסקה"
        tests.append({"תאריך":str(target["date"]),"תחזית":direction,"בפועל":actual,
                      "פגיעה":direction==actual,"תשואת_יום_אחוז":round(body,3)})
    if not tests:
        return {"סטטוס":"אין מספיק בדיקות","מספר_בדיקות":0}
    hits=sum(x["פגיעה"] for x in tests)
    accuracy=100*hits/len(tests)
    return {"סטטוס":"תקין","מספר_בדיקות":len(tests),"פגיעות":hits,
            "דיוק_out_of_sample_אחוז":round(accuracy,1),
            "ביטחון_מכויל_אחוז":round(accuracy,1),
            "בדיקות_אחרונות":tests[-10:]}
