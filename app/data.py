    low_price = float(
        row.get("l") or 0
    )

    close_price = float(
        row.get("c") or 0
    )

    if (
        open_price <= 0
        or high_price <= 0
        or low_price <= 0
        or close_price <= 0
    ):
        continue

    result.append({
        "ts": timestamp,
        "date": dt.date(),
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": close_price,
        "volume": float(
            row.get("v") or 0
        ),
        "vwap": row.get("vw"),
    })

    return result[-250:]


# ==========================================
# DAILY FEATURES
# ==========================================

def build_daily_features(rows):
    features = []

    for index in range(1, len(rows)):
        previous = rows[index - 1]
        current = rows[index]

        previous_close = previous["close"]
        current_open = current["open"]
        current_close = current["close"]
        current_high = current["high"]
        current_low = current["low"]

        if previous_close <= 0:
            continue

        gap_percent = (
            (current_open / previous_close) - 1
        ) * 100

        day_change_percent = (
            (current_close / current_open) - 1
        ) * 100

        day_range_percent = (
            (current_high - current_low)
            / current_open
        ) * 100

        if (
            gap_percent > 0
            and day_change_percent > 0
        ):
            behavior = "CONTINUATION"

        elif (
            gap_percent < 0
            and day_change_percent < 0
        ):
            behavior = "CONTINUATION"

        elif (
            gap_percent > 0
            and day_change_percent < 0
        ):
            behavior = "REVERSAL"

        elif (
            gap_percent < 0
            and day_change_percent > 0
        ):
            behavior = "REVERSAL"

        else:
            behavior = "NEUTRAL"

        features.append({
            "date": current["date"],
            "previous_close": previous_close,
            "open": current_open,
            "high": current_high,
            "low": current_low,
            "close": current_close,
            "volume": current["volume"],
            "gap_percent": gap_percent,
            "day_change_percent":
                day_change_percent,
            "day_range_percent":
                day_range_percent,
            "behavior": behavior,
        })

    return features
