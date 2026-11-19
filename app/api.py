from contextlib import asynccontextmanager
from uuid import uuid4
import hmac
from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field
from app.config import get_settings
from app.agents.graph import handle_question
from app.guardrails.input_guard import MAX_QUESTION_CHARS
from app.observability import configure_observability
from services.pinecone_store import ensure_index

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
THREAD_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"

bearer = HTTPBearer(auto_error=False)
@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    if s.APP_ENV != "development" and s.DEV_AUTH_TOKEN is not None:
        raise RuntimeError("DEV_AUTH_TOKEN must not be set outside development")
    configure_observability(app)
    ensure_index()
    yield

app = FastAPI(title="Enterprise IT support", version="1.0.0", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    # Omit to start a new conversation. Send the returned thread_id to continue it.
    thread_id: str | None = Field(default=None, pattern=THREAD_ID_PATTERN)


class AskResponse(BaseModel):
    thread_id: str
    answer: str
    blocked: bool
    degraded: bool
    sources: list[str]


def verify_token(token: str) -> dict:
    s = get_settings()

    if s.APP_ENV == "development" and s.DEV_AUTH_TOKEN is not None:
        expected = s.DEV_AUTH_TOKEN.get_secret_value()
        if expected and hmac.compare_digest(token, expected):
            return {"sub": s.DEV_USER_ID}

    # Production: replace with real JWT validation against your identity provider.
    raise ValueError("token rejected")


def get_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> str:
    """Resolve the caller from a verified bearer token. Never trust a raw identity header."""
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    try:
        claims = verify_token(credentials.credentials)
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")

    user_id = str(claims.get("sub", "")).strip().lower()
    if not user_id:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token has no subject")
    return user_id


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

#user_id: str = Depends(get_user_id)
@app.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, user_id: str = Depends(get_user_id)) -> AskResponse:
    thread_id = body.thread_id or uuid4().hex
    result = handle_question( user_id,body.question, thread_id)
    return AskResponse(
        thread_id=thread_id,
        answer=result["answer"],
        blocked=result["blocked"],
        degraded=result.get("degraded", False),
        sources=result.get("sources", []),
    )