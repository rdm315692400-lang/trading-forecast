def score_item(item):
    f=item.get("תחזית",{})
    if f.get("כיוון")=="ללא עסקה": return -1
    confidence=float(f.get("ביטחון_גולמי_אחוז",0))
    potential=float(f.get("פוטנציאל_משוער_אחוז",0))
    samples=float(f.get("מספר_מצבים_דומים",0))
    return confidence*0.55 + min(potential,5)*8 + min(samples,20)*0.25

def choose_leader(items):
    valid=[x for x in items if x.get("תחזית",{}).get("status")=="תקין"]
    if not valid: return None
    ranked=sorted(valid,key=score_item,reverse=True)
    best=ranked[0]
    return best if score_item(best)>=45 else None
