"""Поиск по проверенным русскоязычным страницам официального сайта ВОЗ."""

import hashlib
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser

from app.sources.evidence import EvidenceRecord


WHO_PAGES = (
    (
        "https://www.who.int/ru/news/item/04-03-2015-who-calls-on-countries-to-reduce-sugars-intake-among-adults-and-children",
        "ВОЗ: сокращение потребления сахаров взрослыми и детьми",
    ),
    (
        "https://www.who.int/ru/news-room/fact-sheets/detail/sugars-and-dental-caries",
        "ВОЗ: сахар и кариес зубов",
    ),
)


class _WHOPageParser(HTMLParser):
    """Извлекает метаданные, заголовок и текст абзацев HTML-страницы."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts = []
        self.paragraphs = []
        self.description = ""
        self.in_title = False
        self.in_paragraph = False
        self.current_paragraph = []
        self.ignored_depth = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag in {"script", "style", "noscript"}:
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
        elif tag == "p":
            self.in_paragraph = True
            self.current_paragraph = []

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self.ignored_depth:
            self.ignored_depth -= 1
            return
        if self.ignored_depth:
            return

        if tag == "title":
            self.in_title = False
        elif tag == "p" and self.in_paragraph:
            text = re.sub(
                r"\s+", " ", "".join(self.current_paragraph)
            ).strip()
            if text:
                self.paragraphs.append(text)
            self.in_paragraph = False
            self.current_paragraph = []

    def handle_data(self, data):
        if self.ignored_depth:
            return
        if self.in_title:
            self.title_parts.append(data)
        if self.in_paragraph:
            self.current_paragraph.append(data)


def _fetch_page(url: str) -> tuple[str, str]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "AVRORA-medical-fact-checker/1.0"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        html = response.read().decode("utf-8", errors="replace")

    parser = _WHOPageParser()
    parser.feed(html)

    title = re.sub(r"\s+", " ", "".join(parser.title_parts)).strip()
    description = parser.description
    relevant_paragraphs = [
        paragraph
        for paragraph in parser.paragraphs
        if "сахар" in paragraph.lower()
        and (
            "свободн" in paragraph.lower()
            or "10%" in paragraph
            or "5%" in paragraph
        )
    ]

    # Метаданные предпочтительны, если в них есть сама рекомендация.
    if description and "сахар" in description.lower() and (
        "10%" in description
        or "5%" in description
        or "свободн" in description.lower()
    ):
        excerpt = description
    else:
        excerpt = "\n\n".join(relevant_paragraphs[:3])

    return title, excerpt[:3500]


def search_who_pages(claim: str, limit: int = 2) -> list[EvidenceRecord]:
    """Возвращает подходящие фрагменты страниц ВОЗ по теме сахаров."""
    if limit < 1:
        raise ValueError("limit должен быть не меньше 1")

    normalized_claim = claim.lower()
    if not any(word in normalized_claim for word in ("сахар", "сладк", "подсласт")):
        return []

    records = []
    for url, fallback_title in WHO_PAGES:
        try:
            page_title, excerpt = _fetch_page(url)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            continue

        if not excerpt or "сахар" not in excerpt.lower():
            continue

        item_id = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
        records.append(
            EvidenceRecord(
                evidence_id=f"who:{item_id}",
                source_id="who",
                source_name=page_title or fallback_title,
                source_url=url,
                excerpt=excerpt,
                source_type="официальная русскоязычная информационная страница ВОЗ",
                limitations=[
                    "Информационная страница ВОЗ; учитывайте её дату и контекст.",
                    "Совпадение фрагмента с темой утверждения само по себе не означает его подтверждения.",
                ],
            )
        )
        if len(records) >= limit:
            break

    return records
