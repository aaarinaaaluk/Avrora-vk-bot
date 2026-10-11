"""VK Callback API: приём сообщений и ответы фактчекера."""

import json
import urllib.parse
import urllib.request
from uuid import uuid4

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from app.config import VK_CONFIRMATION_CODE, VK_GROUP_TOKEN, VK_SECRET
from app.core.analyzer import AnalysisRoute, analyze_query
from app.core.fact_checker import check_claim
from app.core.verifier import ConfidenceLevel, VerificationStatus

router = APIRouter()
VK_API_VERSION = "5.199"

STATUS_LABELS = {
    VerificationStatus.SUPPORTED: "есть поддержка в найденных источниках",
    VerificationStatus.CONTRADICTED: "найденные источники противоречат утверждению",
    VerificationStatus.INSUFFICIENT: "недостаточно доказательств",
}
CONFIDENCE_LABELS = {
    ConfidenceLevel.HIGH: "высокая",
    ConfidenceLevel.MEDIUM: "средняя",
    ConfidenceLevel.LOW: "низкая",
}


def build_reply(text: str) -> str:
    claim = text.strip()
    if not claim:
        return (
            "Привет! Я AVRORA — медицинский фактчекер. "
            "Пришли конкретное утверждение о здоровье или питании, "
            "и я проверю его по разрешённым источникам."
        )

    analysis = analyze_query(claim)
    if analysis.safety_message:
        return (
            f"{analysis.safety_message}\n\n"
            "Я не ставлю диагнозы и не назначаю лечение."
        )

    if analysis.route != AnalysisRoute.EVIDENCE_SEARCH:
        return (
            "Я проверяю конкретные утверждения о здоровье и питании. "
            "Например: «Витамин C предотвращает простуду».\n\n"
            "Сформулируй сообщение как утверждение, которое можно сверить "
            "с публикациями и рекомендациями."
        )

    result = check_claim(claim)
    status_label = STATUS_LABELS[result.status]
    confidence_label = CONFIDENCE_LABELS[result.confidence]
    reply = (
        f"Утверждение: {result.claim}\n\n"
        f"Результат: {status_label}.\n"
        f"Уверенность оценки: {confidence_label}.\n\n"
        f"{result.explanation}"
    )

    if result.evidence:
        reply += "\n\nИсточники, использованные при проверке:"
        for index, item in enumerate(result.evidence[:5], start=1):
            snippet = item.evidence_summary.strip().replace("\r", "")
            if len(snippet) > 420:
                snippet = snippet[:417] + "..."
            reply += (
                f"\n\n{index}. {item.source_name}"
                f"\nСсылка: {item.source_url}"
                f"\nФрагмент: {snippet}"
            )
            if item.supports_claim is True:
                reply += "\nОценка фрагмента: поддерживает утверждение"
            elif item.supports_claim is False:
                reply += "\nОценка фрагмента: противоречит утверждению"
    else:
        reply += "\n\nПодходящих фрагментов в доступных подключённых источниках не найдено."

    reply += (
        "\n\nВажно: это предварительная автоматическая оценка, а не диагноз "
        "и не назначение лечения. Google Fact Check показывает ранее опубликованные "
        "проверки; PubMed часто предоставляет только аннотации. При противоречиях "
        "или вопросах о личном здоровье обратитесь к медицинскому специалисту."
    )
    # VK ограничивает размер сообщения. Сохраняем вывод и начало списка источников.
    return reply[:3900]


def send_vk_message(peer_id: int, message: str) -> None:
    if not VK_GROUP_TOKEN:
        raise RuntimeError("Не настроена переменная VK_GROUP_TOKEN в .env")

    payload = urllib.parse.urlencode({
        "access_token": VK_GROUP_TOKEN,
        "v": VK_API_VERSION,
        "peer_id": peer_id,
        "random_id": uuid4().int % (2**31),
        "message": message,
    }).encode("utf-8")

    request = urllib.request.Request(
        "https://api.vk.com/method/messages.send",
        data=payload,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        result = json.loads(response.read().decode("utf-8"))

    if "error" in result:
        raise RuntimeError(
            f"VK API error: {result['error'].get('error_msg', 'unknown error')}"
        )


@router.post("/vk/callback")
async def vk_callback(request: Request):
    payload = await request.json()
    event_type = payload.get("type")

    if event_type == "confirmation":
        return PlainTextResponse(VK_CONFIRMATION_CODE)

    if VK_SECRET and payload.get("secret") != VK_SECRET:
        return PlainTextResponse("forbidden", status_code=403)

    if event_type == "message_new":
        message_data = payload.get("object", {}).get("message", {})
        text = message_data.get("text", "")
        peer_id = message_data.get("peer_id")
        if peer_id and text:
            reply = build_reply(text)
            send_vk_message(int(peer_id), reply)

    return PlainTextResponse("ok")
