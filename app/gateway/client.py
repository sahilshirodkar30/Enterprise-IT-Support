from functools import lru_cache

from langchain_openai import ChatOpenAI
from portkey_ai import createHeaders

from app.config import get_settings


@lru_cache(maxsize=None)
def get_llm(feature: str = "rag", max_tokens: int | None = None,
            temperature: float = 0.0) -> ChatOpenAI:
    """Synchronous factory. Cached per (feature, max_tokens, temperature)."""
    s = get_settings()
    key = s.PORTKEY_GATEWAY_API_KEY.get_secret_value()

    return ChatOpenAI(
    api_key=key,
    base_url=s.PORTKEY_GATEWAY_URL,
    model=s.GROQ_MODEL_NAME,  # plain name; the saved config's targets route the request
    temperature=temperature,
    max_tokens=max_tokens,
    timeout=30,
    max_retries=0,
    default_headers=createHeaders(
        api_key=key,
        config=s.PORTKEY_CONFIG_SLUG,
        metadata={
            "feature": feature,
            "_user": "it-support-service",
            "environment": s.APP_ENV,
        },
    ),
    )