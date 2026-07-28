from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE_PATH = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH,
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    DATABASE_URL: str = "sqlite+aiosqlite:///./norman_shop.db"
    GEMINI_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    MESSENGER_VERIFY_TOKEN: str = "norman_secure_webhook_token_2026"
    MESSENGER_PAGE_ACCESS_TOKEN: str = ""
    JWT_SECRET_KEY: str = ""
    ENVIRONMENT: str = "development"
    PORT: int = 8000

    # Admin credentials for Phase 2 authentication
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD_HASH: str = ""

    # Meta Messenger webhook (Phase 4)
    META_APP_SECRET: str = ""

    # Phase 5 — AI auto-reply toggle
    STAFF_HANDOFF_ENABLED: bool = True


settings = Settings()
