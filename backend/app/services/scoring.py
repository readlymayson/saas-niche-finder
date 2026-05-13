from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScoreFactors:
    wordstat_growth: float
    pain_frequency: float
    competitors_count: float
    budget_signal: float


def _to_float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        raw = value.strip().replace(",", ".")
        if not raw:
            return default
        try:
            return float(raw)
        except ValueError:
            return default
    return default


def calculate_score(factors: ScoreFactors) -> float:
    score = (
        factors.wordstat_growth * 0.4
        + factors.pain_frequency * 0.3
        - factors.competitors_count * 0.2
        + factors.budget_signal * 0.1
    )
    return round(score, 6)


def score_from_payloads(
    wordstat_snapshot: dict[str, Any] | None,
    yandex_gpt_json: dict[str, Any] | None,
) -> float:
    wordstat = wordstat_snapshot or {}
    gpt = yandex_gpt_json or {}
    factors = ScoreFactors(
        wordstat_growth=_to_float(wordstat.get("growth")),
        pain_frequency=_to_float(gpt.get("pain_frequency")),
        competitors_count=_to_float(gpt.get("competitors_count")),
        budget_signal=_to_float(gpt.get("budget_signal")),
    )
    return calculate_score(factors)
