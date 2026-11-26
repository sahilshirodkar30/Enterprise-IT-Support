
from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent

COMMON_CONFIG = {
    "env_file": ROOT / ".env",
    "env_file_encoding": "utf-8",
    "extra": "ignore",
}


class Settings(BaseSettings):
    """Backend configuration for FastAPI."""

    model_config = SettingsConfigDict(**COMMON_CONFIG)

    DEV_AUTH_TOKEN: SecretStr | None = None
    DEV_USER_ID: str = "dev.user@novaretail.local"
    APP_ENV: str = "development"
    SERVICE_NAME: str = "enterprise-it-support"

    # Pinecone
    PINECONE_API_KEY: SecretStr
    PINECONE_INDEX_NAME: str
    PINECONE_NAMESPACE: str = "enterprise-it-support-namespace"
    PINECONE_CLOUD: str = "aws"
    PINECONE_REGION: str = "us-east-1"
    EMBEDDING_MODEL_NAME: str
    EMBEDDING_MODEL_DIMENSION: int = Field(gt=0)

    # Portkey
    PORTKEY_GATEWAY_URL: str
    PORTKEY_GATEWAY_API_KEY: SecretStr
    GROQ_SLUG: str
    GROQ_MODEL_NAME: str
    DEEPSEEK_SLUG: str
    DEEPSEEK_MODEL_NAME: str
    PORTKEY_CONFIG_SLUG: str

    # Observability
    LOGFIRE_API_KEY: SecretStr

    # Application
    INGEST_PATH: Path = ROOT / "DATA" / "sample_kb"

    # Cache
    CACHE_TTL_SECONDS: int = Field(default=7 * 24 * 3600, gt=0)
    CACHE_SIMILARITY: float = Field(default=0.95, ge=0.0, le=1.0)

    # Retrieval
    RETRIEVAL_CANDIDATES: int = Field(default=10, ge=1, le=100)
    RETRIEVAL_KEEP: int = Field(default=4, ge=1, le=20)
    RERANK_MIN_SCORE: float | None = None

    # Rate limiting
    RATE_LIMITER_PER_MIN: int = Field(default=5, ge=1)

    # Authentication
    GOOGLE_CLIENT_ID: str
    ADMIN_EMAILS: str = ""

    # Optional application settings if used by backend code
    API_URL: str = "http://api:8000"
    API_TOKEN: str = ""


class FrontendSettings(BaseSettings):
    """Streamlit configuration."""

    model_config = SettingsConfigDict(**COMMON_CONFIG)

    APP_ENV: str = "development"

    # Backend connection
    API_URL: str = "http://api:8000"
    API_TOKEN: str = ""

    # Google OAuth
    GOOGLE_CLIENT_ID: str
    GOOGLE_CLIENT_SECRET: SecretStr
    REDIRECT_URI: str

    DEV_AUTH_TOKEN: SecretStr | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


@lru_cache(maxsize=1)
def get_frontend_settings() -> FrontendSettings:
    return FrontendSettings()
