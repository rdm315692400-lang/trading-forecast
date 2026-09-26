from dataclasses import dataclass, asdict
from math import exp, sqrt


FEATURE_NAMES = (
    "return_1m_pct",
    "return_5m_pct",
    "return_15m_pct",
    "return_30m_pct",
    "return_60m_pct",
    "momentum_acceleration_pct",
    "realized_abs_15m_pct",
    "realized_abs_30m_pct",
    "realized_abs_60m_pct",
    "volatility_30m_pct",
    "range_15m_pct",
    "range_30m_pct",
    "range_60m_pct",
    "volume_ratio_30m",
    "position_in_30m_range",
    "position_in_60m_range",
    "distance_from_visible_open_pct",
    "distance_from_visible_high_pct",
    "distance_from_visible_low_pct",
    "higher_highs_15m",
    "higher_lows_15m",
)


@dataclass(frozen=True)
class ModelPrediction:
    horizon_minutes: int
    expected_terminal_return_pct: float
    expected_upside_reach_pct: float
    expected_downside_reach_pct: float
    probability_up: float
    probability_down: float
    analogue_count: int
    status: str

    def to_dict(self):
        return asdict(self)


def _median(values):
    xs = sorted(float(v) for v in values)
    if not xs:
        return 0.0
    n = len(xs)
    m = n // 2
    return xs[m] if n % 2 else (xs[m - 1] + xs[m]) / 2.0


def _robust_scales(rows):
    scales = {}
    for name in FEATURE_NAMES:
        values = [float(r[name]) for r in rows]
        med = _median(values)
        deviations = [abs(v - med) for v in values]
        mad = _median(deviations)
        # Prevent a nearly constant feature from dominating distance.
        scales[name] = max(mad * 1.4826, 1e-4)
    return scales


class EmpiricalForecastModel:
    """
    Stage 3D model.

    Fit ONLY on the chronological training partition produced by the Stage 3D dataset.
    Validation data may evaluate/tune later versions, but is never added here.
    Holdout must remain untouched until the model design is frozen.

    The model is intentionally transparent: nearest historical states are
    weighted by similarity, and future labels come from those training rows.
    """

    def __init__(self, max_neighbors=120, min_neighbors=25):
        self.max_neighbors = int(max_neighbors)
        self.min_neighbors = int(min_neighbors)
        self._rows_by_horizon = {}
        self._scales_by_horizon = {}
        self._fitted = False

    def fit(self, train_rows):
        grouped = {}
        for row in train_rows:
            h = int(row["horizon_minutes"])
            grouped.setdefault(h, []).append(dict(row))

        self._rows_by_horizon = {}
        self._scales_by_horizon = {}

        for h, rows in grouped.items():
            if len(rows) < self.min_neighbors:
                continue
            self._rows_by_horizon[h] = rows
            self._scales_by_horizon[h] = _robust_scales(rows)

        self._fitted = bool(self._rows_by_horizon)
        return self

    def _distance(self, row, features, scales):
        total = 0.0
        for name in FEATURE_NAMES:
            a = float(row[name])
            b = float(features[name])
            s = float(scales[name])
            total += ((a - b) / s) ** 2
        return sqrt(total)

    def predict(self, features, horizon_minutes):
        if not self._fitted:
            raise RuntimeError("model_not_fitted")

        h = int(horizon_minutes)
        rows = self._rows_by_horizon.get(h)
        scales = self._scales_by_horizon.get(h)
        if not rows or not scales:
            return ModelPrediction(h, 0.0, 0.0, 0.0, 0.5, 0.5, 0, "horizon_not_fitted")

        ranked = [
            (self._distance(row, features, scales), row)
            for row in rows
        ]
        ranked.sort(key=lambda item: item[0])
        neighbors = ranked[:min(self.max_neighbors, len(ranked))]

        if len(neighbors) < self.min_neighbors:
            return ModelPrediction(h, 0.0, 0.0, 0.0, 0.5, 0.5,
                                   len(neighbors), "insufficient_neighbors")

        # Adaptive kernel: distance of the furthest selected neighbor.
        bandwidth = max(neighbors[-1][0], 1e-9)
        weights = [exp(-0.5 * (d / bandwidth) ** 2) for d, _ in neighbors]
        sw = sum(weights)
        if sw <= 0:
            weights = [1.0] * len(neighbors)
            sw = float(len(neighbors))

        def wmean(label):
            return sum(w * float(row[label]) for w, (_, row) in zip(weights, neighbors)) / sw

        terminal = wmean("future_terminal_return_pct")
        upside = max(0.0, wmean("future_upside_reach_pct"))
        downside = max(0.0, wmean("future_downside_reach_pct"))

        up_weight = sum(
            w for w, (_, row) in zip(weights, neighbors)
            if float(row["future_terminal_return_pct"]) > 0
        )
        down_weight = sum(
            w for w, (_, row) in zip(weights, neighbors)
            if float(row["future_terminal_return_pct"]) < 0
        )
        directional_weight = up_weight + down_weight
        p_up = up_weight / directional_weight if directional_weight > 0 else 0.5
        p_up = max(0.01, min(0.99, p_up))

        return ModelPrediction(
            horizon_minutes=h,
            expected_terminal_return_pct=terminal,
            expected_upside_reach_pct=upside,
            expected_downside_reach_pct=downside,
            probability_up=p_up,
            probability_down=1.0 - p_up,
            analogue_count=len(neighbors),
            status="ok",
        )

    def fitted_horizons(self):
        return sorted(self._rows_by_horizon)

    def metadata(self):
        return {
            "stage": "3D",
            "model_type": "empirical_similarity_regression_rich_features",
            "feature_names": list(FEATURE_NAMES),
            "fitted_horizons": self.fitted_horizons(),
            "max_neighbors": self.max_neighbors,
            "min_neighbors": self.min_neighbors,
            "calibrated": False,
            "holdout_used": False,
        }
