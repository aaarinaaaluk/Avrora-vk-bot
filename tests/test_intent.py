
from app.classifier.intent import IntentType, classify_intent


def test_comparison():
    result = classify_intent("Кето-диета эффективнее низкожировой")
    assert result.intent == IntentType.COMPARISON


def test_fact_claim():
    result = classify_intent("Избыток сахара ведёт к ожирению")
    assert result.intent == IntentType.FACT_CLAIM


def test_general_question():
    result = classify_intent("Что такое средиземноморская диета?")
    assert result.intent == IntentType.GENERAL_QUESTION


def test_personal_medical():
    result = classify_intent("У меня гастрит, что мне есть?")
    assert result.intent == IntentType.PERSONAL_MEDICAL


def test_empty_text():
    result = classify_intent("")
    assert result.intent == IntentType.UNCLEAR

def test_personal_medical_question_about_mother():
    result = classify_intent("У моей мамы диабет 2 типа. Какой рацион ей назначить?")
    assert result.intent == IntentType.PERSONAL_MEDICAL


def test_personal_medical_question_about_child():
    result = classify_intent("У моего ребёнка температура, что ему дать?")
    assert result.intent == IntentType.PERSONAL_MEDICAL


def test_general_claim_about_children_is_not_automatically_personal():
    result = classify_intent("Ожирение у детей связано с питанием")
    assert result.intent == IntentType.FACT_CLAIM


def test_risky_question_about_cancelling_prescribed_medicine_routes_to_clinician():
    result = classify_intent(
        "Правда ли, что при диабете 2 типа можно самостоятельно отменить "
        "назначенные лекарства, если полностью отказаться от сахара?"
    )
    assert result.intent == IntentType.PERSONAL_MEDICAL
