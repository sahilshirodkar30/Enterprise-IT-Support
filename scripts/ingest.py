from app.config import get_settings
from app.observability import configure_observability
from app.rag.ingest import ingest_docs


if __name__ == "__main__":
    configure_observability()
    s = get_settings()
    report = ingest_docs(s.INGEST_PATH)
    print(report)