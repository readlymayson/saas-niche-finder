from app.services.scoring import ScoreFactors, calculate_score, score_from_payloads


def test_calculate_score_formula() -> None:
    factors = ScoreFactors(
        wordstat_growth=10.0,
        pain_frequency=8.0,
        competitors_count=5.0,
        budget_signal=7.0,
    )
    score = calculate_score(factors)
    assert score == 6.1


def test_score_from_payloads_defaults_to_zero() -> None:
    assert score_from_payloads(None, None) == 0.0


def test_score_from_payloads_reads_fields() -> None:
    score = score_from_payloads(
        {"growth": "12.5"},
        {"pain_frequency": 4, "competitors_count": "2", "budget_signal": "3.5"},
    )
    assert score == 6.15


def test_score_from_payloads_invalid_growth_string() -> None:
    assert score_from_payloads({"growth": "not-a-number"}, None) == 0.0
