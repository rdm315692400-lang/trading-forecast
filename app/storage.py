import os, json, base64
from datetime import datetime, timezone

_db = None

def _client():
    global _db
    if _db is not None:
        return _db
    raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip()
    if not raw:
        return None
    import firebase_admin
    from firebase_admin import credentials, firestore
    try:
        firebase_admin.get_app()
    except ValueError:
        try:
            info = json.loads(raw)
        except json.JSONDecodeError:
            info = json.loads(base64.b64decode(raw).decode("utf-8"))
        firebase_admin.initialize_app(credentials.Certificate(info))
    _db = firestore.client()
    return _db

def enabled():
    return bool(os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON", "").strip())

def save_asset(item):
    db=_client()
    if db is None: return False
    symbol=item["סמל"]
    payload=dict(item)
    payload["saved_at_utc"]=datetime.now(timezone.utc).isoformat()
    db.collection("asset_forecasts").document(symbol).set(payload)
    return True

def save_forecast_history(item):
    db=_client()
    if db is None: return False
    symbol=item["סמל"]
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    db.collection("forecast_history").document(symbol).collection("runs").document(stamp).set(item)
    return True

def load_assets(symbols):
    db=_client()
    if db is None: return {}
    result={}
    for symbol in symbols:
        snap=db.collection("asset_forecasts").document(symbol).get()
        if snap.exists:
            result[symbol]=snap.to_dict()
    return result
