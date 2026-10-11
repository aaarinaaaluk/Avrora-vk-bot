"""Загрузка конфигурации из переменных окружения и файла .env."""

import os
from dotenv import load_dotenv

# .env не добавляется в git и используется только локально/на сервере.
load_dotenv()


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


VK_GROUP_TOKEN = env("VK_GROUP_TOKEN")
VK_CONFIRMATION_CODE = env("VK_CONFIRMATION_CODE")
VK_SECRET = env("VK_SECRET")

GIGACHAT_AUTH_KEY = env("GIGACHAT_AUTH_KEY")
GIGACHAT_CLIENT_ID = env("GIGACHAT_CLIENT_ID")
GIGACHAT_CLIENT_SECRET = env("GIGACHAT_CLIENT_SECRET")
GIGACHAT_MODEL = env("GIGACHAT_MODEL", "GigaChat")
GIGACHAT_SCOPE = env("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
GIGACHAT_API_BASE_URL = env("GIGACHAT_API_BASE_URL", "https://api.giga.chat")
GIGACHAT_OAUTH_URL = env(
    "GIGACHAT_OAUTH_URL",
    "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
)

GOOGLE_FACT_CHECK_API_KEY = env("GOOGLE_FACT_CHECK_API_KEY")
NCBI_API_KEY = env("NCBI_API_KEY")
NCBI_EMAIL = env("NCBI_EMAIL")
