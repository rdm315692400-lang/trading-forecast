from zoneinfo import ZoneInfo

ISRAEL_TZ = ZoneInfo("Asia/Jerusalem")
US_TZ = ZoneInfo("America/New_York")

def profile(symbol):
    # כל 45 המניות המחוברות כרגע הן מניות ארה"ב במסחר רגיל 09:30–16:00 ET.
    # מדדים/סחורות אינם מסומנים כמחוברים עד אימות מקור הנתונים והסמל.
    return {
        "symbol": symbol,
        "market_timezone": "America/New_York",
        "market_open_minute": 9 * 60 + 30,
        "market_close_minute": 16 * 60,
        "connected": True,
    }

def minute_text(minute):
    minute = int(minute)
    return f"{minute//60:02d}:{minute%60:02d}"

def market_to_israel(day, minute):
    local = __import__("datetime").datetime.combine(
        day,
        __import__("datetime").time(minute // 60, minute % 60),
        tzinfo=US_TZ,
    )
    return local.astimezone(ISRAEL_TZ).strftime("%H:%M")
