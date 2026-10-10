
from typing import Protocol

from app.sources.text_search import SearchResult


class LLMClient(Protocol):
    """Интерфейс для подключения языковой модели."""

    def generate(self, prompt: str) -> str:
        """Возвращает текстовый ответ модели."""
        ...


class MockLLMClient:
    """Заглушка для разработки без API-ключа."""

    def generate(self, prompt: str) -> str:
        return (
            "Это тестовый ответ. Он не является медицинским "
            "доказательством и требует проверки по источникам."
        )


def build_evidence_context(results: list[SearchResult]) -> str:
    """Формирует контекст из найденных фрагментов с указанием источников."""
    if not results:
        return "Проверенные фрагменты источников не найдены."

    sections = []

    for index, result in enumerate(results, start=1):
        sections.append(
            f"Фрагмент {index}\n"
            f"Документ: {result.document_title}\n"
            f"Ссылка: {result.source_url}\n"
            f"Страница: {result.page_number}\n"
            f"Текст фрагмента:\n{result.text}"
        )

    return "\n\n".join(sections)
