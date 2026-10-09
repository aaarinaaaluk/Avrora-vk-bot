
from app.classifier.claim_type import ClaimType, classify_claim_type


def test_comparison_has_effectiveness_tag():
    result = classify_claim_type(
        "Кето-диета эффективнее низкожировой"
    )
    assert result.claim_type == ClaimType.COMPARATIVE
    assert ClaimType.EFFECTIVENESS in result.tags


def test_causal_claim():
    result = classify_claim_type(
        "Избыток сахара ведёт к ожирению"
    )
    assert ClaimType.CAUSAL in result.tags


def test_safety_and_causality():
    result = classify_claim_type(
        "Эта диета вызывает опасные осложнения"
    )
    assert ClaimType.SAFETY in result.tags
    assert ClaimType.CAUSAL in result.tags


def test_effectiveness_and_quantity():
    result = classify_claim_type(
        "Эта диета снижает вес на 5 кг за месяц"
    )
    assert ClaimType.EFFECTIVENESS in result.tags
    assert ClaimType.QUANTITATIVE in result.tags


def test_question_is_unclear_as_a_claim():
    result = classify_claim_type(
        "Что такое средиземноморская диета?"
    )
    assert result.claim_type == ClaimType.UNCLEAR