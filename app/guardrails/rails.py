from functools import lru_cache
from pathlib import Path
import logfire
from nemoguardrails import LLMRails,RailsConfig
from app.gateway.client import get_langchain_llm

CONFIG_DIR = Path(__file__).resolve().parent / "config"

@lru_cache(maxsize=1)
def get_rails() -> LLMRails:

    try:
        config = RailsConfig.from_path(str(CONFIG_DIR))
        llm = get_langchain_llm(feature="guardrails")
        rails = LLMRails(config=config,llm=llm,verbose=False)
        logfire.info("Nemo Guardrails initialized")
        return rails
    except Exception as e:
        logfire.error("Nemo Guardrails initialization failed",error_type=type(e).__name__)
        raise RuntimeError("Unable to initialize nemo guardrail") from e