from statistics import mean

from .forecast_model import FEATURE_NAMES, EmpiricalForecastModel, stage_3e_baselines


def _safe_mean(xs):
    return mean(xs) if xs else None


def _direction_from_terminal(value):
    value = float(value)
    if value > 0:
        return "LONG"
    if value < 0:
        return "SHORT"
    return "NO_TRADE"


def _actual_for_direction(row, direction):
    if direction == "LONG":
        return float(row["future_long_x_to_v_pct"])
    if direction == "SHORT":
        return float(row["future_short_x_to_v_pct"])
    return 0.0


def _oracle(row):
    long_v = float(row["future_long_x_to_v_pct"])
    short_v = float(row["future_short_x_to_v_pct"])
    if long_v >= short_v:
        return "LONG", long_v
    return "SHORT", short_v


def _summarize_policy(records):
    if not records:
        return {"samples": 0}

    chosen = [r["actual_chosen_x_to_v_pct"] for r in records]
    oracle = [r["oracle_x_to_v_pct"] for r in records]
    captures = [
        (r["actual_chosen_x_to_v_pct"] / r["oracle_x_to_v_pct"])
        for r in records if r["oracle_x_to_v_pct"] > 0
    ]
    correct = [
        1.0 if r["chosen_direction"] == r["oracle_direction"] else 0.0
        for r in records if r["chosen_direction"] != "NO_TRADE"
    ]
    pred_err = [
        abs(r["predicted_x_to_v_pct"] - r["actual_chosen_x_to_v_pct"])
        for r in records if r["predicted_x_to_v_pct"] is not None
    ]

    return {
        "samples": len(records),
        "direction_selection_accuracy_vs_oracle": _safe_mean(correct),
        "mean_actual_chosen_x_to_v_pct": _safe_mean(chosen),
        "mean_oracle_x_to_v_pct": _safe_mean(oracle),
        "mean_capture_ratio_of_oracle": _safe_mean(captures),
        "mean_abs_predicted_x_to_v_error_pct_points": _safe_mean(pred_err),
    }


def validate_xv(train_rows, validation_rows):
    """
    Stage 3 X->V validation.

    Fits the empirical model on TRAIN only and scores VALIDATION only.
    HOLDOUT rows are not accepted by this function and are never inspected.
    """
    if not train_rows or not validation_rows:
        raise ValueError("insufficient_train_or_validation_rows")

    model = EmpiricalForecastModel().fit(train_rows)
    baselines = stage_3e_baselines()

    model_records = []
    baseline_records = {name: [] for name in baselines}
    by_horizon = {}

    for row in validation_rows:
        h = int(row["horizon_minutes"])
        features = {name: float(row[name]) for name in FEATURE_NAMES}
        oracle_direction, oracle_pct = _oracle(row)

        pred = model.predict(features, h)
        if pred.status == "ok":
            long_score = float(pred.expected_long_x_to_v_pct) * float(pred.probability_up)
            short_score = float(pred.expected_short_x_to_v_pct) * float(pred.probability_down)
            direction = "LONG" if long_score >= short_score else "SHORT"
            predicted_pct = (
                float(pred.expected_long_x_to_v_pct)
                if direction == "LONG"
                else float(pred.expected_short_x_to_v_pct)
            )
            actual_pct = _actual_for_direction(row, direction)
            rec = {
                "horizon_minutes": h,
                "chosen_direction": direction,
                "oracle_direction": oracle_direction,
                "predicted_x_to_v_pct": predicted_pct,
                "actual_chosen_x_to_v_pct": actual_pct,
                "oracle_x_to_v_pct": oracle_pct,
            }
            model_records.append(rec)
            by_horizon.setdefault(h, []).append(rec)

        for name, baseline in baselines.items():
            bp = baseline.predict(features, h)
            direction = _direction_from_terminal(bp.expected_terminal_return_pct)
            predicted_pct = (
                abs(float(bp.expected_terminal_return_pct))
                if direction != "NO_TRADE" else 0.0
            )
            baseline_records[name].append({
                "horizon_minutes": h,
                "chosen_direction": direction,
                "oracle_direction": oracle_direction,
                "predicted_x_to_v_pct": predicted_pct,
                "actual_chosen_x_to_v_pct": _actual_for_direction(row, direction),
                "oracle_x_to_v_pct": oracle_pct,
            })

    return {
        "stage": "3_XV_VALIDATION",
        "model": _summarize_policy(model_records),
        "baselines": {
            name: _summarize_policy(records)
            for name, records in baseline_records.items()
        },
        "by_horizon": {
            str(h): _summarize_policy(records)
            for h, records in sorted(by_horizon.items())
        },
        "holdout_used": False,
        "interpretation_rule": (
            "Primary metrics are future ordered X->V direction selection, "
            "realized chosen X->V magnitude, and capture ratio versus the "
            "best LONG/SHORT ordered path available in the same future horizon."
        ),
    }
