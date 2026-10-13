"""VK Callback API: приём сообщений и ответы фактчекера."""

import json
import logging
import time
import urllib.parse
import urllib.request
from collections import OrderedDict
from threading import Lock
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import PlainTextResponse

from app.config import VK_CONFIRMATION_CODE, VK_GROUP_TOKEN, VK_SECRET
from app.core.analyzer import AnalysisRoute, analyze_query
from app.core.fact_checker import check_claim
from app.core.verifier import ConfidenceLevel, VerificationStatus

router = APIRouter()

logger = logging.getLogger(__name__)

# Защита от повторных Callback-событий для одного процесса приложения.
_EVENT_TTL_SECONDS = 6 * 60 * 60
_EVENT_CACHE_LIMIT = 10000
_seen_events: OrderedDict[str, float] = OrderedDict()
_event_lock = Lock()


def _claim_event(event_id: str) -> bool:
    """Атомарно отмечает новое событие; повторное событие возвращает False."""
    now = time.monotonic()

    with _event_lock:
        while _seen_events:
            oldest_id, received_at = next(iter(_seen_events.items()))
            if now - received_at <= _EVENT_TTL_SECONDS:
                break
            _seen_events.popitem(last=False)

        if event_id in _seen_events:
            return False

        _seen_events[event_id] = now

        while len(_seen_events) > _EVENT_CACHE_LIMIT:
            _seen_events.popitem(last=False)

        return True


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

    claim_preview = " ".join(result.claim.split())
    if len(claim_preview) > 240:
        claim_preview = claim_preview[:237] + "..."

    explanation = " ".join(result.explanation.split()).strip()
    if not explanation:
        explanation = "Подробное объяснение автоматически сформировать не удалось."

    reply = (
        f"«{claim_preview}» — {status_label}. "
        f"Уверенность: {confidence_label}. {explanation}"
    )

    # Показываем только источники, которые модель явно отметила как
    # поддерживающие или противоречащие утверждению. Просто найденная ссылка
    # без оценки релевантности не должна выглядеть доказательством.
    assessed_evidence = [
        item for item in result.evidence if item.supports_claim is not None
    ]
    if assessed_evidence:
        reply += "\n\nИсточники:"
        seen_urls = set()
        source_index = 0

        for item in assessed_evidence:
            url = (item.source_url or "").strip()
            if not url.startswith("https://") or url in seen_urls:
                continue

            seen_urls.add(url)
            title = " ".join(item.source_name.split()).strip() or "Источник"
            if len(title) > 120:
                title = title[:117] + "..."

            source_index += 1
            reply += f"\n{source_index}. {title}: {url}"

            if source_index >= 5:
                break
        if source_index == 0:
            reply += "\n\nСсылки не удалось проверить автоматически; их релевантность не подтверждена."
    elif result.evidence:
        explanation_lower = result.explanation.casefold()
        if "найдены кандидаты в источники, но ни один" in explanation_lower:
            reply += "\n\nКандидаты, не подтверждённые как релевантные, не перечислены как доказательства."
        elif "оценка gigachat не завершилась" in explanation_lower or "проверка ии не запущена" in explanation_lower:
            reply += (
                "\n\nАвтоматическая оценка найденных материалов не завершилась. "
                "Они не перечислены как доказательства, поскольку их релевантность не подтверждена."
            )
        elif "источники по теме" in explanation_lower:
            reply += (
                "\n\nНайдены источники по теме, но они не позволяют прямо подтвердить "
                "или опровергнуть утверждение. Их ссылки не показаны как доказательства."
            )
        else:
            reply += (
                "\n\nМатериалы были найдены, но бот не подтвердил их непосредственную "
                "релевантность этому утверждению. Нерелевантные ссылки не показаны. "
                "Это не означает, что подходящих исследований не существует."
            )
    elif "поиск не удалось полностью завершить" in explanation.casefold() or "техническ" in explanation.casefold():
        reply += (
            "\n\nПоиск завершился технической ошибкой. Отсутствие результата сейчас "
            "не означает, что научных доказательств не существует; попробуйте повторить позже."
        )
    else:
        reply += "\n\nПодходящие источники не найдены."

    reply += (
        "\n\nАвтоматическая проверка не заменяет медицинскую консультацию."
    )
    return reply[:3900]


def _event_random_id(event_id: str, peer_id: int) -> int:
    """Возвращает стабильный положительный ID для отправки одного события."""
    import hashlib

    digest = hashlib.sha256(
        f"{event_id}:{peer_id}".encode("utf-8")
    ).digest()
    return (int.from_bytes(digest[:4], "big") & 0x7FFFFFFF) or 1


def send_vk_message(
    peer_id: int,
    message: str,
    *,
    random_id: int | None = None,
) -> None:
    if not VK_GROUP_TOKEN:
        raise RuntimeError("Не настроена переменная VK_GROUP_TOKEN в .env")

    # Один random_id сохраняется при обеих попытках: тайм-аут не доказывает,
    # что VK не успел принять сообщение.
    if random_id is None:
        random_id = (uuid4().int % (2**31)) or 1

    payload = urllib.parse.urlencode({
        "access_token": VK_GROUP_TOKEN,
        "v": VK_API_VERSION,
        "peer_id": peer_id,
        "random_id": random_id,
        "message": message,
    }).encode("utf-8")

    for attempt in range(2):
        request = urllib.request.Request(
            "https://api.vk.com/method/messages.send",
            data=payload,
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (TimeoutError, urllib.error.URLError) as exc:
            is_timeout = (
                isinstance(exc, TimeoutError)
                or (
                    isinstance(exc, urllib.error.URLError)
                    and isinstance(exc.reason, TimeoutError)
                )
            )
            if attempt == 0 and is_timeout:
                logger.warning(
                    "VK messages.send timed out; retrying once "
                    "with the same random_id=%s",
                    random_id,
                )
                continue
            raise

        if "error" in result:
            error = result["error"]
            raise RuntimeError(
                f"VK API error {error.get('error_code', 'unknown')}: "
                f"{error.get('error_msg', 'unknown error')}"
            )
        return

def _process_message(peer_id: int, text: str, event_id: str | None) -> None:
    """Долгая проверка выполняется после подтверждения Callback."""
    logger.info("Started VK message processing: event_id=%s peer_id=%s",
                event_id or "missing", peer_id)
    try:
        reply = build_reply(text)
        stable_random_id = (
            _event_random_id(event_id, peer_id) if event_id else None
        )
        send_vk_message(peer_id, reply, random_id=stable_random_id)
        logger.info("VK reply sent: event_id=%s peer_id=%s",
                    event_id or "missing", peer_id)
    except Exception:
        # Фоновая ошибка не должна ронять обработчик Callback.
        logger.exception("VK message processing failed: event_id=%s peer_id=%s",
                         event_id or "missing", peer_id)


@router.post("/vk/callback")
async def vk_callback(
    request: Request,
    background_tasks: BackgroundTasks,
):
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

        if peer_id and isinstance(text, str) and text:
            try:
                peer_id = int(peer_id)
            except (TypeError, ValueError):
                logger.warning("Invalid peer_id in VK Callback")
                return PlainTextResponse("ok")

            raw_event_id = payload.get("event_id")
            event_id = (
                str(raw_event_id)
                if raw_event_id is not None and str(raw_event_id).strip()
                else None
            )

            if event_id is not None:
                if not _claim_event(event_id):
                    logger.info("Duplicate VK event ignored: event_id=%s",
                                event_id)
                    return PlainTextResponse("ok")
            else:
                # Без event_id невозможно надёжно отличить повтор от нового сообщения.
                logger.warning(
                    "VK message_new without event_id; deduplication unavailable"
                )

            background_tasks.add_task(
                _process_message, peer_id, text, event_id
            )

    # FastAPI запускает BackgroundTasks после отправки ответа клиенту.
    return PlainTextResponse("ok", background=background_tasks)
