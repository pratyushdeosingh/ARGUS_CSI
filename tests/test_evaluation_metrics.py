import pytest

from evaluation.dataset import generate_split
from evaluation.metrics import binary_metrics, select_threshold


def test_metrics_known_confusion_matrix_and_tied_precision_recall_area():
    scores = binary_metrics([1, 1, 0, 0], [0.9, 0.4, 0.8, 0.1], 0.7)
    assert scores["precision"] == scores["recall"] == scores["f1"] == 0.5
    assert scores["false_positives"] == 1
    assert scores["false_positive_rate"] == 0.5
    assert binary_metrics([1, 0], [0.5, 0.5])["pr_auc_average_precision"] == 0.5
    assert binary_metrics([0, 1], [0.5, 0.5])["pr_auc_average_precision"] == 0.5


def test_threshold_selection_uses_only_passed_validation_samples():
    assert select_threshold([0, 1], [0.2, 0.8]) == 0.8
    assert select_threshold([0, 1], [1, 0.1]) > 1
    with pytest.raises(ValueError):
        binary_metrics([1], [float("nan")])


def test_synthetic_splits_are_reproducible_and_have_disjoint_accounts():
    validation = generate_split("validation", 123)
    assert validation == generate_split("validation", 123)
    test = generate_split("test", 456)
    def accounts(cases):
        return {tx["source_account"] for case in cases for tx in case["transactions"]}
    assert accounts(validation).isdisjoint(accounts(test))
    assert {case["label"] for case in test} == {0, 1}
    assert any(case["segment"] == "payroll_control" and case["label"] == 0 for case in test)
