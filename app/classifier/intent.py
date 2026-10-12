import re
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


_DIRECT_PERSONAL_MARKERS = (
    "у меня", "мне", "мой диагноз", "мои анализы",
    "что мне принимать", "что мне есть",
    "какую диету мне", "мне можно", "могу ли я принимать",
    "моя дозировка", "мне назначили", "мне прописали",
)

# Личные формулировки о близких. Общие фразы вроде «диабет у детей» сами по
# себе не должны считаться личным вопросом, поэтому ниже дополнительно проверяется
# наличие медицинского контекста.
_FAMILY_CONTEXT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bу\s+(?:моего|моей|моему|моих|своего|своей|своему|своих|мамы|папы|отца|матери|реб[её]нка|сына|дочери|мужа|жены|бабушки|дедушки|родителей|брата|сестры|сестры|внука|внучки|родственника|партнера|партнёра|опекуна|подопечного)\b",
        r"\b(?:моя|моей|моему|моего|мои|моих|своя|своей|своему|своего|свои|своих)\s+(?:мам\w*|пап\w*|отц\w*|матер\w*|родител\w*|реб[её]нк\w*|дет\w*|сын\w*|дочер\w*|муж\w*|жен\w*|бабушк\w*|дедушк\w*|супруг\w*|брат\w*|сестр\w*|внук\w*|внучк\w*|родственник\w*|опекун\w*|подопечн\w*|близк\w*|партн[её]р\w*)\b",
        r"\b(?:маме|папе|отцу|матери|реб[её]нку|ребенку|сыну|дочери|мужу|жене|бабушке|дедушке|родителям|брату|сестре|внуку|внучке|родственнику|партнеру|партнёру|опекуну|подопечному)\b",
    )
)

_MEDICAL_CONTEXT_MARKERS = (
    "диабет", "заболев", "симптом", "температур", "болит", "боль",
    "лечен", "лекарств", "препарат", "инсулин", "глюкоз", "доз",
    "назнач", "рацион", "диет", "питан", "похуд", "давлен", "анализ",
    "аллерг", "витамин", "таблет", "принимать", "приним", "что делать",
    "можно ли", "что ему", "что ей", "что дать", "чем кормить", "как кормить",
    "беремен", "кормить", "кормлен", "расстрой", "терап", "врач",
    "посовет", "рекоменд", "воспален", "сыпь", "кашель", "насморк",
    "рвота", "понос", "запор", "холестерин", "сердц", "вес", "масса тела",
    "болезн", "озноб", "головн", "сустав", "пульс", "дозиров", "питания",
)


def _is_personal_medical(text: str) -> bool:
    if any(marker in text for marker in _DIRECT_PERSONAL_MARKERS):
        return True

    refers_to_close_person = any(
        pattern.search(text) for pattern in _FAMILY_CONTEXT_PATTERNS
    )
    has_medical_context = any(
        marker in text for marker in _MEDICAL_CONTEXT_MARKERS
    )
    return refers_to_close_person and has_medical_context


def classify_intent(text: str) -> IntentResult:
    normalized = text.lower().strip()

    if not normalized:
        return IntentResult(
            text=text,
            intent=IntentType.UNCLEAR,
            explanation="Пользователь не ввёл текст.",
        )

    if _is_personal_medical(normalized):
        return IntentResult(
            text=text,
            intent=IntentType.PERSONAL_MEDICAL,
            explanation=(
                "Запрос содержит признаки индивидуального медицинского вопроса "
                "о пользователе или другом конкретном человеке."
            ),
        )

    comparison_markers = (
        "что лучше", "что эффективнее", "сравни",
        "по сравнению с", "в отличие от", "против",
        " или ", "превосходит", "не уступает",
        "эффективнее", "лучше, чем", "хуже, чем",
        "менее эффективен", "более эффективен",
        "не отличается от", "сравнение",
    )

    if any(marker in normalized for marker in comparison_markers):
        return IntentResult(
            text=text,
            intent=IntentType.COMPARISON,
            explanation="Запрос содержит признаки сравнения.",
        )

    question_markers = (
        "что такое", "почему", "как выбрать",
        "как работает", "можно ли", "правда ли",
        "действительно ли", "сколько", "какие",
    )

    if normalized.endswith("?") or any(
        marker in normalized for marker in question_markers
    ):
        return IntentResult(
            text=text,
            intent=IntentType.GENERAL_QUESTION,
            explanation="Запрос сформулирован как вопрос.",
        )

    return IntentResult(
        text=text,
        intent=IntentType.FACT_CLAIM,
        explanation="Запрос предварительно классифицирован как утверждение.",
    )
