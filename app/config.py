from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    BOT_TOKEN: str = ""
    OPENAI_API_KEY: str = ""

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/telegram_chinese_bot"
    REDIS_URL: str = "redis://localhost:6379/0"

    ADMIN_IDS: str = "7965751363"
    PAYMENT_DETAILS: str = ""
    BOT_USERNAME: str = ""
    MINI_APP_BASE_URL: str = "https://telegram-chinese-bot-production.up.railway.app/study.html"

    DEFAULT_LANGUAGE: str = "tj"
    LOG_LEVEL: str = "INFO"

    AIRTABLE_API_KEY: str = ""
    AIRTABLE_BASE_ID: str = ""
    AIRTABLE_USERS_TABLE: str = "Users"
    AIRTABLE_PAYMENTS_TABLE: str = "Payments"
    AIRTABLE_REFERRALS_TABLE: str = "Referrals"
    AIRTABLE_CHAT_SUMMARY_TABLE: str = "ChatSummary"
    AIRTABLE_CHAT_ARCHIVE_TABLE: str = "ChatArchive"    

    @property
    def admin_id_list(self) -> List[int]:
        return [int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip()]


settings = Settings()
COURSE_MODE_ENABLED = True
