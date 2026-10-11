"""Клиенты языковой модели и подготовка контекста доказательств."""

import base64
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from threading import Lock
from typing import Protocol
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GIGACHAT_CA_FILE = (
    PROJECT_ROOT / "certs" / "russian_trusted_root_ca_pem.crt"
)


def _create_gigachat_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    if GIGACHAT_CA_FILE.is_file():
        context.load_verify_locations(cafile=str(GIGACHAT_CA_FILE))
    return context

from pydantic import BaseModel, Field

from app.config import (
    GIGACHAT_API_BASE_URL,
    GIGACHAT_AUTH_KEY,
    GIGACHAT_CLIENT_ID,
    GIGACHAT_CLIENT_SECRET,
    GIGACHAT_MODEL,
    GIGACHAT_OAUTH_URL,
    GIGACHAT_SCOPE,
)
from app.sources.text_search import SearchResult


class LLMClient(Protocol):
    """Интерфейс подключаемой языковой модели."""

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


class GigaChatClient:
    """Минимальный клиент GigaChat API с OAuth-токеном в памяти процесса.

    Ключ авторизации никогда не передаётся в логи или ответы пользователю.
    SSL-проверка не отключается. Access token запрашивается повторно заранее,
    поскольку срок его действия ограничен.
    """

    def __init__(
        self,
        auth_key: str = "",
        client_id: str = "",
        client_secret: str = "",
        model: str = "GigaChat",
        api_base_url: str = "https://api.giga.chat",
        oauth_url: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
        scope: str = "GIGACHAT_API_PERS",
    ) -> None:
        self.auth_key = auth_key.strip()
        if not self.auth_key and client_id.strip() and client_secret.strip():
            raw_credentials = f"{client_id.strip()}:{client_secret.strip()}".encode("utf-8")
            self.auth_key = base64.b64encode(raw_credentials).decode("ascii")
        self.model = model.strip() or "GigaChat"
        self.api_base_url = api_base_url.rstrip("/")
        self.oauth_url = oauth_url
        self.scope = scope
        self._access_token = ""
        self._token_expires_at = 0.0
        self._token_lock = Lock()
        self._usage_lock = Lock()
        self._usage = {
            "calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }

    def usage_snapshot(self) -> dict[str, int]:
        """Возвращает статистику расхода токенов без содержимого запросов."""
        with self._usage_lock:
            return dict(self._usage)

    @property
    def is_configured(self) -> bool:
        return bool(self.auth_key)

    @classmethod
    def from_env(cls) -> "GigaChatClient":
        return cls(
            auth_key=GIGACHAT_AUTH_KEY,
            client_id=GIGACHAT_CLIENT_ID,
            client_secret=GIGACHAT_CLIENT_SECRET,
            model=GIGACHAT_MODEL,
            api_base_url=GIGACHAT_API_BASE_URL,
            oauth_url=GIGACHAT_OAUTH_URL,
            scope=GIGACHAT_SCOPE,
        )

    def _authorization_value(self) -> str:
        if self.auth_key.lower().startswith("basic "):
            return self.auth_key
        return f"Basic {self.auth_key}"

    @staticmethod
    def _read_json(request: urllib.request.Request, timeout: int = 30) -> dict:
        try:
            with urllib.request.urlopen(
                request,
                timeout=timeout,
                context=_create_gigachat_ssl_context(),
            ) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            # Не печатаем заголовки запроса, в которых могут быть секреты.
            try:
                details = exc.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                details = ""
            raise RuntimeError(
                f"GigaChat API вернул HTTP {exc.code}. {details}"
            ) from None
        except (urllib.error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"Не удалось подключиться к GigaChat API: {exc}") from None

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            raise RuntimeError("GigaChat API вернул некорректный JSON.") from None
        if not isinstance(data, dict):
            raise RuntimeError("GigaChat API вернул неожиданный формат ответа.")
        return data

    def _get_access_token(self) -> str:
        if not self.is_configured:
            raise RuntimeError(
                "Не настроен GIGACHAT_AUTH_KEY (либо GIGACHAT_CLIENT_ID и "
                "GIGACHAT_CLIENT_SECRET) в файле .env."
            )

        with self._token_lock:
            if self._access_token and time.monotonic() < self._token_expires_at:
                return self._access_token

            body = urllib.parse.urlencode({"scope": self.scope}).encode("utf-8")
            request = urllib.request.Request(
                self.oauth_url,
                data=body,
                method="POST",
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                    "RqUID": str(uuid4()),
                    "Authorization": self._authorization_value(),
                },
            )
            data = self._read_json(request, timeout=30)
            token = data.get("access_token")
            if not isinstance(token, str) or not token:
                raise RuntimeError("OAuth GigaChat не вернул access_token.")

            # В документации срок токена — 30 минут. Обновляем за минуту до истечения.
            expires_at_ms = data.get("expires_at")
            if isinstance(expires_at_ms, (int, float)):
                remaining_seconds = max(1, (expires_at_ms / 1000) - time.time() - 60)
                self._token_expires_at = time.monotonic() + min(remaining_seconds, 1740)
            else:
                self._token_expires_at = time.monotonic() + 1740
            self._access_token = token
            return token

    def generate(self, prompt: str) -> str:
        """Отправляет запрос в POST /chat/completions."""
        token = self._get_access_token()
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "stream": False,
            "repetition_penalty": 1,
        }
        request = urllib.request.Request(
            f"{self.api_base_url}/v1/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        data = self._read_json(request, timeout=60)

        usage = data.get("usage", {})
        if not isinstance(usage, dict):
            usage = {}

        def token_count(name: str) -> int:
            value = usage.get(name, 0)
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                return value
            return 0

        prompt_tokens = token_count("prompt_tokens")
        completion_tokens = token_count("completion_tokens")
        total_tokens = token_count("total_tokens")
        if "total_tokens" not in usage:
            total_tokens = prompt_tokens + completion_tokens

        with self._usage_lock:
            self._usage["calls"] += 1
            self._usage["prompt_tokens"] += prompt_tokens
            self._usage["completion_tokens"] += completion_tokens
            self._usage["total_tokens"] += total_tokens
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise RuntimeError("GigaChat API не вернул текст ответа модели.") from None
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("GigaChat API вернул пустой ответ модели.")
        return content.strip()


def create_llm_client() -> GigaChatClient | None:
    """Возвращает реальный клиент, только если настройки API заданы."""
    client = GigaChatClient.from_env()
    return client if client.is_configured else None


class EvidenceAssessment(BaseModel):
    """Структурированная оценка найденного фрагмента."""

    relevant: bool = False
    supports_claim: bool | None = None
    explanation: str = (
        "Недостаточно данных для оценки найденных фрагментов."
    )
    limitations: list[str] = Field(default_factory=list)
    source_url: str | None = None
    page_number: int | None = None


def build_evidence_context(results: list[SearchResult]) -> str:
    """Формирует контекст локальных фрагментов и предупреждение о поиске."""
    if not results:
        return "Фрагменты источников по запросу не найдены."
    sections = [
        "Важно: найденные фрагменты получены поиском по совпадению слов. "
        "Они не считаются подтверждёнными доказательствами сами по себе. "
        "Не делай вывод о достоверности медицинского утверждения только "
        "по наличию совпадающих слов. Учитывай контекст и ограничения источника."
    ]

    for index, result in enumerate(results, start=1):
        sections.append(
            f"Фрагмент {index}\n"
            f"Документ: {result.document_title}\n"
            f"Ссылка: {result.source_url}\n"
            f"Страница: {result.page_number}\n"
            f"Текст фрагмента:\n{result.text}"
        )

    return "\n\n".join(sections)
