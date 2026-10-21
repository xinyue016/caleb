from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def load_dotenv(path: Path) -> None:
    """Small .env loader so the project has zero required dependencies."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8787"))
    data_dir: Path = Path(os.getenv("CALEB_DATA_DIR", str(BASE_DIR / "data")))
    provider: str = os.getenv("CALEB_PROVIDER", "mock").strip().lower()
    model: str = os.getenv("CALEB_MODEL", "gpt-5.1")
    api_key: str = os.getenv("OPENAI_API_KEY", "") or os.getenv("CALEB_API_KEY", "")
    base_url: str = os.getenv("CALEB_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    temperature: float = float(os.getenv("CALEB_TEMPERATURE", "0.82"))
    max_output_tokens: int = int(os.getenv("CALEB_MAX_OUTPUT_TOKENS", "700"))
    request_timeout: int = int(os.getenv("CALEB_REQUEST_TIMEOUT", "75"))
    history_limit: int = int(os.getenv("CALEB_HISTORY_LIMIT", "14"))
    allow_public_webhooks: bool = env_bool("CALEB_ALLOW_PUBLIC_WEBHOOKS", True)

    wechat_token: str = os.getenv("WECHAT_TOKEN", "")
    wechat_plain_mode: bool = env_bool("WECHAT_PLAIN_MODE", True)

    qq_app_id: str = os.getenv("QQ_BOT_APP_ID", "")
    qq_client_secret: str = os.getenv("QQ_BOT_CLIENT_SECRET", "")
    qq_private_key: str = os.getenv("QQ_BOT_PRIVATE_KEY", "")
    qq_public_key: str = os.getenv("QQ_BOT_PUBLIC_KEY", "")
    qq_api_base: str = os.getenv("QQ_BOT_API_BASE", "https://api.sgroup.qq.com").rstrip("/")
    qq_token_url: str = os.getenv("QQ_BOT_TOKEN_URL", "https://bots.qq.com/app/getAppAccessToken")


settings = Settings()
