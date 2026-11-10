"""Deterministic, dependency-free ML baseline for *research-only* V2.

Uses chronological fit and independent calibration. This is a comparator, not
an execution gate. No performance or profitability claim is implied.
"""
from dataclasses import dataclass
from math import exp, isfinite, log
from statistics import mean


class ModelRejected(ValueError):
    pass


@dataclass(frozen=True)
class LabeledRow:
    decision_ms: int
    features: tuple[float, ...]
    profitable: int

    def __post_init__(self):
        if type(self.decision_ms) is not int or self.decision_ms < 0:
            raise ModelRejected("invalid_timestamp")
        if not isinstance(self.features, tuple) or not self.features:
            raise ModelRejected("empty_features")
        if any(type(v) not in (float, int) or not isfinite(v) for v in self.features):
            raise ModelRejected("invalid_feature")
        if type(self.profitable) is not int or self.profitable not in (0, 1):
            raise ModelRejected("invalid_label")


@dataclass(frozen=True)
class LogisticModel:
    means: tuple[float, ...]
    scales: tuple[float, ...]
    weights: tuple[float, ...]
    intercept: float
    training_end_ms: int

    def predict(self, values: tuple[float, ...], *, asof_ms: int) -> float:
        if type(asof_ms) is not int or asof_ms <= self.training_end_ms:
            raise ModelRejected("not_out_of_training_time")
        if not isinstance(values, tuple) or len(values) != len(self.weights):
            raise ModelRejected("feature_shape_mismatch")
        if any(type(v) not in (float, int) or not isfinite(v) for v in values):
            raise ModelRejected("invalid_feature")
        z = self.intercept + sum(
            w * ((v - mu) / scale)
            for w, v, mu, scale in zip(self.weights, values, self.means, self.scales)
        )
        return _sigmoid(z)


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1 / (1 + exp(-min(z, 700)))
    e = exp(max(z, -700))
    return e / (1 + e)


def _check_rows(rows: tuple[LabeledRow, ...], *, minimum: int) -> int:
    if not isinstance(rows, tuple) or len(rows) < minimum:
        raise ModelRejected("insufficient_rows")
    if any(not isinstance(row, LabeledRow) for row in rows):
        raise ModelRejected("invalid_row")
    dims = len(rows[0].features)
    if any(len(row.features) != dims for row in rows):
        raise ModelRejected("feature_shape_mismatch")
    if any(b.decision_ms <= a.decision_ms for a, b in zip(rows, rows[1:])):
        raise ModelRejected("nonchronological_or_duplicate_rows")
    if len({r.profitable for r in rows}) < 2:
        raise ModelRejected("single_class_labels")
    return dims


def fit_logistic(rows: tuple[LabeledRow, ...], *, iterations: int = 300,
                 learning_rate: float = 0.1, ridge: float = 0.01,
                 minimum: int = 30) -> LogisticModel:
    dims = _check_rows(rows, minimum=minimum)
    if type(iterations) is not int or not 1 <= iterations <= 10_000:
        raise ModelRejected("invalid_iterations")
    if not isfinite(learning_rate) or not 0 < learning_rate <= 1:
        raise ModelRejected("invalid_learning_rate")
    if not isfinite(ridge) or ridge < 0:
        raise ModelRejected("invalid_regularization")
    means = tuple(mean(row.features[j] for row in rows) for j in range(dims))
    scales = tuple(max(1e-12, (mean(
        (row.features[j] - means[j]) ** 2 for row in rows
    )) ** 0.5) for j in range(dims))
    x = [tuple((v - mu) / scale for v, mu, scale in
               zip(row.features, means, scales)) for row in rows]
    w = [0.0] * dims
    b = log(sum(row.profitable for row in rows) /
            sum(1 - row.profitable for row in rows))
    n = len(rows)
    for _ in range(iterations):
        residuals = [_sigmoid(b + sum(a * c for a, c in zip(w, row))) -
                     original.profitable for row, original in zip(x, rows)]
        b -= learning_rate * sum(residuals) / n
        for j in range(dims):
            gradient = sum(e * row[j] for e, row in zip(residuals, x)) / n
            w[j] -= learning_rate * (gradient + ridge * w[j])
    return LogisticModel(means, scales, tuple(w), b, rows[-1].decision_ms)


@dataclass(frozen=True)
class CalibratedModel:
    base: LogisticModel
    slope: float
    intercept: float
    calibration_end_ms: int
    sample_count: int

    def predict(self, values: tuple[float, ...], *, asof_ms: int) -> float:
        if type(asof_ms) is not int or asof_ms <= self.calibration_end_ms:
            raise ModelRejected("not_out_of_calibration_time")
        p = self.base.predict(values, asof_ms=asof_ms)
        p = min(max(p, 1e-12), 1 - 1e-12)
        return _sigmoid(self.slope * log(p / (1 - p)) + self.intercept)


def calibrate_platt(model: LogisticModel, rows: tuple[LabeledRow, ...],
                    *, minimum: int = 30) -> CalibratedModel:
    _check_rows(rows, minimum=minimum)
    if rows[0].decision_ms <= model.training_end_ms:
        raise ModelRejected("calibration_overlaps_training")
    if any(len(r.features) != len(model.weights) for r in rows):
        raise ModelRejected("feature_shape_mismatch")
    logits = []
    for r in rows:
        p = model.predict(r.features, asof_ms=r.decision_ms)
        p = min(max(p, 1e-12), 1 - 1e-12)
        logits.append(log(p / (1 - p)))
    scale = max(1.0, max(abs(v) for v in logits))
    normalized = [v / scale for v in logits]
    slope, intercept = 0.0, log(sum(r.profitable for r in rows) /
                                 sum(1-r.profitable for r in rows))
    for _ in range(500):
        errors = [_sigmoid(slope*x + intercept) - r.profitable
                  for x, r in zip(normalized, rows)]
        slope -= 0.1 * sum(e*x for e, x in zip(errors, normalized)) / len(rows)
        intercept -= 0.1 * sum(errors) / len(rows)
    return CalibratedModel(model, slope/scale, intercept,
                           rows[-1].decision_ms, len(rows))


def brier_score(probabilities: tuple[float, ...],
                labels: tuple[int, ...]) -> float:
    if not probabilities or len(probabilities) != len(labels):
        raise ModelRejected("invalid_evaluation_sample")
    if any(type(p) not in (int, float) or not isfinite(p) or not 0 <= p <= 1
           for p in probabilities):
        raise ModelRejected("invalid_probability")
    if any(type(y) is not int or y not in (0, 1) for y in labels):
        raise ModelRejected("invalid_label")
    return mean((p-y)**2 for p, y in zip(probabilities, labels))
