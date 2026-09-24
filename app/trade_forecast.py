from statistics import median

def _pct(a, b):
    return ((b / a) - 1) * 100 if a else 0.0

def _median(values):
    return median(values) if values else 0.0

def _daily_features(rows):
    out = []
    for i in range(2, len(rows)):
        p2, prev, cur = rows[i-2], rows[i-1], rows[i]
        prev_change = _pct(prev["open"], prev["close"])
        prev_range = ((prev["high"] - prev["low"]) / prev["open"]) * 100
        prior_change = _pct(p2["open"], p2["close"])
        gap = _pct(prev["close"], cur["open"])
        body = _pct(cur["open"], cur["close"])
        rng = ((cur["high"] - cur["low"]) / cur["open"]) * 100
        out.append({
            "prev_change": prev_change,
            "prev_range": prev_range,
            "prior_change": prior_change,
            "gap": gap,
            "body": body,
            "range": rng,
            "open": cur["open"],
            "high": cur["high"],
            "low": cur["low"],
            "close": cur["close"],
        })
    return out

def next_day_trade_forecast(daily_rows, minute_rows):
    if len(daily_rows) < 60:
        return {"status": "אין מספיק היסטוריה"}

    hist = _daily_features(daily_rows)
    last = daily_rows[-1]
    prev = daily_rows[-2]
    target = {
        "prev_change": _pct(last["open"], last["close"]),
        "prev_range": ((last["high"] - last["low"]) / last["open"]) * 100,
        "prior_change": _pct(prev["open"], prev["close"]),
    }

    ranked = []
    for x in hist[:-1]:
        distance = (
            abs(x["prev_change"] - target["prev_change"]) * 0.45
            + abs(x["prev_range"] - target["prev_range"]) * 0.35
            + abs(x["prior_change"] - target["prior_change"]) * 0.20
        )
        ranked.append((distance, x))

    matches = [x for _, x in sorted(ranked, key=lambda z: z[0])[:20]]
    if len(matches) < 8:
        return {"status": "אין מספיק מצבים דומים"}

    gaps = [x["gap"] for x in matches]
    bodies = [x["body"] for x in matches]
    up = sum(x > 0 for x in bodies)
    down = sum(x < 0 for x in bodies)
    n = len(matches)

    direction = "LONG" if up / n >= 0.60 else "SHORT" if down / n >= 0.60 else "ללא עסקה"
    confidence = max(up, down) / n * 100
    expected_gap = _median(gaps)
    expected_body = _median(bodies)
    previous_close = last["close"]
    expected_open = previous_close * (1 + expected_gap / 100)

    if direction == "LONG":
        positive = [x["body"] for x in matches if x["body"] > 0]
        move = _median(positive)
        expected_exit = expected_open * (1 + move / 100)
    elif direction == "SHORT":
        negative = [x["body"] for x in matches if x["body"] < 0]
        move = _median(negative)
        expected_exit = expected_open * (1 + move / 100)
    else:
        expected_exit = expected_open * (1 + expected_body / 100)

    # Intraday timing is estimated only from the recent minute sample.
    # It is deliberately returned as a window, not a guaranteed timestamp.
    entry_window = "09:30–10:30"
    exit_window = "14:30–16:00"

    if minute_rows:
        market = [x for x in minute_rows if 570 <= x.get("minute", -1) <= 960]
        if market:
            # If recent sessions tend to expand early, narrow the entry window.
            early = [x for x in market if 570 <= x.get("minute", -1) <= 600]
            later = [x for x in market if 600 < x.get("minute", -1) <= 660]
            if early and later:
                early_ranges = [abs(float(x.get("high") or 0) - float(x.get("low") or 0)) for x in early]
                later_ranges = [abs(float(x.get("high") or 0) - float(x.get("low") or 0)) for x in later]
                if _median(early_ranges) > _median(later_ranges):
                    entry_window = "09:30–10:00"
                else:
                    entry_window = "10:00–10:30"

    potential = abs(_pct(expected_open, expected_exit))
    opening_state = "Gap Up" if expected_gap > 0.15 else "Gap Down" if expected_gap < -0.15 else "סביב שער הסגירה"
    after_open = "המשך" if expected_gap * expected_body > 0 else "היפוך" if expected_gap * expected_body < 0 else "ניטרלי"

    return {
        "direction": direction,
        "opening_forecast": opening_state,
        "expected_gap_percent": round(expected_gap, 2),
        "expected_open_price": round(expected_open, 3),
        "entry_price_estimate": round(expected_open, 3),
        "entry_time_window": entry_window,
        "exit_price_estimate": round(expected_exit, 3),
        "exit_time_window": exit_window,
        "potential_percent": round(potential, 2),
        "after_open_forecast": after_open,
        "model_confidence_raw": round(confidence, 1),
        "historical_matches": n,
        "warning": "תחזית מחקרית. רמת הביטחון טרם מכוילת ב-walk-forward; השעות הן חלונות משוערים."
    }
