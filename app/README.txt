Trading Forecast — Stage 3 Final Candidate
==========================================

Purpose
-------
Research/day-trading forecasting backend. Stage 3 predicts an ordered future path:
forecast time t -> future X -> future V, and measures only the expected future X->V move.

Stage 3 architecture
--------------------
- 65-asset registry (45 provider-verified US stocks; remaining assets reserved for Stage 4 provider mapping).
- Minute-history cache with immutable UTC bars and received-at timestamps.
- Regular-session-only feature generation for training and forecast-time inference.
- 21 current-state features; no future label is used as a feature.
- Chronological Train / Validation / untouched Holdout split.
- Empirical similarity model fitted on Train only for Stage 3 validation.
- Ordered future X/V labels and learned X/V timing/price interquartile windows.
- Horizons: 15/30/60/90/120/180 minutes, limited by remaining session time.
- X->V ranking objective is future remaining percentage only.
- Walk-forward endpoint is restricted to the Stage 3 Validation partition.
- Validation/calibration reporting does not inspect Holdout.

Important status
----------------
This package is a Stage 3 validation candidate, not a claim of trading accuracy.
The final Holdout must remain unopened until the model design is frozen after server-side Validation.
If the model is changed after seeing Holdout results, that result is no longer a clean final holdout test.

Runtime
-------
Build: pip install -r requirements.txt
Start: uvicorn app.main:app --host 0.0.0.0 --port $PORT
Environment: MASSIVE_API_KEY; optional FIREBASE_SERVICE_ACCOUNT_JSON for Firestore persistence.
