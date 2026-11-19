import logfire

from app.config import get_settings

_configured = False


def configure_observability(app=None) -> None:
    """Call once at application startup, not at import time."""
    global _configured
    if _configured:
        return

    s = get_settings()
    logfire.configure(
        api_key=s.LOGFIRE_API_KEY.get_secret_value(),
        service_name=s.SERVICE_NAME,
        # Confirm this argument exists in your logfire version; drop it if not.
        environment=s.APP_ENV,
    )

    # Prompts and completions include user questions and document excerpts.
    # Check your version's docs for a flag to disable content capture here.
    logfire.instrument_openai()

    if app is not None:
        logfire.instrument_fastapi(app)

    _configured = True