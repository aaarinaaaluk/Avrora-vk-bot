
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