from fastapi import Depends,FastAPI,Header,HTTPException,status
from pydantic import BaseModel,Field
import logfire
from app.agents.graph import handle_question
from app.observability import configure_observability
from uuid import uuid4
from services.pinecone_store import ensure_index


THREAD_ID_PATTERN = r"^[A-Za-z0-9_-]{1,64}$"
MAX_MESSAGE_CHARS = 4000  # keep equal to input_guard.MAX_INPUT_CHARS


app = FastAPI(title="Enterprise IT support",version="1.0.0")

@app.on_event("startup")
def _startup() -> None:
    configure_observability()
    ensure_index()

class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    thread_id: str = Field(
        default_factory=lambda: uuid4().hex,
        pattern=THREAD_ID_PATTERN,
    )


class AskResponse(BaseModel):
    thread_id: str
    answer: str
    blocked: bool
    degraded: bool
    sources: list[str]

def get_user_id(x_user_id: str = Header(..., description="Caller identity, e.g. the user's email")) -> str:
    """Identify the caller. Replace this with real token verification (see notes below)."""
    if not x_user_id.strip():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing user id")
    return x_user_id.strip().lower()

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}

def get_thread_id(x_thread_id: str = Header(..., description="Conversation id, one per chat")) -> str:
    return x_thread_id.strip()

@logfire.log_function("ask questions")
@app.post("/ask", response_model=AskResponse)
def ask(body: AskRequest, user_id: str = Depends(get_user_id),
        thread_id: str = Depends(get_thread_id)) -> AskResponse:
    result = handle_question(user_id, body.question, thread_id)
    return AskResponse(**result)