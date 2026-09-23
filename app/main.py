from collections import defaultdict
from statistics import mean, median


# ==========================================
# BASIC HELPERS
# ==========================================

def percentile(values, p):
    if not values:
        return 0.0

    values = sorted(float(v) for v in values)

    if len(values) == 1:
        return values[0]

    position = (len(values) - 1) * p
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)

    weight = position - lower

    return (
        values[lower] * (1 - weight)
        + values[upper] * weight
    )


def safe_mean(values):
    values = [
        float(v)
        for v in values
        if v is not None
    ]

    if not values:
        return 0.0

    return mean(values)


def format_time(minutes):
    minutes = int(minutes)

    hour = minutes // 60
    minute = minutes % 60

    return f"{hour:02d}:{minute:02d} ET"


# ==========================================
# BUILD DAILY DATA FROM MINUTE DATA
# ==========================================

def build_daily_sessions(rows):
    by_day = defaultdict(list)

    for row in rows:
        minute = row.get("minute")

        if minute is None:
            continue

        # מסחר רגיל בארה"ב
        if 570 <= minute <= 960:
            by_day[row["day"]].append(row)

    sessions = []

    for day, day_rows in by_day.items():

        if len(day_rows) < 100:
            continue

        day_rows.sort(
            key=lambda x: x["ts"]
        )

        open_price = float(
            day_rows[0]["open"]
        )

        close_price = float(
            day_rows[-1]["close"]
        )

        high_row = max(
            day_rows,
            key=lambda x: float(x["high"])
        )

        low_row = min(
            day_rows,
            key=lambda x: float(x["low"])
        )

        high_price = float(
            high_row["high"]
        )

        low_price = float(
            low_row["low"]
        )

        if open_price <= 0:
            continue

        change_percent = (
            (close_price / open_price) - 1
        ) * 100

        range_percent = (
            (high_price - low_price)
            / open_price
        ) * 100

        sessions.append({
            "day": day,
            "open": open_price,
            "high": high_price,
            "low": low_price,
            "close": close_price,
            "change_percent": change_percent,
            "range_percent": range_percent,
            "high_time": high_row["minute"],
            "low_time": low_row["minute"],
        })

    sessions.sort(
        key=lambda x: x["day"]
    )

    return sessions


# ==========================================
# MARKET STATE
# ==========================================

def detect_market_state(sessions):

    if len(sessions) < 5:
        return {
            "trend": "לא ידוע",
            "status": "אין מספיק נתונים",
            "strength": 0.0
        }

    recent = sessions[-5:]

    closes = [
        x["close"]
        for x in recent
    ]

    ranges = [
        x["range_percent"]
        for x in recent
    ]

    last = recent[-1]

    avg_range = safe_mean(ranges[:-1])

    if avg_range <= 0:
        avg_range = last["range_percent"]

    first_close = closes[0]
    last_close = closes[-1]

    trend_change = (
        (last_close / first_close) - 1
    ) * 100

    # התכווצות / דשדוש
    compression = (
        last["range_percent"]
        < avg_range * 0.70
    )

    # יום חריג ביחס לטווח האחרון
    expansion = (
        last["range_percent"]
        > avg_range * 1.40
    )

    if compression:

        status = "דשדוש / התכווצות"

    elif expansion and last["change_percent"] > 0:

        status = "תנועה חזקה מעלה"

    elif expansion and last["change_percent"] < 0:

        status = "תנועה חזקה מטה"

    elif abs(last["change_percent"]) < 0.30:

        status = "דשדוש"

    elif trend_change > 1:

        status = "מגמה עולה"

    elif trend_change < -1:

        status = "מגמה יורדת"

    else:

        status = "מצב מעורב"

    if trend_change > 0.50:

        trend = "עולה"

    elif trend_change < -0.50:

        trend = "יורדת"

    else:

        trend = "ניטרלית"

        strength = min(
        abs(trend_change),
        10.0
    )
