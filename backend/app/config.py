import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Repository root (parent of backend/)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_UI_ASSETS = PROJECT_ROOT / "ui" / "assets"
_DEFAULT_UI_JS = PROJECT_ROOT / "ui" / "js"
UI_ASSETS_DIR = Path(os.getenv("UI_ASSETS_DIR", str(_DEFAULT_UI_ASSETS)))
UI_JS_DIR = Path(os.getenv("UI_JS_DIR", str(_DEFAULT_UI_JS)))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Orqestra"
    app_tagline: str = "AI Agent Orchestration Platform"
    api_version: str = "0.1.0"
    app_env: str = "development"
    debug: bool = True

    openapi_enabled: bool = True
    docs_url: str | None = "/docs"
    redoc_url: str | None = "/redoc"
    openapi_url: str | None = "/openapi.json"

    database_url: str = (
        "postgresql+psycopg2://yuno:yuno@localhost:5432/yuno"
    )
    session_secret_key: str = "change-me-in-production"
    session_max_age_seconds: int = 60 * 60 * 24 * 7  # 7 days

    admin_email: str = "admin@example.com"
    admin_password: str = "admin123"
    admin_full_name: str = "Platform Admin"

    app_base_url: str = "http://localhost:3000"
    password_reset_token_hours: int = 24

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host.strip() and self.smtp_from.strip())

    redis_url: str = "redis://localhost:6379/0"
    celery_task_always_eager: bool = False

    openai_api_key: str = ""
    runtime_mock_llm: bool = False
    runtime_mock_tools: bool = False

    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    telegram_use_polling: bool = False

    # --- Dev pipeline: GitHub integration ---
    github_token: str = ""
    github_owner: str = ""

    # --- Dev pipeline: DigitalOcean integration ---
    do_api_token: str = ""
    do_region: str = "blr1"
    do_size: str = "s-1vcpu-1gb"
    do_image: str = "ubuntu-22-04-x64"

    # --- Dev pipeline: droplet root password (temporary demo droplets only) ---
    deploy_root_password: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
