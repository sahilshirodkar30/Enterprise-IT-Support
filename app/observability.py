import logfire

from app.config import get_settings

_configured = False


def configure_observability() -> None:
    """Call once at application startup, not at import time."""
    global _configured
    if _configured:
        return

    s = get_settings()
    logfire.configure(
        api_key=s.LOGFIRE_API_KEY.get_secret_value(),
        service_name=s.SERVICE_NAME,
    )
    logfire.instrument_openai()
    _configured = True