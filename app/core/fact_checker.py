"""Оркестрация поиска разрешённых источников и оценки GigaChat."""

import logging
import re

from app.core.llm import create_llm_client
from app.core.verifier import VerificationResult, verify_claim
from app.sources.document_search import search_documents
from app.sources.evidence import EvidenceRecord
from app.sources.factcheck_search import search_fact_checks
from app.sources.pubmed_search import search_pubmed_with_status
from app.sources.who_search import search_who_pages


logger = logging.getLogger(__name__)

# Резервные англоязычные запросы для частых тем проекта. Они нужны только для
# поиска в PubMed при тайм-ауте/ошибке перевода, а не для вынесения вердикта.
_PUBMED_FALLBACK_RULES: tuple[tuple[str, str], ...] = (
    (r"mind\s+диет|диет\w*\s+mind|mind diet|когнитивн\w*\s+спад", "MIND diet cognitive decline dementia 7.5 years"),
    (r"интервальн\w*\s+голод|аутофаг", "intermittent fasting autophagy humans"),
    (r"ограничен\w*\s+калор|биологическ\w*\s+старен", "caloric restriction biological aging biomarkers humans"),
    (r"растительн\w*\s+диет|системн\w*\s+воспален", "plant-based diet systemic inflammation markers adults"),
    (r"разнообрази\w*\s+пищев\w*\s+клетчат|микробиом", "dietary fiber gut microbiome richness diversity"),
    (r"ограничительн\w*\s+диет|возврат\w*\s+вес|метаболическ\w*\s+адаптац", "dieting metabolic adaptation weight regain"),
    (r"высокобелков\w*\s+завтрак|грелин", "high protein breakfast ghrelin evening food intake"),
    (r"дефицит\w*\s+калори|жиров\w*\s+масс", "energy deficit fat mass loss caloric restriction adults"),
    (r"сахарозаменител|подсластител", "non-sugar sweeteners long-term weight management obesity adults"),
    (r"ж[её]сткост\w*\s+артер|поваренн\w*\s+сол|натри", "dietary sodium arterial stiffness blood pressure"),
    (r"омега\s*[-–]?\s*3|сетчатк|макулярн\w*\s+дегенерац", "omega-3 age-related macular degeneration retina clinical trial"),
    (r"витамин\w*\s+d|остеопороз|синтез\w*\s+кальци", "vitamin D deficiency calcium metabolism osteoporosis adults"),
    (r"свободн\w*\s+сахар|сахар\w*\s+суточн\w*\s+энерг", "free sugars intake daily energy recommendation"),
    (r"средиземноморск\w*\s+диет|сердечно-сосудист\w*\s+заболев", "Mediterranean diet cardiovascular disease prevention"),
    (r"кетоген\w*\s+диет|кето\w*\s+диет", "ketogenic diet cognitive function mood emotional health"),
    (r"глютен|целиаки", "gluten-free diet healthy adults health outcomes"),
    (r"ультра.?обработан\w*\s+продукт|кишечн\w*\s+барьер", "ultra-processed foods intestinal barrier gut microbiota inflammation"),
)

_QUERY_GENERIC_TOKENS = {
    "who", "diet", "dietary", "disease", "diseases", "risk", "health", "study",
    "studies", "research", "review", "systematic", "effect", "effects", "impact",
    "associated", "association", "adult", "adults", "human", "humans", "patient",
    "patients", "long", "term", "clinical", "trial", "trials", "intake", "use",
    "using", "benefit", "benefits", "prevention", "prevent", "reduce", "reduces",
}


def _fallback_pubmed_query_from_claim(claim: str) -> str | None:
    """Возвращает заранее подготовленный поисковый запрос для известных тем."""
    normalized = re.sub(r"\s+", " ", claim.casefold()).strip()
    for pattern, query in _PUBMED_FALLBACK_RULES:
        if re.search(pattern, normalized, flags=re.IGNORECASE):
            return query
    return None


def _query_signature(query: str) -> set[str]:
    terms = set(re.findall(r"[a-z0-9]+", query.casefold()))
    return {term for term in terms if len(term) > 2 and term not in _QUERY_GENERIC_TOKENS}


def _build_pubmed_query(claim: str, llm_client) -> tuple[str, bool]:
    """Возвращает английский запрос и признак технического сбоя перевода."""
    fallback = _fallback_pubmed_query_from_claim(claim)
    if llm_client is None:
        if fallback:
            logger.info("Using topic-specific PubMed fallback query without GigaChat")
            return fallback, False
        logger.warning("GigaChat is not configured and no topic fallback was found for PubMed")
        return claim, True

    prompt = (
        "Преобразуй медицинское утверждение ниже в короткий поисковый запрос "
        "на английском языке для PubMed. Сохрани ключевые медицинские понятия, "
        "не добавляй фактов и не оценивай утверждение. Верни только запрос, "
        "не более 12 слов. Не добавляй кавычки, пояснения или метки.\n\nУтверждение: "
        + claim[:1000]
    )
    try:
        query = llm_client.generate(prompt).strip().strip("\"'`")
        query = re.sub(r"\s+", " ", query)
        contains_latin = bool(re.search(r"[A-Za-z]", query))
        usable = bool(query and len(query) <= 250 and "\n" not in query and contains_latin)
        if usable and fallback:
            query_signature = _query_signature(query)
            fallback_signature = _query_signature(fallback)
            # Не даём случайному/сбитому ответу модели превратиться в запрос
            # по посторонней теме (например, классификация рака вместо сахаров).
            if query_signature and fallback_signature and not (query_signature & fallback_signature):
                logger.warning("PubMed translation did not preserve claim topic; using fallback query")
                return fallback, False
        if usable:
            return query, False
        logger.warning("GigaChat returned an unusable PubMed search translation")
    except Exception as exc:
        logger.warning("PubMed query translation failed (%s)", type(exc).__name__)

    if fallback:
        logger.info("Using topic-specific PubMed fallback query after translation failure")
        return fallback, False
    return claim, True


def _pubmed_query_from_claim(claim: str, llm_client) -> str:
    """Совместимая обёртка для перевода запроса; используется и в тестах."""
    return _build_pubmed_query(claim, llm_client)[0]


def _collect_evidence_with_status(
    claim: str,
    llm_client=None,
) -> tuple[list, list[EvidenceRecord], list[str]]:
    """Собирает источники и сохраняет названия сервисов, поиск которых не удался."""
    local_results = []
    failures: list[str] = []
    try:
        local_results = [
            result
            for result in search_documents(claim, limit=5)
            if len(result.matched_terms) >= 2
        ]
    except (OSError, ValueError) as exc:
        logger.warning("Local document search failed (%s)", type(exc).__name__)
        failures.append("локальный поиск PDF")
        local_results = []

    external: list[EvidenceRecord] = []
    who_results: list[EvidenceRecord] = []
    who_count = pubmed_count = fact_check_count = 0
    try:
        who_results = search_who_pages(claim, limit=2)
        who_count = len(who_results)
        external.extend(who_results)
    except Exception as exc:
        logger.warning("WHO search failed (%s)", type(exc).__name__)
        failures.append("сайт ВОЗ")

    explicit_who_claim = bool(re.search(r"\b(?:воз|who)\b", claim, re.IGNORECASE))
    if explicit_who_claim and who_results:
        # Для проверки того, что именно рекомендует ВОЗ, официальный источник
        # приоритетнее случайной сопутствующей статьи из PubMed. Это также
        # избегает лишнего токена на перевод и не добавляет посторонние ссылки.
        logger.info("PubMed skipped: an official WHO page was found for an explicit WHO claim")
    else:
        translated_query, translation_failed = _build_pubmed_query(claim, llm_client)
        try:
            outcome = search_pubmed_with_status(translated_query, limit=3)
            pubmed_count = len(outcome.records)
            external.extend(outcome.records)
            if outcome.status == "unavailable":
                failures.append("PubMed")
        except Exception as exc:
            # Защитный catch: ошибка адаптера не должна обрывать обработку сообщения VK.
            logger.warning("PubMed retrieval failed unexpectedly (%s)", type(exc).__name__)
            failures.append("PubMed")
        if translation_failed:
            failures.append("перевод поискового запроса PubMed")

    try:
        fact_check_results = search_fact_checks(claim, limit=3)
        fact_check_count = len(fact_check_results)
        external.extend(fact_check_results)
    except Exception as exc:
        logger.warning("Fact Check search failed (%s)", type(exc).__name__)
        failures.append("Google Fact Check Tools")

    seen_urls = {item.source_url for item in local_results if item.source_url}
    deduplicated: list[EvidenceRecord] = []
    for item in external:
        if item.source_url in seen_urls:
            continue
        seen_urls.add(item.source_url)
        deduplicated.append(item)

    selected_local = local_results[:3]
    selected_external = deduplicated[:6]
    external_ids_by_source: dict[str, list[str]] = {}
    for item in selected_external:
        external_ids_by_source.setdefault(item.source_id, []).append(item.evidence_id)
    logger.info(
        "Evidence retrieval complete: local=%d WHO=%d PubMed=%d fact_check=%d external_unique=%d failures=%d",
        len(local_results), who_count, pubmed_count, fact_check_count,
        len(deduplicated), len(failures),
    )
    logger.info(
        "Evidence candidates passed to verifier: local_count=%d external_ids_by_source=%s retrieval_failures=%s",
        len(selected_local), external_ids_by_source, list(dict.fromkeys(failures)),
    )
    return selected_local, selected_external, list(dict.fromkeys(failures))


def collect_evidence(claim: str, llm_client=None) -> tuple[list, list[EvidenceRecord]]:
    """Ищет разрешённые источники; сохранён для обратной совместимости."""
    local_results, external_results, _ = _collect_evidence_with_status(claim, llm_client)
    return local_results, external_results


def check_claim(claim: str) -> VerificationResult:
    """Полная проверка: сбор источников, оценка модели, безопасный fallback."""
    client = create_llm_client()
    local_results, external_results, retrieval_failures = _collect_evidence_with_status(
        claim, llm_client=client
    )
    result = verify_claim(
        claim,
        search_results=local_results,
        external_evidence=external_results,
        llm_client=client,
        retrieval_warnings=retrieval_failures,
    )

    if client is not None:
        usage = client.usage_snapshot()
        if usage["calls"] > 0:
            logger.info(
                "GigaChat usage: calls=%d prompt_tokens=%d completion_tokens=%d total_tokens=%d",
                usage["calls"], usage["prompt_tokens"],
                usage["completion_tokens"], usage["total_tokens"],
            )

    return result
