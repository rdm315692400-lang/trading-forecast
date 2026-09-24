V13.0 DATA FOUNDATION

Purpose:
- Asset Registry
- Raw historical bar contract
- Snapshot Engine
- Replay Engine
- Explicit anti-future-leakage test

Important:
This version does NOT replace V12.5.
It contains no trading model and no live ranking yet.

Core rule:
A historical item is visible at time t only when:
1) its market timestamp <= t
2) its received/available timestamp <= t

Run:
python test_no_future_leak.py
