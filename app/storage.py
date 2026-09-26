import json
import os
from datetime import datetime, timezone
from .settings import FORECAST_COLLECTION, OUTCOME_COLLECTION

_db = None

def client():
    global _db
    if _db is not None:
        return _db
    raw = os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON")
    if not raw:
        return None
    import firebase_admin
    from firebase_admin import credentials, firestore
    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.Certificate(json.loads(raw)))
    _db = firestore.client()
    return _db

def configured():
    return bool(os.getenv("FIREBASE_SERVICE_ACCOUNT_JSON"))

def save_frozen_forecast(forecast_id: str, payload: dict):
    db = client()
    if db is None:
        return False
    doc = dict(payload)
    doc["saved_at_utc"] = datetime.now(timezone.utc).isoformat()
    db.collection(FORECAST_COLLECTION).document(forecast_id).set(doc)
    return True

def save_outcome(forecast_id: str, payload: dict):
    db = client()
    if db is None:
        return False
    db.collection(OUTCOME_COLLECTION).document(forecast_id).set(payload)
    return True
