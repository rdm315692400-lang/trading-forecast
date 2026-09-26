from __future__ import annotations

import asyncio
from dataclasses import dataclass, asdict
from datetime import date, timedelta

from .asset_registry import get_asset
from .massive_provider import fetch_minute_bars
from .historical_cache import load_day, save_bars


@dataclass(frozen=True)
class BackfillWindow:
    start_day: str
    end_day: str
    requested_market_days: int
    cached_before: int
    missing_before: int
    downloaded_bars: int
    daily_documents_written: int
    status: str

    def to_dict(self):
        return asdict(self)


def market_weekdays(start_day: date, end_day: date) -> list[date]:
    out = []
    d = start_day
    while d <= end_day:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def split_calendar_windows(start_day: date, end_day: date, window_calendar_days: int = 14):
    size = max(1, min(int(window_calendar_days), 14))
    cursor = start_day
    while cursor <= end_day:
        w_end = min(cursor + timedelta(days=size - 1), end_day)
        yield cursor, w_end
        cursor = w_end + timedelta(days=1)


def cached_state(asset_id: str, start_day: date, end_day: date):
    present = []
    missing = []
    for d in market_weekdays(start_day, end_day):
        bars = load_day(asset_id, d.isoformat())
        if bars:
            present.append(d)
        else:
            missing.append(d)
    return present, missing


async def backfill_history(
    asset_id: str,
    start_day: date,
    end_day: date,
    window_calendar_days: int = 14,
    pause_seconds: float = 13.0,
    dry_run: bool = False,
):
    """
    Incremental historical cache backfill.

    Safety properties:
    - Existing cached days are never fetched again when an entire window is cached.
    - Provider requests are split into <=14-calendar-day windows.
    - Requests are sequential and paused between provider calls.
    - This module does not run forecasts and does not alter X/V logic.
    - Holidays can appear as missing before a provider request and remain missing after it.
    """
    asset_id = asset_id.upper().strip()
    asset = get_asset(asset_id)

    if not asset:
        return {"ok": False, "stage": "asset_validation", "asset": asset_id,
                "error": "unknown_asset"}
    if not asset.provider_verified:
        return {"ok": False, "stage": "asset_validation", "asset": asset_id,
                "error": "provider_mapping_not_verified"}
    if start_day > end_day:
        return {"ok": False, "stage": "date_validation", "asset": asset_id,
                "error": "start_day_after_end_day"}

    windows = []
    provider_calls = 0
    total_downloaded = 0
    total_written = 0

    for w_start, w_end in split_calendar_windows(
        start_day, end_day, window_calendar_days
    ):
        present, missing = cached_state(asset_id, w_start, w_end)
        requested_days = len(present) + len(missing)

        if not missing:
            windows.append(BackfillWindow(
                w_start.isoformat(), w_end.isoformat(), requested_days,
                len(present), 0, 0, 0, "ALREADY_CACHED"
            ))
            continue

        if dry_run:
            windows.append(BackfillWindow(
                w_start.isoformat(), w_end.isoformat(), requested_days,
                len(present), len(missing), 0, 0, "WOULD_FETCH"
            ))
            continue

        # One aggregate request for this calendar window. save_bars deduplicates
        # daily cache storage; already-cached days are not a correctness problem.
        try:
            bars = await fetch_minute_bars(asset_id, w_start, w_end)
            provider_calls += 1
        except Exception as exc:
            return {
                "ok": False,
                "stage": "provider_fetch",
                "asset": asset_id,
                "failed_window": {
                    "start_day": w_start.isoformat(),
                    "end_day": w_end.isoformat(),
                },
                "provider_calls": provider_calls + 1,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "windows": [w.to_dict() for w in windows],
            }

        written = save_bars(bars, asset.market_timezone) if bars else 0
        total_downloaded += len(bars)
        total_written += written

        windows.append(BackfillWindow(
            w_start.isoformat(), w_end.isoformat(), requested_days,
            len(present), len(missing), len(bars), written, "FETCHED"
        ))

        if w_end < end_day and pause_seconds > 0:
            await asyncio.sleep(float(pause_seconds))

    final_present, final_missing = cached_state(asset_id, start_day, end_day)

    return {
        "ok": True,
        "asset": asset_id,
        "start_day": start_day.isoformat(),
        "end_day": end_day.isoformat(),
        "dry_run": dry_run,
        "provider_calls": provider_calls,
        "downloaded_bars": total_downloaded,
        "daily_documents_written": total_written,
        "cached_market_days_after": len(final_present),
        "missing_weekdays_after": [d.isoformat() for d in final_missing],
        "windows": [w.to_dict() for w in windows],
        "forecast_logic_changed": False,
        "calibration_performed": False,
    }
