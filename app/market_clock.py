from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from .asset_registry import get_asset

def _hhmm(value: str):
    h, m = map(int, value.split(":"))
    return h, m

def session_bounds_utc(asset_id: str, market_day: date):
    asset = get_asset(asset_id)
    if not asset:
        raise ValueError(f"Unknown asset: {asset_id}")
    tz = ZoneInfo(asset.market_timezone)
    oh, om = _hhmm(asset.session_open)
    ch, cm = _hhmm(asset.session_close)
    start = datetime(market_day.year, market_day.month, market_day.day, oh, om, tzinfo=tz)
    end = datetime(market_day.year, market_day.month, market_day.day, ch, cm, tzinfo=tz)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)

def market_time_to_utc(asset_id: str, market_day: date, hhmm: str):
    asset = get_asset(asset_id)
    if not asset:
        raise ValueError(f"Unknown asset: {asset_id}")
    h, m = _hhmm(hhmm)
    local = datetime(market_day.year, market_day.month, market_day.day, h, m,
                     tzinfo=ZoneInfo(asset.market_timezone))
    return local.astimezone(timezone.utc)
