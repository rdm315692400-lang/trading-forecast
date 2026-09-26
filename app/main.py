from fastapi import FastAPI
from .settings import APP_VERSION
from .asset_registry import all_assets, provider_verified_assets
from .storage import configured
from .scanner import BACKGROUND_SCANNER_ENABLED
from .api import router

app=FastAPI(title="Trading Forecast",version=APP_VERSION)
app.include_router(router)

@app.get("/")
async def root():
    return {"ok":True,"name":"Trading Forecast","version":APP_VERSION}

@app.get("/health")
async def health():
    return {
        "ok":True,
        "version":APP_VERSION,
        "architecture":"stage3-future-xv",
        "universe":len(all_assets()),
        "provider_verified_assets":len(provider_verified_assets()),
        "firestore_configured":configured(),
        "background_scanner":BACKGROUND_SCANNER_ENABLED,
        "forecast_status":"stage3_validation_candidate_not_holdout_calibrated",
    }
