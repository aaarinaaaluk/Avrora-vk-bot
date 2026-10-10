
from typing import Protocol


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
