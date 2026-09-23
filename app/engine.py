from collections import defaultdict
from statistics import median


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


def format_time(minutes):
    minutes = int(minutes)

    hour = minutes // 60
    minute = minutes % 60

    return f"{hour:02d}:{minute:02d} ET"


def forecast(ticker, rows):
    if not rows:
        raise ValueError("אין נתונים")

    # חלוקה לימי מסחר
    by_day = defaultdict(list)

    for row in rows:
        minute = row.get("minute")

        if minute is None:
            continue

        # שעות המסחר הרגילות בארה"ב:
        # 09:30–16:00 ET
        if 570 <= minute <= 960:
            by_day[row["day"]].append(row)

    daily = []

    for day_rows in by_day.values():
        if len(day_rows) < 100:
            continue

        day_rows.sort(key=lambda x: x["ts"])

        opening = float(day_rows[0]["open"])

        if opening <= 0:
            continue

        high_row = max(
            day_rows,
            key=lambda x: float(x["high"])
        )

        low_row = min(
            day_rows,
            key=lambda x: float(x["low"])
        )

        high = float(high_row["high"])
        low = float(low_row["low"])

        daily.append({
            "up": (high / opening - 1) * 100,
            "down": (low / opening - 1) * 100,
            "high_time": high_row["minute"],
            "low_time": low_row["minute"]
        })

    if len(daily) < 2:
        raise ValueError("אין מספיק היסטוריית דקות")

    # משתמשים בעד 20 ימי המסחר האחרונים
    recent = daily[-20:]

    up_moves = [d["up"] for d in recent]
    down_moves = [d["down"] for d in recent]

    high_times = [d["high_time"] for d in recent]
    low_times = [d["low_time"] for d in recent]

    last = rows[-1]

    reference = float(last["close"])
    last_open = float(last["open"])

    buy = reference >= last_open

    predicted_high = reference * (
        1 + percentile(up_moves, 0.70) / 100
    )

    predicted_low = reference * (
        1 + percentile(down_moves, 0.30) / 100
    )

    median_high_time = median(high_times)
    median_low_time = median(low_times)

    if buy:
        exit_price = predicted_high * 0.997
        entry_time = median_low_time
        exit_time = median_high_time
        potential = abs(
            predicted_high / reference - 1
        ) * 100
    else:
        exit_price = predicted_low * 1.003
        entry_time = median_high_time
        exit_time = median_low_time
        potential = abs(
            predicted_low / reference - 1
        ) * 100

    return {
        "ticker": ticker,
        "action": "קנייה" if buy else "מכירה",
        "entry_price": round(reference, 3),
        "exit_price": round(exit_price, 3),
        "entry_time": format_time(entry_time),
        "exit_time": format_time(exit_time),
        "predicted_high": round(predicted_high, 3),
        "predicted_low": round(predicted_low, 3),
        "potential": round(potential, 2)
    }
