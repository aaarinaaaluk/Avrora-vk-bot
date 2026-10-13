import json

from app.sources import document_search
from app.sources.pdf_reader import PDFDocument, PDFPage


def test_search_documents_uses_multiple_enabled_catalog_entries(
    tmp_path, monkeypatch
):
    documents_dir = tmp_path / "documents"
    documents_dir.mkdir()

    (documents_dir / "one.pdf").write_bytes(b"test")
    (documents_dir / "two.pdf").write_bytes(b"test")
    (documents_dir / "unregistered.pdf").write_bytes(b"test")
    (documents_dir / "disabled.pdf").write_bytes(b"test")

    catalog_path = tmp_path / "document_catalog.json"
    catalog_path.write_text(
        json.dumps(
            [
                {
                    "id": "guideline_one",
                    "filename": "one.pdf",
                    "title": "Рекомендация по витамину D",
                    "source_id": "ru_moh_clinical_guidelines",
                    "source_url": "https://example.org/one",
                    "enabled": True,
                },
                {
                    "id": "guideline_two",
                    "filename": "two.pdf",
                    "title": "Рекомендация по рахиту",
                    "source_id": "ru_moh_clinical_guidelines",
                    "source_url": "https://example.org/two",
                    "enabled": True,
                },
                {
                    "id": "disabled_guideline",
                    "filename": "disabled.pdf",
                    "title": "Отключённая рекомендация",
                    "source_id": "ru_moh_clinical_guidelines",
                    "source_url": "https://example.org/disabled",
                    "enabled": False,
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(document_search, "DOCUMENTS_DIR", documents_dir)
    monkeypatch.setattr(
        document_search, "DOCUMENT_CATALOG_PATH", catalog_path
    )

    def fake_extract_pdf_text(pdf_path, source_url, title):
        return PDFDocument(
            title=title,
            source_url=source_url,
            page_count=1,
            pages=[
                PDFPage(
                    page_number=1,
                    text="Дефицит витамина D вызывает рахит у детей.",
                )
            ],
        )

    monkeypatch.setattr(
        document_search, "extract_pdf_text", fake_extract_pdf_text
    )

    results = document_search.search_documents(
        "Дефицит витамина D вызывает рахит у детей",
        limit=5,
    )

    assert len(results) == 2
    assert {result.document_title for result in results} == {
        "Рекомендация по витамину D",
        "Рекомендация по рахиту",
    }
    assert {result.source_url for result in results} == {
        "https://example.org/one",
        "https://example.org/two",
    }


def test_search_documents_rejects_invalid_limit():
    import pytest

    with pytest.raises(ValueError, match="limit"):
        document_search.search_documents("витамин", limit=0)


def test_load_document_catalog_ignores_disabled_and_invalid_entries(
    tmp_path, monkeypatch
):
    catalog_path = tmp_path / "document_catalog.json"
    catalog_path.write_text(
        json.dumps(
            [
                {
                    "id": "enabled",
                    "filename": "good.pdf",
                    "title": "Разрешённый документ",
                    "source_id": "ru_moh_clinical_guidelines",
                    "source_url": "https://example.org/good",
                    "enabled": True,
                },
                {
                    "id": "disabled",
                    "filename": "disabled.pdf",
                    "title": "Отключённый документ",
                    "source_id": "ru_moh_clinical_guidelines",
                    "source_url": "https://example.org/disabled",
                    "enabled": False,
                },
                {
                    "id": "path",
                    "filename": "../outside.pdf",
                    "title": "Недопустимый путь",
                    "source_id": "ru_moh_clinical_guidelines",
                    "source_url": "https://example.org/outside",
                    "enabled": True,
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        document_search, "DOCUMENT_CATALOG_PATH", catalog_path
    )

    catalog = document_search.load_document_catalog()

    assert len(catalog) == 1
    assert catalog[0]["filename"] == "good.pdf"


def test_unrelated_pdf_is_not_extracted_and_relevant_pdf_is_cached(
    tmp_path, monkeypatch
):
    documents_dir = tmp_path / "documents"
    documents_dir.mkdir()
    (documents_dir / "diabetes.pdf").write_bytes(b"pdf")
    (documents_dir / "flu.pdf").write_bytes(b"pdf")
    catalog_path = tmp_path / "document_catalog.json"
    catalog_path.write_text(
        json.dumps(
            [
                {
                    "id": "diabetes", "filename": "diabetes.pdf",
                    "title": "Сахарный диабет", "source_id": "ru_moh_clinical_guidelines",
                    "source_url": "https://example.org/diabetes", "enabled": True,
                    "language": "ru", "search_keywords": ["диабет", "инсулин", "глюкоза"],
                },
                {
                    "id": "flu", "filename": "flu.pdf", "title": "Грипп",
                    "source_id": "ru_moh_clinical_guidelines",
                    "source_url": "https://example.org/flu", "enabled": True,
                    "language": "ru", "search_keywords": ["грипп", "инфлюэнца"],
                },
            ], ensure_ascii=False,
        ), encoding="utf-8"
    )
    monkeypatch.setattr(document_search, "DOCUMENTS_DIR", documents_dir)
    monkeypatch.setattr(document_search, "DOCUMENT_CATALOG_PATH", catalog_path)
    document_search._extract_pdf_text_cached.cache_clear()
    calls = []

    def fake_extract_pdf_text(pdf_path, source_url, title):
        calls.append(title)
        return PDFDocument(
            title=title, source_url=source_url, page_count=1,
            pages=[PDFPage(page_number=1, text="Диабет требует контроля глюкозы и инсулина.")],
        )

    monkeypatch.setattr(document_search, "extract_pdf_text", fake_extract_pdf_text)
    document_search.search_documents("Как контролировать диабет и глюкозу")
    document_search.search_documents("Как контролировать диабет и глюкозу")

    assert calls == ["Сахарный диабет"]
    document_search._extract_pdf_text_cached.cache_clear()


def test_generic_diet_word_does_not_select_celiac_pdf():
    item = {
        "title": "Целиакия",
        "filename": "КР404.pdf",
        "search_keywords": ["целиакия", "глютен", "безглютеновая диета"],
    }
    assert not document_search._document_matches_query(
        item,
        "Средиземноморская диета снижает риск сердечно-сосудистых заболеваний",
    )


def test_specific_gluten_query_selects_celiac_pdf():
    item = {
        "title": "Целиакия",
        "filename": "КР404.pdf",
        "search_keywords": ["целиакия", "глютен", "безглютеновая диета"],
    }
    assert document_search._document_matches_query(
        item,
        "Безглютеновая диета нужна при целиакии",
    )


def test_generic_acid_term_does_not_select_folate_anemia_for_omega3_claim():
    item = {
        "title": "Фолиеводефицитная анемия",
        "filename": "КР540.pdf",
        "search_keywords": ["фолиевая кислота", "фолат", "анемия"],
    }
    assert not document_search._document_matches_query(
        item,
        "Омега-3 полиненасыщенные жирные кислоты защищают сетчатку от возрастной дегенерации",
    )
