from __future__ import annotations

from dataclasses import dataclass

from src.nutrition.matcher import normalize_food_name


@dataclass(frozen=True)
class ExtractionMetrics:
    precision: float
    recall: float
    f1: float


def compute_item_f1(expected: list[str], predicted: list[str]) -> ExtractionMetrics:
    expected_set = {normalize_food_name(item) for item in expected}
    predicted_set = {normalize_food_name(item) for item in predicted}

    true_positive = len(expected_set & predicted_set)
    false_positive = len(predicted_set - expected_set)
    false_negative = len(expected_set - predicted_set)

    precision = true_positive / (true_positive + false_positive) if predicted_set else 0.0
    recall = true_positive / (true_positive + false_negative) if expected_set else 0.0
    f1 = 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)

    return ExtractionMetrics(precision=precision, recall=recall, f1=f1)
