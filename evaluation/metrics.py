"""Binary metrics with grouped score ties; no runtime dependency on sklearn."""

import math


def binary_metrics(labels, scores, threshold=0.70):
    if not labels or len(labels) != len(scores):
        raise ValueError("Non-empty, equally sized labels and scores are required")
    if any(label not in (0, 1) for label in labels) or any(not math.isfinite(score) or not 0 <= score <= 1 for score in scores):
        raise ValueError("Labels must be binary and scores finite in [0, 1]")
    predictions = [score >= threshold for score in scores]
    tp = sum(label == 1 and predicted for label, predicted in zip(labels, predictions))
    fp = sum(label == 0 and predicted for label, predicted in zip(labels, predictions))
    fn, tn = sum(labels) - tp, len(labels) - sum(labels) - fp
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    # Average precision is the stepwise area under the precision-recall curve.
    groups = {}
    for label, score in zip(labels, scores):
        groups.setdefault(score, []).append(label)
    positives = sum(labels)
    cumulative_tp = cumulative_count = 0
    average_precision = 0.0
    for score in sorted(groups, reverse=True):
        group = groups[score]
        cumulative_tp += sum(group)
        cumulative_count += len(group)
        if positives:
            average_precision += (sum(group) / positives) * (cumulative_tp / cumulative_count)
    return {"samples": len(labels), "threshold": threshold, "true_positives": tp,
            "false_positives": fp, "true_negatives": tn, "false_negatives": fn,
            "precision": precision, "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
            "pr_auc_average_precision": average_precision,
            "false_positive_rate": fp / (fp + tn) if fp + tn else 0.0}


def select_threshold(labels, scores, maximum_fpr=0.05):
    candidates = sorted(set([0.0, 1.000001, *scores]))
    feasible = [binary_metrics(labels, scores, threshold) for threshold in candidates]
    feasible = [result for result in feasible if result["false_positive_rate"] <= maximum_fpr]
    return max(feasible, key=lambda result: (result["f1"], result["precision"], result["threshold"]))["threshold"]
