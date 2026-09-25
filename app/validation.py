def anti_leak(snapshot):
    return all(
        b.timestamp_utc <= snapshot.snapshot_time_utc
        and b.received_at_utc <= snapshot.snapshot_time_utc
        for b in snapshot.bars
    )

def evaluate_frozen_xv(bars, forecast_time_utc, x, v):
    future=[b for b in bars if b.received_at_utc>forecast_time_utc]
    xbar=next((b for b in future if b.low<=x.price_high and b.high>=x.price_low),None)
    after=[b for b in future if xbar and b.received_at_utc>xbar.received_at_utc]
    vbar=next((b for b in after if b.low<=v.price_high and b.high>=v.price_low),None)
    return {
        "x_zone_touched":bool(xbar),
        "v_zone_touched_after_x":bool(vbar),
        "actual_x_time_utc":xbar.received_at_utc.isoformat() if xbar else None,
        "actual_v_time_utc":vbar.received_at_utc.isoformat() if vbar else None,
    }
