import os
from uuid import uuid4
from app.sources.document_search import search_documents

import urllib.parse
import urllib.request
import json

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from app.core.analyzer import analyze_query
from app.core.verifier import verify_claim

router = APIRouter()

VK_GROUP_TOKEN = os.getenv("VK_GROUP_TOKEN", "")
VK_CONFIRMATION_CODE = os.getenv("VK_CONFIRMATION_CODE", "")
VK_SECRET = os.getenv("VK_SECRET", "")
VK_API_VERSION = "5.199"


def build_reply(text: str) -> str:
    claim = text.strip()

    if not claim:
        return (
            "Привет! Я AVRORA — медицинский фактчекер. "
            "Пришли утверждение о питании или витаминах, "
            "которое хочешь проверить."
        )

    analysis = analyze_query(claim)

    if analysis.safety_message:
        return (
            f"{analysis.safety_message}\n\n"
            "Я не ставлю диагнозы и не назначаю лечение."
        )

    if analysis.route.value != "EVIDENCE_SEARCH":
        return (
            "Я помогаю разбирать конкретные утверждения о питании "
            "и здоровье. Например: «Витамин C предотвращает простуду».\n\n"
            "Пока у меня нет достаточной базы проверенных источников, "
            "поэтому я не буду объявлять утверждение правдой или ложью."
        )

    
    search_results = search_documents(claim, limit=5)

    # Не показываем слабые совпадения по одному общему слову.
    relevant_results = [
        item for item in search_results
        if len(item.matched_terms) >= 2
    ]

    result = verify_claim(claim, search_results=relevant_results)

    reply = (
        f"Утверждение: {result.claim}\n\n"
        "Результат: недостаточно проверенных доказательств.\n"
        f"{result.explanation}"
    )

    if relevant_results:
        reply += "\n\nНайденные фрагменты для изучения:"
        for item in relevant_results[:3]:
            reply += (
                f"\n\nИсточник: {item.document_title}"
                f"\nСтраница: {item.page_number}"
                f"\nСсылка: {item.source_url}"
                f"\nФрагмент: {item.text[:500]}"
            )
    else:
        reply += "\n\nВ локальных документах не найдено достаточно совпадений "
        "для показа фрагментов."

    reply += (
        "\n\nВажно: совпадение слов не подтверждает и не опровергает "
        "медицинское утверждение. Найденные фрагменты требуют проверки "
        "контекста и качества доказательств."
    )

    return reply

def send_vk_message(peer_id: int, message: str) -> None:
    if not VK_GROUP_TOKEN:
        raise RuntimeError("Не настроена переменная VK_GROUP_TOKEN")

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

    with urllib.request.urlopen(request, timeout=10) as response:
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

    