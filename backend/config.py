from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application configuration from environment variables."""

    # Database
    database_url: str = "postgresql://user:password@localhost:5432/profit_capture"

    # API
    api_title: str = "ShoppingAgent API"
    api_version: str = "0.1.0"
    debug: bool = True

    # Anthropic (for future conversational agent)
    anthropic_api_key: str = ""

    class Config:
        env_file = ".env"
        case_sensitive = False


@lru_cache()
def get_settings() -> Settings:
    return Settings()
