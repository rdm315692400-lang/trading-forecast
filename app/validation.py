def anti_leak(snapshot):
    return all(
        b.timestamp_utc <= snapshot.snapshot_time_utc
        and b.received_at_utc <= snapshot.snapshot_time_utc
        for b in snapshot.bars
    )


def _touches(bar, low, high):
    return float(bar.low) <= float(high) and float(bar.high) >= float(low)


def evaluate_frozen_xv(bars, forecast_time_utc, x, v):
    """Evaluate a frozen forecast without changing its price or time windows."""
    future=[b for b in bars if b.received_at_utc>forecast_time_utc]
    xbar=next((b for b in future
               if x.time_start_utc <= b.received_at_utc <= x.time_end_utc
               and _touches(b,x.price_low,x.price_high)),None)
    after=[b for b in future if xbar and b.received_at_utc>xbar.received_at_utc]
    vbar=next((b for b in after
               if v.time_start_utc <= b.received_at_utc <= v.time_end_utc
               and _touches(b,v.price_low,v.price_high)),None)
    return {
        "x_zone_touched":bool(xbar),
        "v_zone_touched_after_x":bool(vbar),
        "actual_x_time_utc":xbar.received_at_utc.isoformat() if xbar else None,
        "actual_v_time_utc":vbar.received_at_utc.isoformat() if vbar else None,
    }
