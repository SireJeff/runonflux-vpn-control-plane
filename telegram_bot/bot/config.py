import os
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class BotConfig:
    TELEGRAM_BOT_TOKEN: str = ""
    WORKER_API_URL: str = "http://localhost:8080/api/v1"
    INTERNAL_API_KEY: str = ""
    ADMIN_DASHBOARD_URL: str = "https://admin.operator7.example.invalid"
    ADMIN_USER_IDS: List[int] = field(default_factory=list)
    WEBHOOK_HOST: str = "0.0.0.0"
    WEBHOOK_PORT: int = 8443
    WEBHOOK_SECRET: str = ""
    ENVIRONMENT: str = "development"
    DEBUG: bool = False

    SUPPORTED_LANGUAGES = ["en", "fa"]
    RTL_LANGUAGES = ["fa"]
    DEFAULT_LANGUAGE = "en"

    API_TIMEOUT_READ: int = 10
    API_TIMEOUT_WRITE: int = 30
    API_MAX_RETRIES: int = 3
    API_RETRY_BACKOFF: float = 1.0

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.ADMIN_USER_IDS


_config: Optional[BotConfig] = None


def init_config() -> BotConfig:
    global _config
    _config = BotConfig(
        TELEGRAM_BOT_TOKEN=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        WORKER_API_URL=os.getenv("WORKER_API_URL", "http://localhost:8080/api/v1"),
        INTERNAL_API_KEY=os.getenv("INTERNAL_API_KEY", ""),
        ADMIN_DASHBOARD_URL=os.getenv("ADMIN_DASHBOARD_URL", "https://admin.operator7.example.invalid"),
        ADMIN_USER_IDS=[
            int(x.strip())
            for x in os.getenv("ADMIN_USER_IDS", "").split(",")
            if x.strip().isdigit()
        ],
        WEBHOOK_HOST=os.getenv("WEBHOOK_HOST", "0.0.0.0"),
        WEBHOOK_PORT=int(os.getenv("WEBHOOK_PORT", "8443")),
        WEBHOOK_SECRET=os.getenv("WEBHOOK_SECRET", ""),
        ENVIRONMENT=os.getenv("ENVIRONMENT", "development"),
        DEBUG=os.getenv("DEBUG", "false").lower() in ("true", "1", "yes"),
    )
    if not _config.TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is required")
    return _config


def get_config() -> BotConfig:
    if _config is None:
        raise RuntimeError("Config not initialized. Call init_config() first.")
    return _config
