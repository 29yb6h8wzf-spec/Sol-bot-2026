"""No-network ML baseline tests: causal chronology, calibration and abstention."""
from dataclasses import replace
import math
import pytest
from signals_v2.ml_baseline import (
    LabeledRow, ModelRejected, fit_logistic, calibrate_platt, brier_score,
)


def rows(start, count, *, offset=0):
    return tuple(LabeledRow(start + i*300_000,
                            (float((i+offset)%11 - 5), float(i%3)),
                            int((i+offset)%11 >= 6))
                 for i in range(count))


def test_training_and_calibration_are_chronological():
    training = rows(1_800_000_000_000, 80)
    calibration = rows(training[-1].decision_ms + 300_000, 50, offset=2)
    model = fit_logistic(training)
    calibrated = calibrate_platt(model, calibration)
    assert calibrated.sample_count == 50
    assert 0 < calibrated.predict((2.0, 1.0),
                                  asof_ms=calibration[-1].decision_ms+300_000) < 1


def test_training_time_cannot_be_predicted():
    training = rows(1_800_000_000_000, 80)
    model = fit_logistic(training)
    with pytest.raises(ModelRejected, match="not_out_of_training_time"):
        model.predict((1.0, 0.0), asof_ms=training[-1].decision_ms)


def test_calibration_overlap_is_rejected():
    training = rows(1_800_000_000_000, 80)
    model = fit_logistic(training)
    with pytest.raises(ModelRejected, match="calibration_overlaps_training"):
        calibrate_platt(model, training[-50:])


def test_calibrated_predictions_reject_calibration_time():
    training = rows(1_800_000_000_000, 80)
    calibration = rows(training[-1].decision_ms+300_000, 50)
    model = calibrate_platt(fit_logistic(training), calibration)
    with pytest.raises(ModelRejected, match="not_out_of_calibration_time"):
        model.predict((0.0, 1.0), asof_ms=calibration[-1].decision_ms)


def test_training_is_deterministic_and_predicts_higher_for_positive_feature():
    training = rows(1_800_000_000_000, 88)
    a, b = fit_logistic(training), fit_logistic(training)
    assert a == b
    asof = training[-1].decision_ms + 300_000
    assert a.predict((5.0, 1.0), asof_ms=asof) > a.predict((-5.0, 1.0), asof_ms=asof)


def test_duplicate_time_and_single_class_rejected():
    training = rows(1_800_000_000_000, 80)
    with pytest.raises(ModelRejected, match="nonchronological"):
        fit_logistic(training[:-1]+(training[-2],))
    with pytest.raises(ModelRejected, match="single_class"):
        fit_logistic(tuple(replace(r, profitable=1) for r in training))


def test_shape_nan_and_unavailable_prediction_rejected():
    training = rows(1_800_000_000_000, 80)
    model = fit_logistic(training)
    asof = training[-1].decision_ms + 300_000
    with pytest.raises(ModelRejected, match="feature_shape"):
        model.predict((1.0,), asof_ms=asof)
    with pytest.raises(ModelRejected, match="invalid_feature"):
        model.predict((math.nan, 1.0), asof_ms=asof)


def test_brier_is_descriptive_not_profitability():
    assert brier_score((0.9, 0.1), (1, 0)) == pytest.approx(0.01)
    with pytest.raises(ModelRejected, match="invalid_probability"):
        brier_score((1.2,), (1,))
