from app.classifier.intent import IntentType
from app.core.analyzer import AnalysisRoute, analyze_query


def test_analyzer_classifies_comparison():
    result = analyze_query(
        "Кето-диета эффективнее низкожировой диеты"
    )

    assert result.intent == IntentType.COMPARISON
    assert result.route == AnalysisRoute.EVIDENCE_SEARCH
    assert "COMPARATIVE" in [
        tag.value for tag in result.claim_tags
    ]


def test_personal_medical_query_has_no_candidate_sources():
    result = analyze_query("Какую диету мне выбрать?")

    assert result.intent == IntentType.PERSONAL_MEDICAL
    assert result.route == AnalysisRoute.CLINICIAN_GUIDANCE
    assert result.candidate_sources == []
    assert result.safety_message is not None


def test_analyzer_does_not_return_medical_verdict():
    result = analyze_query("Клетчатка улучшает работу кишечника")

    assert hasattr(result, "claim_tags")
    assert not hasattr(result, "status")


def test_general_question_uses_general_information_route():
    result = analyze_query("Что такое клетчатка?")

    assert result.route == AnalysisRoute.GENERAL_INFORMATION
    assert result.candidate_sources == []


def test_personal_medical_route_has_safety_message():
    result = analyze_query("Что мне принимать для похудения?")

    assert result.route == AnalysisRoute.CLINICIAN_GUIDANCE
    assert result.safety_message


def test_personal_medical_question_about_relative_routes_to_clinician():
    result = analyze_query("У моей мамы диабет 2 типа. Какой рацион ей назначить?")
    assert result.intent == IntentType.PERSONAL_MEDICAL
    assert result.route == AnalysisRoute.CLINICIAN_GUIDANCE
    assert result.candidate_sources == []
    assert "другого конкретного человека" in result.safety_message
