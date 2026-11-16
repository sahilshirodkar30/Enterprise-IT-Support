from functools import lru_cache

from langchain_openai import ChatOpenAI
from portkey_ai import createHeaders

from app.config import get_settings


def _gateway_config(s) -> dict:
    # Verify the target format against your Portkey version's fallback docs.
    return {
        "strategy": {"mode": "fallback"},
        "retry": {"attempts": 2, "on_status_codes": [429, 503]},
        "targets": [
            {"override_params": {"model": f"@{s.GROQ_SLUG}/{s.GROQ_MODEL_NAME}"}},
            {"override_params": {"model": f"@{s.DEEPSEEK_SLUG}/{s.DEEPSEEK_MODEL_NAME}"}},
        ],
    }


@lru_cache(maxsize=None)
def get_llm(feature: str = "rag", max_tokens: int | None = None,
            temperature: float = 0.0) -> ChatOpenAI:
    """Synchronous factory. Cached per (feature, max_tokens, temperature)."""
    s = get_settings()
    key = s.PORTKEY_GATEWAY_API_KEY.get_secret_value()

    return ChatOpenAI(
        api_key=key,
        base_url=s.PORTKEY_GATEWAY_URL,
        model=f"@{s.GROQ_SLUG}/{s.GROQ_MODEL_NAME}",
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=30,
        max_retries=0,  # the gateway handles retries and failover
        default_headers=createHeaders(
            api_key=key,
            config=_gateway_config(s),
            metadata={
                "feature": feature,
                "_user": "it-support-service",
                "environment": s.APP_ENV,
            },
        ),
    )