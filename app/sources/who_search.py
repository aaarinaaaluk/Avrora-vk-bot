"""Поиск доказательных фрагментов в разрешённых русскоязычных страницах ВОЗ.

Для локального PDF-поиска используются только русскоязычные клинические
рекомендации. Англоязычные PDF ВОЗ удалены из локального каталога; этот адаптер
ходит только на заранее разрешённые URL https://www.who.int/ru/.
"""

import hashlib
import json
import re
import urllib.error
import urllib.request
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from app.sources.evidence import EvidenceRecord


PROJECT_ROOT = Path(__file__).resolve().parents[2]
WHO_CATALOG_PATH = PROJECT_ROOT / "data" / "who_nutrition_catalog.json"
WHO_BASE_URL = "https://www.who.int/ru/"


def _load_who_catalog() -> list[dict[str, Any]]:
    """Загружает список разрешённых русскоязычных страниц ВОЗ.

    Каталог намеренно является allowlist: функция не ищет и не открывает URL,
    поступившие из пользовательского текста или из ответа языковой модели.
    """
    if not WHO_CATALOG_PATH.is_file():
        return []

    with WHO_CATALOG_PATH.open(encoding="utf-8") as file:
        catalog = json.load(file)

    if not isinstance(catalog, list):
        raise ValueError("Каталог русскоязычных страниц ВОЗ должен быть списком.")

    pages = []
    for item in catalog:
        if not isinstance(item, dict):
            continue
        url = item.get("url")
        if (
            item.get("source_id") != "who"
            or item.get("language") != "ru"
            or not isinstance(url, str)
            or not url.startswith(WHO_BASE_URL)
        ):
            continue
        if not isinstance(item.get("title"), str) or not item["title"].strip():
            continue
        keywords = item.get("search_keywords")
        if not isinstance(keywords, list) or not all(
            isinstance(keyword, str) and keyword.strip() for keyword in keywords
        ):
            continue
        pages.append(item)
    return pages


# Каталог мал, поэтому перечитывать его при каждом сообщении не нужно.
WHO_PAGES = _load_who_catalog()


class _WHOPageParser(HTMLParser):
    """Извлекает заголовок и текстовые блоки HTML, пропуская навигацию и скрипты."""

    _IGNORED_TAGS = {"script", "style", "noscript", "svg", "nav", "footer"}
    _BLOCK_TAGS = {"h1", "h2", "h3", "p", "li"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.blocks: list[str] = []
        self.description = ""
        self.in_title = False
        self.ignored_depth = 0
        self.current_block_tag: str | None = None
        self.current_block: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self._IGNORED_TAGS:
            self.ignored_depth += 1
            return
        if self.ignored_depth:
            return

        if tag == "meta":
            key = (attrs.get("name") or attrs.get("property") or "").lower()
            if key in {"description", "og:description"} and not self.description:
                self.description = attrs.get("content", "").strip()
        elif tag == "title":
            self.in_title = True
        elif tag in self._BLOCK_TAGS and self.current_block_tag is None:
            self.current_block_tag = tag
            self.current_block = []

    def handle_endtag(self, tag):
        if tag in self._IGNORED_TAGS and self.ignored_depth:
            self.ignored_depth -= 1
            return
        if self.ignored_depth:
            return

        if tag == "title":
            self.in_title = False
        elif tag == self.current_block_tag:
            text = re.sub(r"\s+", " ", "".join(self.current_block)).strip()
            if text:
                self.blocks.append(text)
            self.current_block_tag = None
            self.current_block = []

    def handle_data(self, data):
        if self.ignored_depth:
            return
        if self.in_title:
            self.title_parts.append(data)
        if self.current_block_tag is not None:
            self.current_block.append(data)


def _safe_who_url(url: str) -> bool:
    return url.startswith(WHO_BASE_URL) and "\x00" not in url


@lru_cache(maxsize=32)
def _fetch_page(url: str) -> tuple[str, tuple[str, ...]]:
    """Загружает страницу ВОЗ; успешные результаты кэшируются на время процесса."""
    if not _safe_who_url(url):
        raise ValueError("Разрешены только URL русскоязычного сайта ВОЗ.")

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "AVRORA-medical-fact-checker/1.0"},
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        # Ограничиваем объём чтения, чтобы страница с некорректным ответом
        # не могла неограниченно потреблять память.
        html = response.read(2_500_000).decode("utf-8", errors="replace")

    parser = _WHOPageParser()
    parser.feed(html)
    title = re.sub(r"\s+", " ", "".join(parser.title_parts)).strip()
    blocks = list(parser.blocks)
    if parser.description and parser.description not in blocks:
        blocks.insert(0, parser.description)
    # Убираем дубликаты, сохраняя исходный порядок.
    unique_blocks = tuple(dict.fromkeys(blocks))
    return title, unique_blocks


def _matching_keywords(claim: str, page: dict[str, Any]) -> list[str]:
    normalized_claim = re.sub(r"\s+", " ", claim.casefold())
    return [
        keyword.casefold()
        for keyword in page.get("search_keywords", [])
        if keyword.casefold() in normalized_claim
    ]


def _select_excerpt(
    claim: str,
    paragraphs: tuple[str, ...],
    matching_keywords: list[str],
) -> str:
    """Выбирает фрагменты, в которых действительно встречаются слова запроса."""
    normalized_claim = claim.casefold()
    stop_words = {
        "это", "как", "что", "или", "для", "при", "после", "перед", "через",
        "если", "когда", "который", "которая", "которые", "быть", "может",
        "могут", "является", "являются", "снижает", "повышает", "приводит",
        "риск", "уровень", "организм", "человек", "люди", "среди", "также",
        "более", "менее", "очень", "высокое", "высокий", "низкое", "низкий",
    }
    claim_terms = {
        token for token in re.findall(r"[а-яёa-z0-9%]+", normalized_claim)
        if len(token) >= 4 and token not in stop_words
    }
    # Сохраняем и целевые фразы-ключи, чтобы числа вроде 10% не терялись.
    selected: list[tuple[int, int, str]] = []
    for index, paragraph in enumerate(paragraphs):
        normalized_paragraph = paragraph.casefold()
        keyword_hits = sum(
            1 for keyword in matching_keywords if keyword in normalized_paragraph
        )
        term_hits = sum(
            1 for term in claim_terms if term in normalized_paragraph
        )
        score = keyword_hits * 3 + term_hits
        if score > 0:
            selected.append((score, index, paragraph))

    if not selected:
        return ""

    selected.sort(key=lambda item: (-item[0], item[1]))
    excerpts = [item[2] for item in selected[:5]]
    return "\n\n".join(excerpts)[:3500]


def search_who_pages(claim: str, limit: int = 2) -> list[EvidenceRecord]:
    """Ищет только в разрешённых русскоязычных страницах ВОЗ.

    Это не полнотекстовый поиск по всему WHO.int: используется поддерживаемый
    список официальных русскоязычных страниц и отбор по ключевым словам.
    """
    if limit < 1:
        raise ValueError("limit должен быть не меньше 1")
    if not claim.strip():
        return []

    candidates: list[tuple[int, dict[str, Any], list[str]]] = []
    for page in WHO_PAGES:
        keywords = _matching_keywords(claim, page)
        if keywords:
            candidates.append((len(keywords), page, keywords))
    candidates.sort(key=lambda item: (-item[0], item[1]["id"]))

    records: list[EvidenceRecord] = []
    # Не загружаем десятки страниц на один запрос; проверяем только самые
    # подходящие записи каталога, а уже загруженные страницы берём из кэша.
    for _, page, keywords in candidates[: max(limit * 2, limit)]:
        url = page["url"]
        try:
            page_title, paragraphs = _fetch_page(url)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            continue

        excerpt = _select_excerpt(claim, paragraphs, keywords)
        if not excerpt:
            continue

        item_id = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
        records.append(
            EvidenceRecord(
                evidence_id=f"who:{item_id}",
                source_id="who",
                source_name=page_title or page["title"],
                source_url=url,
                excerpt=excerpt,
                source_type="официальная русскоязычная информационная страница ВОЗ",
                limitations=[
                    "Используется русскоязычная информационная страница ВОЗ, а не весь корпус руководств организации.",
                    "Совпадение фрагмента с темой утверждения само по себе не доказывает утверждение.",
                ],
            )
        )
        if len(records) >= limit:
            break

    return records
