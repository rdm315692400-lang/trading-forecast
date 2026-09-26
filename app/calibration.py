from dataclasses import dataclass, asdict
from math import sqrt
from statistics import mean

@dataclass(frozen=True)
class CalibrationReport:
    samples: int
    direction_brier: float | None
    terminal_mae_pct_points: float | None
    upside_mae_pct_points: float | None
    downside_mae_pct_points: float | None
    calibration_status: str
    holdout_used: bool = False

    def to_dict(self):
        return asdict(self)

def _mae(pred, actual):
    pairs = [(float(p), float(a)) for p, a in zip(pred, actual)
             if p is not None and a is not None]
    return mean(abs(p-a) for p,a in pairs) if pairs else None

def _brier(probabilities, outcomes):
    pairs = [(float(p), 1.0 if bool(y) else 0.0)
             for p,y in zip(probabilities, outcomes)
             if p is not None and y is not None]
    return mean((p-y)**2 for p,y in pairs) if pairs else None

def reliability_bins(probabilities, outcomes, bins=10):
    """Validation-only reliability table; never fit or inspect holdout here."""
    buckets = [[] for _ in range(int(bins))]
    for p, y in zip(probabilities, outcomes):
        if p is None or y is None:
            continue
        p = max(0.0, min(1.0, float(p)))
        idx = min(int(bins)-1, int(p * int(bins)))
        buckets[idx].append((p, 1.0 if bool(y) else 0.0))
    out = []
    for i, rows in enumerate(buckets):
        if not rows:
            continue
        out.append({
            "bin": i,
            "n": len(rows),
            "mean_predicted_probability": mean(p for p,_ in rows),
            "observed_frequency": mean(y for _,y in rows),
        })
    return out

def calibration_report(predictions, validation_rows):
    """
    Score ONLY the chronological validation partition.
    This function does not train, tune, or inspect the final holdout.
    """
    if len(predictions) != len(validation_rows):
        raise ValueError("prediction_validation_length_mismatch")

    probs = [p.probability_up for p in predictions]
    outcomes = [float(r["future_terminal_return_pct"]) > 0 for r in validation_rows]

    return {
        "report": CalibrationReport(
            samples=len(predictions),
            direction_brier=_brier(probs, outcomes),
            terminal_mae_pct_points=_mae(
                [p.expected_terminal_return_pct for p in predictions],
                [r["future_terminal_return_pct"] for r in validation_rows],
            ),
            upside_mae_pct_points=_mae(
                [p.expected_upside_reach_pct for p in predictions],
                [r["future_upside_reach_pct"] for r in validation_rows],
            ),
            downside_mae_pct_points=_mae(
                [p.expected_downside_reach_pct for p in predictions],
                [r["future_downside_reach_pct"] for r in validation_rows],
            ),
            calibration_status="VALIDATION_ONLY_NOT_FINAL_CALIBRATED",
        ).to_dict(),
        "direction_reliability": reliability_bins(probs, outcomes),
        "holdout_used": False,
    }

def freeze_model_spec(model, validation_result, version="stage3-final-candidate"):
    """
    Freeze the selected design BEFORE final holdout evaluation.
    No holdout metric is accepted as an input here.
    """
    metadata = dict(model.metadata())
    return {
        "version": str(version),
        "model_metadata": metadata,
        "validation_result": validation_result,
        "frozen": True,
        "holdout_used": False,
        "rule": (
            "After this spec is frozen, the final holdout may be evaluated once. "
            "Any model/feature/target change after seeing holdout results creates a new research cycle."
        ),
    }
