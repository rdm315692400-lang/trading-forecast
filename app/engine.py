from collections import defaultdict
from statistics import mean, median


# ==========================================
# SETTINGS
# ==========================================

MARKET_OPEN = 9 * 60 + 30
MARKET_CLOSE = 16 * 60

MIN_MATCHES = 3
MAX_MATCHES = 10


# ==========================================
# HELPERS
# ==========================================

def percent_change(start, end):
    if not start:
        return 0.0

    return ((end / start) - 1) * 100


def safe_mean(values):
    values = [
        value
        for value in values
        if value is not None
    ]

    if not values:
        return 0.0

    return mean(values)


def safe_median(values):
    values = [
        value
        for value in values
        if value is not None
    ]

    if not values:
        return 0.0

    return median(values)


# ==========================================
# BUILD DAILY SESSIONS
# ==========================================

def build_sessions(rows):
    grouped = defaultdict(list)

    for row in rows:
        day = row.get("day")
        minute = row.get("minute")

        if day is None or minute is None:
            continue

        if not (
            MARKET_OPEN
            <= minute
            <= MARKET_CLOSE
        ):
            continue

        grouped[day].append(row)

    sessions = []

    for day in sorted(grouped.keys()):
        candles = sorted(
            grouped[day],
            key=lambda item: item["minute"],
        )

        if len(candles) < 20:
            continue

        first = candles[0]
        last = candles[-1]

        open_price = float(
            first.get("open") or 0
        )

        close_price = float(
            last.get("close") or 0
        )

        highs = [
            float(item.get("high") or 0)
            for item in candles
        ]

        lows = [
            float(item.get("low") or 0)
            for item in candles
            if float(item.get("low") or 0) > 0
        ]

        if (
            open_price <= 0
            or close_price <= 0
            or not highs
            or not lows
        ):
            continue

        high_price = max(highs)
        low_price = min(lows)

        change_percent = percent_change(
            open_price,
            close_price,
        )

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
            "candles": candles,
        })

    return sessions


# ==========================================
# MARKET STATE
# ==========================================

def detect_market_state(sessions):
    if len(sessions) < 3:
        return "אין מספיק נתונים"

    recent = sessions[-3:]

    changes = [
        item["change_percent"]
        for item in recent
    ]

    ranges = [
        item["range_percent"]
        for item in recent
    ]

    avg_change = safe_mean(changes)
    avg_range = safe_mean(ranges)

    last_change = changes[-1]

    if (
        avg_change > 0.6
        and last_change > 0
    ):
        return "מגמת עלייה"

    if (
        avg_change < -0.6
        and last_change < 0
    ):
        return "מגמת ירידה"

    if (
        abs(avg_change) < 0.35
        and avg_range < 2.0
    ):
        return "דשדוש"

    if (
        avg_change > 0
        and last_change < 0
    ):
        return "תיקון בתוך מגמת עלייה"

    if (
        avg_change < 0
        and last_change > 0
    ):
        return "תיקון בתוך מגמת ירידה"

    return "מצב מעורב"


# ==========================================
# FIND HISTORICAL MATCHES
# ==========================================

def find_historical_matches(sessions):
    if len(sessions) < 4:
        return []

    current = sessions[-1]

    candidates = []

    for index in range(
        0,
        len(sessions) - 2
    ):
        historical = sessions[index]
        next_session = sessions[index + 1]

        change_distance = abs(
            historical["change_percent"]
            - current["change_percent"]
        )

        range_distance = abs(
            historical["range_percent"]
            - current["range_percent"]
        )

        distance = (
            change_distance * 0.60
            + range_distance * 0.40
        )

        candidates.append({
            "distance": distance,
            "historical": historical,
            "next": next_session,
        })

    candidates.sort(
        key=lambda item: item["distance"]
    )

    return candidates[:MAX_MATCHES]


# ==========================================
# NEXT SESSION TIMING
# ==========================================

def analyze_next_session(session):
    candles = session["candles"]

    if not candles:
        return None

    open_price = session["open"]

    if open_price <= 0:
        return None

    best_long = None
    best_short = None

    for candle in candles:
        minute = candle["minute"]

        high_price = float(
            candle.get("high") or 0
        )

        low_price = float(
            candle.get("low") or 0
        )

        long_move = (
            (high_price / open_price) - 1
        ) * 100

        short_move = (
            (open_price / low_price) - 1
        ) * 100 if low_price > 0 else 0

        if (
            best_long is None
            or long_move
            > best_long["move"]
        ):
            best_long = {
                "move": long_move,
                "minute": minute,
                "price": high_price,
            }

        if (
            best_short is None
            or short_move
            > best_short["move"]
        ):
            best_short = {
                "move": short_move,
                "minute": minute,
                "price": low_price,
            }

    return {
        "change_percent":
            session["change_percent"],
        "range_percent":
            session["range_percent"],
        "best_long": best_long,
        "best_short": best_short,
    }


# ==========================================
# FORMAT TIME
# ==========================================

def minute_to_time(minute):
    if minute is None:
        return None

    hour = int(minute // 60)
    minute_part = int(minute % 60)

    return (
        f"{hour:02d}:"
        f"{minute_part:02d}"
    )


# ==========================================
# MAIN FORECAST
# ==========================================

def forecast(symbol, rows):
    sessions = build_sessions(rows)

    if len(sessions) < 4:
        return {
            "symbol": symbol,
            "status": "אין מספיק היסטוריה",
            "historical_sessions":
                len(sessions),
        }

    current = sessions[-1]

    market_status = detect_market_state(
        sessions
    )

    matches = find_historical_matches(
        sessions
    )

    analyzed = []

    for match in matches:
        result = analyze_next_session(
            match["next"]
        )

        if result is not None:
            analyzed.append(result)

    if len(analyzed) < MIN_MATCHES:
        return {
            "symbol": symbol,
            "status":
                "אין מספיק מקרים דומים",
            "market_status":
                market_status,
            "historical_matches":
                len(analyzed),
        }

    next_changes = [
        item["change_percent"]
        for item in analyzed
    ]

    positive = sum(
        1
        for value in next_changes
        if value > 0
    )

    negative = sum(
        1
        for value in next_changes
        if value < 0
    )

    total = len(next_changes)

    long_probability = (
        positive / total
    ) * 100

    short_probability = (
        negative / total
    ) * 100

    if long_probability >= 60:
        direction = "LONG"
        confidence = long_probability

    elif short_probability >= 60:
        direction = "SHORT"
        confidence = short_probability

    else:
        direction = "ללא עסקה"
        confidence = max(
            long_probability,
            short_probability,
        )

    current_price = current["close"]

    expected_change = safe_median(
        next_changes
    )

    expected_range = safe_median([
        item["range_percent"]
        for item in analyzed
    ])

    long_moves = [
        item["best_long"]["move"]
        for item in analyzed
        if item["best_long"] is not None
    ]

    short_moves = [
        item["best_short"]["move"]
        for item in analyzed
        if item["best_short"] is not None
    ]

    long_times = [
        item["best_long"]["minute"]
        for item in analyzed
        if item["best_long"] is not None
    ]

    short_times = [
        item["best_short"]["minute"]
        for item in analyzed
        if item["best_short"] is not None
    ]

    expected_entry_price = current_price
    expected_entry_time = "09:30"

    expected_exit_price = current_price
    expected_exit_time = None
    potential_percent = 0.0

    if direction == "LONG":
        potential_percent = max(
            0.0,
            safe_median(long_moves)
        )

        expected_exit_price = (
            current_price
            * (
                1
                + potential_percent / 100
            )
        )

        expected_exit_time = (
            minute_to_time(
                safe_median(long_times)
            )
        )

    elif direction == "SHORT":
        potential_percent = max(
            0.0,
            safe_median(short_moves)
        )

        expected_exit_price = (
            current_price
            * (
                1
                - potential_percent / 100
            )
        )

        expected_exit_time = (
            minute_to_time(
                safe_median(short_times)
            )
        )

    trend_forecast = "ניטרלי"

    if expected_change > 0.25:
        trend_forecast = "עלייה"

    elif expected_change < -0.25:
        trend_forecast = "ירידה"

    return {
        "symbol": symbol,
        "trend_forecast":
            trend_forecast,
        "market_status":
            market_status,
        "direction":
            direction,
        "expected_entry_price":
            round(
                expected_entry_price,
                3
            ),
        "expected_entry_time":
            expected_entry_time,
        "expected_exit_price":
            round(
                expected_exit_price,
                3
            ),
        "expected_exit_time":
            expected_exit_time,
        "potential_percent":
            round(
                potential_percent,
                2
            ),
        "model_confidence":
            round(
                confidence,
                1
            ),
        "historical_matches":
            total,
        "expected_next_change":
            round(
                expected_change,
                2
            ),
        "expected_next_range":
            round(
                expected_range,
                2
            ),
        "current_reference_price":
            round(
                current_price,
                3
            ),
  }
