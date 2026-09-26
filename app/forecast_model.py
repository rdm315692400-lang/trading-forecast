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
    expected_upside_peak_minute: float = 0.0
    expected_downside_peak_minute: float = 0.0
    expected_long_x_adverse_pct: float = 0.0
    expected_long_x_minute: float = 0.0
    expected_long_v_reach_pct: float = 0.0
    expected_long_v_minute: float = 0.0
    expected_long_x_to_v_pct: float = 0.0
    expected_short_x_adverse_pct: float = 0.0
    expected_short_x_minute: float = 0.0
    expected_short_v_reach_pct: float = 0.0
    expected_short_v_minute: float = 0.0
    expected_short_x_to_v_pct: float = 0.0
    long_x_adverse_q25: float = 0.0
    long_x_adverse_q75: float = 0.0
    long_x_minute_q25: float = 0.0
    long_x_minute_q75: float = 0.0
    long_v_reach_q25: float = 0.0
    long_v_reach_q75: float = 0.0
    long_v_minute_q25: float = 0.0
    long_v_minute_q75: float = 0.0
    short_x_adverse_q25: float = 0.0
    short_x_adverse_q75: float = 0.0
    short_x_minute_q25: float = 0.0
    short_x_minute_q75: float = 0.0
    short_v_reach_q25: float = 0.0
    short_v_reach_q75: float = 0.0
    short_v_minute_q25: float = 0.0
    short_v_minute_q75: float = 0.0

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

        def wquantile(label, q):
            pairs = sorted((float(row[label]), w) for w, (_, row) in zip(weights, neighbors))
            target = max(0.0, min(1.0, float(q))) * sum(w for _, w in pairs)
            acc = 0.0
            for value, weight in pairs:
                acc += weight
                if acc >= target:
                    return value
            return pairs[-1][0] if pairs else 0.0

        terminal = wmean("future_terminal_return_pct")
        upside = max(0.0, wmean("future_upside_reach_pct"))
        downside = max(0.0, wmean("future_downside_reach_pct"))

        # Timing labels are learned from training rows only.
        # They estimate when the future upside/downside extreme is typically reached.
        if "future_upside_peak_minute" in neighbors[0][1]:
            upside_peak_minute = max(1.0, min(float(h), wmean("future_upside_peak_minute")))
        else:
            upside_peak_minute = float(h)

        if "future_downside_peak_minute" in neighbors[0][1]:
            downside_peak_minute = max(1.0, min(float(h), wmean("future_downside_peak_minute")))
        else:
            downside_peak_minute = float(h)

        has_ordered = "future_long_x_to_v_pct" in neighbors[0][1]
        if has_ordered:
            long_x_adverse = max(0.0, wmean("future_long_x_adverse_pct"))
            long_x_minute = max(1.0, min(float(h), wmean("future_long_x_minute")))
            long_v_reach = max(0.0, wmean("future_long_v_reach_pct"))
            long_v_minute = max(long_x_minute, min(float(h), wmean("future_long_v_minute")))
            long_x_to_v = max(0.0, wmean("future_long_x_to_v_pct"))
            short_x_adverse = max(0.0, wmean("future_short_x_adverse_pct"))
            short_x_minute = max(1.0, min(float(h), wmean("future_short_x_minute")))
            short_v_reach = max(0.0, wmean("future_short_v_reach_pct"))
            short_v_minute = max(short_x_minute, min(float(h), wmean("future_short_v_minute")))
            short_x_to_v = max(0.0, wmean("future_short_x_to_v_pct"))
            long_x_adverse_q25, long_x_adverse_q75 = wquantile("future_long_x_adverse_pct", .25), wquantile("future_long_x_adverse_pct", .75)
            long_x_minute_q25, long_x_minute_q75 = wquantile("future_long_x_minute", .25), wquantile("future_long_x_minute", .75)
            long_v_reach_q25, long_v_reach_q75 = wquantile("future_long_v_reach_pct", .25), wquantile("future_long_v_reach_pct", .75)
            long_v_minute_q25, long_v_minute_q75 = wquantile("future_long_v_minute", .25), wquantile("future_long_v_minute", .75)
            short_x_adverse_q25, short_x_adverse_q75 = wquantile("future_short_x_adverse_pct", .25), wquantile("future_short_x_adverse_pct", .75)
            short_x_minute_q25, short_x_minute_q75 = wquantile("future_short_x_minute", .25), wquantile("future_short_x_minute", .75)
            short_v_reach_q25, short_v_reach_q75 = wquantile("future_short_v_reach_pct", .25), wquantile("future_short_v_reach_pct", .75)
            short_v_minute_q25, short_v_minute_q75 = wquantile("future_short_v_minute", .25), wquantile("future_short_v_minute", .75)
        else:
            long_x_adverse, long_x_minute, long_v_reach, long_v_minute, long_x_to_v = (
                downside, downside_peak_minute, upside, upside_peak_minute, 0.0
            )
            short_x_adverse, short_x_minute, short_v_reach, short_v_minute, short_x_to_v = (
                upside, upside_peak_minute, downside, downside_peak_minute, 0.0
            )
            long_x_adverse_q25 = long_x_adverse_q75 = long_x_adverse
            long_x_minute_q25 = long_x_minute_q75 = long_x_minute
            long_v_reach_q25 = long_v_reach_q75 = long_v_reach
            long_v_minute_q25 = long_v_minute_q75 = long_v_minute
            short_x_adverse_q25 = short_x_adverse_q75 = short_x_adverse
            short_x_minute_q25 = short_x_minute_q75 = short_x_minute
            short_v_reach_q25 = short_v_reach_q75 = short_v_reach
            short_v_minute_q25 = short_v_minute_q75 = short_v_minute

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
            expected_upside_peak_minute=upside_peak_minute,
            expected_downside_peak_minute=downside_peak_minute,
            expected_long_x_adverse_pct=long_x_adverse,
            expected_long_x_minute=long_x_minute,
            expected_long_v_reach_pct=long_v_reach,
            expected_long_v_minute=long_v_minute,
            expected_long_x_to_v_pct=long_x_to_v,
            expected_short_x_adverse_pct=short_x_adverse,
            expected_short_x_minute=short_x_minute,
            expected_short_v_reach_pct=short_v_reach,
            expected_short_v_minute=short_v_minute,
            expected_short_x_to_v_pct=short_x_to_v,
            long_x_adverse_q25=long_x_adverse_q25, long_x_adverse_q75=long_x_adverse_q75,
            long_x_minute_q25=long_x_minute_q25, long_x_minute_q75=long_x_minute_q75,
            long_v_reach_q25=long_v_reach_q25, long_v_reach_q75=long_v_reach_q75,
            long_v_minute_q25=long_v_minute_q25, long_v_minute_q75=long_v_minute_q75,
            short_x_adverse_q25=short_x_adverse_q25, short_x_adverse_q75=short_x_adverse_q75,
            short_x_minute_q25=short_x_minute_q25, short_x_minute_q75=short_x_minute_q75,
            short_v_reach_q25=short_v_reach_q25, short_v_reach_q75=short_v_reach_q75,
            short_v_minute_q25=short_v_minute_q25, short_v_minute_q75=short_v_minute_q75,
        )

    def fitted_horizons(self):
        return sorted(self._rows_by_horizon)

    def metadata(self):
        return {
            "stage": "3-FINAL-CANDIDATE",
            "model_type": "empirical_similarity_ordered_future_xv_path",
            "feature_names": list(FEATURE_NAMES),
            "fitted_horizons": self.fitted_horizons(),
            "max_neighbors": self.max_neighbors,
            "min_neighbors": self.min_neighbors,
            "calibrated": False,
            "holdout_used": False,
        }


# ---------------------------------------------------------------------------
# Stage 3E-1: fixed baselines for validation comparison.
# These baselines never learn from validation or holdout labels.
# ---------------------------------------------------------------------------

class ZeroChangeBaseline:
    name = "zero_change"

    def predict(self, features, horizon_minutes):
        h = int(horizon_minutes)
        return ModelPrediction(
            horizon_minutes=h,
            expected_terminal_return_pct=0.0,
            expected_upside_reach_pct=0.0,
            expected_downside_reach_pct=0.0,
            probability_up=0.5,
            probability_down=0.5,
            analogue_count=0,
            status="baseline_zero_change",
            expected_upside_peak_minute=float(h),
            expected_downside_peak_minute=float(h),
        )


class MomentumBaseline:
    name = "momentum"

    def predict(self, features, horizon_minutes):
        h = int(horizon_minutes)
        r30 = float(features["return_30m_pct"])
        scale = sqrt(max(h, 1) / 30.0)
        terminal = r30 * min(scale, 2.0)
        magnitude = abs(terminal)
        p_up = 0.55 if terminal > 0 else (0.45 if terminal < 0 else 0.5)
        return ModelPrediction(
            horizon_minutes=h,
            expected_terminal_return_pct=terminal,
            expected_upside_reach_pct=max(0.0, terminal) + 0.25 * magnitude,
            expected_downside_reach_pct=max(0.0, -terminal) + 0.25 * magnitude,
            probability_up=p_up,
            probability_down=1.0 - p_up,
            analogue_count=0,
            status="baseline_momentum",
            expected_upside_peak_minute=float(h),
            expected_downside_peak_minute=float(h),
        )


class MeanReversionBaseline:
    name = "mean_reversion"

    def predict(self, features, horizon_minutes):
        h = int(horizon_minutes)
        r30 = float(features["return_30m_pct"])
        scale = sqrt(max(h, 1) / 30.0)
        terminal = -0.5 * r30 * min(scale, 2.0)
        magnitude = abs(terminal)
        p_up = 0.55 if terminal > 0 else (0.45 if terminal < 0 else 0.5)
        return ModelPrediction(
            horizon_minutes=h,
            expected_terminal_return_pct=terminal,
            expected_upside_reach_pct=max(0.0, terminal) + 0.25 * magnitude,
            expected_downside_reach_pct=max(0.0, -terminal) + 0.25 * magnitude,
            probability_up=p_up,
            probability_down=1.0 - p_up,
            analogue_count=0,
            status="baseline_mean_reversion",
            expected_upside_peak_minute=float(h),
            expected_downside_peak_minute=float(h),
        )


def stage_3e_baselines():
    return {
        "zero_change": ZeroChangeBaseline(),
        "momentum": MomentumBaseline(),
        "mean_reversion": MeanReversionBaseline(),
    }
