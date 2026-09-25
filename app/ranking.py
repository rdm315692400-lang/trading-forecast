def rank_forecasts(items):
    """Primary objective: greatest FUTURE remaining X->V percentage."""
    usable=[
        dict(x) for x in items
        if x.get("expected_future_x_to_v_pct") is not None
    ]
    usable.sort(
        key=lambda x:(
            float(x.get("expected_future_x_to_v_pct",0.0)),
            str(x.get("forecast_time_utc",""))
        ),
        reverse=True
    )
    for i,row in enumerate(usable,1):
        row["rank"]=i
    return usable

def leader(items):
    ranked=rank_forecasts(items)
    return ranked[0] if ranked else None
