from statistics import mean, median
from .model_v12 import forecast_daily


def _pct(a, b):
    return ((b / a) - 1) * 100 if a else 0.0


def _r(value, digits=3):
    return round(float(value), digits)


def _direction_stats(tests, direction):
    rows = [x for x in tests if x["תחזית"] == direction]
    if not rows:
        return {
            "מספר_תחזיות": 0,
            "פגיעות": 0,
            "שיעור_פגיעה_אחוז": None,
            "תשואה_ממוצעת_לכיוון_אחוז": None,
            "חציון_תשואה_לכיוון_אחוז": None,
        }
    hits = sum(1 for x in rows if x["פגיעה"])
    returns = [x["תשואה_לכיוון_אחוז"] for x in rows]
    return {
        "מספר_תחזיות": len(rows),
        "פגיעות": hits,
        "שיעור_פגיעה_אחוז": _r(100 * hits / len(rows), 1),
        "תשואה_ממוצעת_לכיוון_אחוז": _r(mean(returns)),
        "חציון_תשואה_לכיוון_אחוז": _r(median(returns)),
    }


def _window_stats(tests, n):
    rows = tests[-n:] if len(tests) > n else tests[:]
    if not rows:
        return {"מספר_תחזיות": 0}
    hits = sum(1 for x in rows if x["פגיעה"])
    returns = [x["תשואה_לכיוון_אחוז"] for x in rows]
    potentials = [x["פוטנציאל_חזוי_אחוז"] for x in rows]
    return {
        "מספר_תחזיות": len(rows),
        "שיעור_פגיעה_אחוז": _r(100 * hits / len(rows), 1),
        "תשואה_ממוצעת_לכיוון_אחוז": _r(mean(returns)),
        "חציון_תשואה_לכיוון_אחוז": _r(median(returns)),
        "פוטנציאל_חזוי_ממוצע_אחוז": _r(mean(potentials)),
    }


def _confidence_bins(tests):
    bins = [
        ("60-64.9", 60.0, 65.0),
        ("65-69.9", 65.0, 70.0),
        ("70-79.9", 70.0, 80.0),
        ("80+", 80.0, 101.0),
    ]
    out = []
    for label, lo, hi in bins:
        rows = [x for x in tests if lo <= x["ביטחון_גולמי_אחוז"] < hi]
        if not rows:
            continue
        hits = sum(1 for x in rows if x["פגיעה"])
        predicted = mean(x["ביטחון_גולמי_אחוז"] for x in rows)
        observed = 100 * hits / len(rows)
        out.append({
            "טווח_ביטחון": label,
            "מספר_תחזיות": len(rows),
            "ביטחון_גולמי_ממוצע_אחוז": _r(predicted, 1),
            "שיעור_פגיעה_נצפה_אחוז": _r(observed, 1),
            "פער_כיול_אחוז": _r(observed - predicted, 1),
        })
    return out


def _max_losing_streak(tests):
    current = 0
    worst = 0
    for x in tests:
        if x["תשואה_לכיוון_אחוז"] <= 0:
            current += 1
            worst = max(worst, current)
        else:
            current = 0
    return worst


def run_walk_forward(rows, min_train=80):
    """
    בדיקת תחזית יומית Out-of-Sample.
    אין כאן עדיין Backtest מלא של כניסה/יציאה תוך-יומית, עלויות, spread או slippage.
    """
    eligible_days = 0
    abstained = 0
    tests = []

    for end in range(min_train, len(rows) - 1):
        train = rows[:end + 1]
        target = rows[end + 1]
        pred = forecast_daily(train)

        if pred.get("status") != "תקין":
            continue

        eligible_days += 1
        direction = pred.get("כיוון")

        if direction not in ("קנייה", "מכירה"):
            abstained += 1
            continue

        body = _pct(target["open"], target["close"])
        signed_return = body if direction == "קנייה" else -body
        actual = "קנייה" if body > 0 else "מכירה" if body < 0 else "ללא עסקה"

        raw_conf = float(pred.get("ביטחון_גולמי_אחוז") or 0)
        predicted_potential = float(pred.get("פוטנציאל_משוער_אחוז") or 0)

        tests.append({
            "תאריך": str(target["date"]),
            "תחזית": direction,
            "בפועל": actual,
            "פגיעה": signed_return > 0,
            "ביטחון_גולמי_אחוז": _r(raw_conf, 1),
            "פוטנציאל_חזוי_אחוז": _r(predicted_potential),
            "תנועת_פתיחה_לסגירה_בפועל_אחוז": _r(body),
            "תשואה_לכיוון_אחוז": _r(signed_return),
        })

    if not tests:
        return {
            "סטטוס": "אין מספיק בדיקות",
            "ימים_כשירים": eligible_days,
            "מספר_תחזיות": 0,
            "ללא_עסקה": abstained,
        }

    hits = sum(1 for x in tests if x["פגיעה"])
    returns = [x["תשואה_לכיוון_אחוז"] for x in tests]
    raw_probs = [x["ביטחון_גולמי_אחוז"] / 100 for x in tests]
    outcomes = [1.0 if x["פגיעה"] else 0.0 for x in tests]
    brier = mean((p - y) ** 2 for p, y in zip(raw_probs, outcomes))

    coverage = 100 * len(tests) / eligible_days if eligible_days else 0

    return {
        "סטטוס": "תקין",
        "סוג_בדיקה": "אימות תחזית יומית Out-of-Sample",
        "ימים_כשירים": eligible_days,
        "מספר_תחזיות": len(tests),
        "ללא_עסקה": abstained,
        "כיסוי_תחזיות_אחוז": _r(coverage, 1),
        "פגיעות": hits,
        "שיעור_פגיעה_out_of_sample_אחוז": _r(100 * hits / len(tests), 1),
        "תשואה_ממוצעת_לכיוון_אחוז": _r(mean(returns)),
        "חציון_תשואה_לכיוון_אחוז": _r(median(returns)),
        "אחוז_תחזיות_עם_תשואה_חיובית": _r(100 * sum(r > 0 for r in returns) / len(returns), 1),
        "רצף_הפסדים_מקסימלי": _max_losing_streak(tests),
        "Brier_לביטחון_הגולמי": _r(brier, 4),
        "LONG": _direction_stats(tests, "קנייה"),
        "SHORT": _direction_stats(tests, "מכירה"),
        "חלונות_אחרונים": {
            "20": _window_stats(tests, 20),
            "60": _window_stats(tests, 60),
            "120": _window_stats(tests, 120),
            "250": _window_stats(tests, 250),
        },
        "בדיקת_כיול_ראשונית": _confidence_bins(tests),
        "בדיקות_אחרונות": tests[-10:],
        "הערה": (
            "זהו אימות של תחזית הכיוון היומית בלבד. "
            "הנתון אינו רווח מסחרי בפועל ואינו כולל spread, slippage או כללי כניסה/יציאה תוך-יומיים. "
            "ביטחון גולמי אינו מוצג כהסתברות מכוילת."
        ),
    }
