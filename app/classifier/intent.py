
from enum import Enum

from pydantic import BaseModel


class IntentType(str, Enum):
    FACT_CLAIM = "FACT_CLAIM"
    COMPARISON = "COMPARISON"
    GENERAL_QUESTION = "GENERAL_QUESTION"
    PERSONAL_MEDICAL = "PERSONAL_MEDICAL"
    UNCLEAR = "UNCLEAR"


class IntentResult(BaseModel):
    text: str
    intent: IntentType
    explanation: str


def classify_intent(text: str) -> IntentResult:
    normalized = text.lower().strip()

    if not normalized:
        return IntentResult(
            text=text,
            intent=IntentType.UNCLEAR,
            explanation="Пользователь не ввёл текст."
        )

    personal_markers = (
        "у меня", "мне", "мой диагноз", "мои анализы",
        "что мне принимать", "что мне есть",
        "какую диету мне", "мне можно"
    )

    if any(marker in normalized for marker in personal_markers):
        return IntentResult(
            text=text,
            intent=IntentType.PERSONAL_MEDICAL,
            explanation="Запрос содержит признаки индивидуального медицинского вопроса."
        )

    comparison_markers = (
        "что лучше", "что эффективнее", "сравни",
        "по сравнению с", "в отличие от", "против",
        " или ", "превосходит", "не уступает",
        "эффективнее", "лучше, чем", "хуже, чем",
        "менее эффективен", "более эффективен",
        "не отличается от", "сравнение"
    )

    if any(marker in normalized for marker in comparison_markers):
        return IntentResult(
            text=text,
            intent=IntentType.COMPARISON,
            explanation="Запрос содержит признаки сравнения."
        )

    question_markers = (
        "что такое", "почему", "как выбрать",
        "как работает", "можно ли", "правда ли",
        "действительно ли", "сколько", "какие"
    )

    if normalized.endswith("?") or any(
        marker in normalized for marker in question_markers
    ):
        return IntentResult(
            text=text,
            intent=IntentType.GENERAL_QUESTION,
            explanation="Запрос сформулирован как вопрос."
        )

    return IntentResult(
        text=text,
        intent=IntentType.FACT_CLAIM,
        explanation="Запрос предварительно классифицирован как утверждение."
    )