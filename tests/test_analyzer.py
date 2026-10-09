
from app.classifier.intent import IntentType
from app.core.analyzer import analyze_query


def test_analyzer_classifies_comparison():
    result = analyze_query(
        "Кето-диета эффективнее низкожировой диеты"
    )

    assert result.intent == IntentType.COMPARISON
    assert "COMPARATIVE" in [
        tag.value for tag in result.claim_tags
    ]


def test_personal_medical_query_has_no_candidate_sources():
    result = analyze_query("Какую диету мне выбрать?")

    assert result.intent == IntentType.PERSONAL_MEDICAL
    assert result.candidate_sources == []


def test_analyzer_does_not_return_medical_verdict():
    result = analyze_query("Клетчатка улучшает работу кишечника")

    assert hasattr(result, "claim_tags")
    assert not hasattr(result, "status")
