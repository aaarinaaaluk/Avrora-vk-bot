from app.sources import who_search


def test_who_catalog_contains_only_russian_allowlisted_pages():
    assert who_search.WHO_PAGES
    assert all(page["source_id"] == "who" for page in who_search.WHO_PAGES)
    assert all(page["language"] == "ru" for page in who_search.WHO_PAGES)
    assert all(page["url"].startswith("https://www.who.int/ru/") for page in who_search.WHO_PAGES)
    assert not any(page["url"].startswith("https://www.who.int/en/") for page in who_search.WHO_PAGES)


def test_who_search_finds_russian_sugar_recommendation(monkeypatch):
    pages = [
        {
            "id": "who_healthy_diet_ru",
            "title": "Здоровое питание",
            "url": "https://www.who.int/ru/news-room/fact-sheets/detail/healthy-diet",
            "source_id": "who",
            "language": "ru",
            "search_keywords": ["сахар", "свободные сахара"],
        }
    ]
    monkeypatch.setattr(who_search, "WHO_PAGES", pages)
    monkeypatch.setattr(
        who_search,
        "_fetch_page",
        lambda url: (
            "Здоровое питание",
            ("Потребление свободных сахаров следует ограничивать менее 10% общей суточной энергии.",),
        ),
    )

    results = who_search.search_who_pages(
        "ВОЗ рекомендует ограничивать потребление свободных сахаров менее 10% суточной энергии"
    )

    assert len(results) == 1
    assert results[0].source_id == "who"
    assert results[0].source_url.startswith("https://www.who.int/ru/")
    assert "10%" in results[0].excerpt


def test_who_search_does_not_fetch_pages_for_unrelated_claim(monkeypatch):
    monkeypatch.setattr(who_search, "_fetch_page", lambda url: (_ for _ in ()).throw(AssertionError("should not fetch")))
    assert who_search.search_who_pages("Средиземноморская диета снижает риск сердечно-сосудистых заболеваний") == []
