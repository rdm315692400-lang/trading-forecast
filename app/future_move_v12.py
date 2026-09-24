from collections import defaultdict
from statistics import median


OPEN_MINUTE = 570
OPENING_RANGE_END = 600
CLOSE_MINUTE = 960


def _pct(a, b):
    return ((b / a) - 1) * 100 if a else 0.0


def _r(x, n=3):
    return round(float(x), n)


def _sessions(rows):
    g = defaultdict(list)
    for x in rows:
        day = x.get("day")
        minute = x.get("minute", -1)
        if day is not None and OPEN_MINUTE <= minute <= CLOSE_MINUTE:
            g[day].append(x)
    return [(day, sorted(g[day], key=lambda z: z["minute"])) for day in sorted(g)]


def _signal_for_day(rows, direction):
    if direction not in ("קנייה", "מכירה") or len(rows) < 100:
        return None

    first = [x for x in rows if OPEN_MINUTE <= x["minute"] < OPENING_RANGE_END]
    later = [x for x in rows if x["minute"] >= OPENING_RANGE_END]
    if not first or not later:
        return None

    hi = max(float(x.get("high") or 0) for x in first)
    lows = [float(x.get("low") or 0) for x in first if float(x.get("low") or 0) > 0]
    if not lows:
        return None
    lo = min(lows)

    for x in later:
        close = float(x.get("close") or 0)
        if close <= 0:
            continue
        if direction == "קנייה" and close > hi:
            return x
        if direction == "מכירה" and close < lo:
            return x
    return None


def _observed_move(rows, direction, exit_after_minutes=120):
    """
    X is a real-time detectable opening-range breakout.
    V is fixed ex-ante: first bar at/after X + exit_after_minutes,
    capped by the regular-session close. No hindsight best high/low is used.
    """
    entry = _signal_for_day(rows, direction)
    if not entry:
        return None

    entry_minute = int(entry["minute"])
    target_minute = min(CLOSE_MINUTE, entry_minute + exit_after_minutes)
    after = [x for x in rows if x["minute"] >= target_minute]
    if not after:
        return None
    exit_bar = after[0]

    entry_price = float(entry.get("close") or 0)
    exit_price = float(exit_bar.get("close") or 0)
    if entry_price <= 0 or exit_price <= 0:
        return None

    signed = _pct(entry_price, exit_price)
    if direction == "מכירה":
        signed = -signed

    return {
        "day": entry["day"],
        "direction": direction,
        "entry_minute": entry_minute,
        "exit_minute": int(exit_bar["minute"]),
        "entry_price": entry_price,
        "exit_price": exit_price,
        "signed_move": signed,
    }


def learn_future_xv(minute_rows, direction, exit_after_minutes=120):
    """
    Learns only FUTURE remaining movement X->V.
    Movement before X is never counted as forecast potential.
    """
    samples = []
    for day, rows in _sessions(minute_rows):
        s = _observed_move(rows, direction, exit_after_minutes)
        if s:
            samples.append(s)

    if len(samples) < 3:
        return {
            "סטטוס_XV": "אין מספיק דגימות",
            "מספר_דגימות": len(samples),
            "כיוון": direction,
        }

    moves = [x["signed_move"] for x in samples]
    positive = [m for m in moves if m > 0]
    expected_signed = median(moves)
    success = 100 * len(positive) / len(moves)

    # Potential is ONLY the still-future X->V leg.
    potential = max(0.0, expected_signed)

    return {
        "סטטוס_XV": "תקין",
        "כיוון": direction,
        "מספר_דגימות": len(samples),
        "הגדרת_X": "פריצת טווח 30 הדקות הראשונות שניתנת לזיהוי בזמן אמת",
        "הגדרת_V": f"סגירה {exit_after_minutes} דקות לאחר X, או סגירת המסחר אם מוקדם יותר",
        "צפי_תחילת_מהלך_דקת_שוק": int(median([x["entry_minute"] for x in samples])),
        "צפי_סיום_מהלך_דקת_שוק": int(median([x["exit_minute"] for x in samples])),
        "צפי_תנועה_עתידית_XV_אחוז": _r(potential),
        "חציון_תנועה_חתומה_XV_אחוז": _r(expected_signed),
        "שיעור_הצלחה_היסטורי_XV_אחוז": _r(success, 1),
        "הערה_XV": "תנועה שכבר התרחשה לפני X אינה נכללת בפוטנציאל.",
    }


def walk_forward_future_xv(minute_rows, direction, min_train_sessions=5, exit_after_minutes=120):
    """
    Expanding walk-forward over intraday sessions.
    At each test day, X/V timing and expected remaining move are learned
    only from earlier sessions. The test-day result is never used in its forecast.
    """
    sessions = _sessions(minute_rows)
    observations = []
    for day, rows in sessions:
        obs = _observed_move(rows, direction, exit_after_minutes)
        if obs:
            observations.append(obs)

    if len(observations) <= min_train_sessions:
        return {
            "סטטוס": "אין מספיק דגימות ל-Walk-Forward",
            "מספר_דגימות_XV": len(observations),
        }

    tests = []
    for i in range(min_train_sessions, len(observations)):
        train = observations[:i]
        target = observations[i]

        expected = median([x["signed_move"] for x in train])
        predicted_potential = max(0.0, expected)
        actual = target["signed_move"]

        tests.append({
            "תאריך": str(target["day"]),
            "פוטנציאל_XV_חזוי_אחוז": _r(predicted_potential),
            "תנועה_XV_בפועל_אחוז": _r(actual),
            "פגיעה_בכיוון": actual > 0,
            "שגיאת_עוצמה_מוחלטת_אחוז": _r(abs(predicted_potential - max(0.0, actual))),
        })

    if not tests:
        return {"סטטוס": "אין מספיק בדיקות", "מספר_בדיקות": 0}

    hits = sum(1 for x in tests if x["פגיעה_בכיוון"])
    mae = sum(x["שגיאת_עוצמה_מוחלטת_אחוז"] for x in tests) / len(tests)

    return {
        "סטטוס": "תקין",
        "סוג_בדיקה": "Walk-Forward לתנועה העתידית X→V",
        "מספר_בדיקות": len(tests),
        "שיעור_פגיעה_בכיוון_אחוז": _r(100 * hits / len(tests), 1),
        "שגיאת_עוצמה_MAE_אחוז": _r(mae),
        "בדיקות_אחרונות": tests[-10:],
        "הערה": "זהו אימות ראשוני ללא spread/slippage. X ניתן לזיהוי בזמן אמת ו-V מוגדר מראש; אין בחירת שיא/שפל בדיעבד.",
    }
