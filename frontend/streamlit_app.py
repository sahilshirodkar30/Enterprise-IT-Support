import html
import os
import secrets
import sys
import urllib.parse
import uuid
from pathlib import Path

# --------------------------------------------------
# Make the project root importable
# --------------------------------------------------
# This file is located at: Enterprise-IT-Support/frontend/streamlit_app.py
# Its parent.parent is the Enterprise-IT-Support project root.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests
import streamlit as st
from dotenv import load_dotenv

from app.config import get_frontend_settings


# --------------------------------------------------
# Configuration
# --------------------------------------------------

load_dotenv(PROJECT_ROOT / ".env")

settings = get_frontend_settings()

API_URL = settings.API_URL.rstrip("/")
API_TOKEN = settings.API_TOKEN
CLIENT_ID = settings.GOOGLE_CLIENT_ID
CLIENT_SECRET = settings.GOOGLE_CLIENT_SECRET.get_secret_value()
REDIRECT_URI = settings.REDIRECT_URI
REQUEST_TIMEOUT = 90
TITLE_CHARS = 40

SUGGESTIONS = [
    (
        "🔑 Reset my password",
        "How do I reset my password after an account lockout?",
    ),
    (
        "🌐 VPN won't connect",
        "My VPN won't connect from home. What should I check?",
    ),
    (
        "🔐 Set up MFA",
        "How do I set up multi-factor authentication on a new phone?",
    ),
    (
        "💻 Lost laptop",
        "What should I do if my company laptop is lost or stolen?",
    ),
]


# --------------------------------------------------
# Streamlit page configuration and styling
# --------------------------------------------------

st.set_page_config(
    page_title="NovaRetail IT Support",
    page_icon="💬",
    layout="wide",
)

CSS = """
<style>
:root {
    --bg: #212121;
    --sidebar: #171717;
    --surface: #2f2f2f;
    --hover: #3a3a3a;
    --border: #383838;
    --text: #ececec;
    --muted: #9a9a9a;
    --accent: #10a37f;
}

html, body, .stApp,
[data-testid="stAppViewContainer"] {
    background: var(--bg) !important;
    color: var(--text);
}

.block-container {
    max-width: 1000px;
    padding-top: 2rem;
    padding-bottom: 7rem;
}

[data-testid="stSidebar"] {
    background: var(--sidebar) !important;
    border-right: 1px solid var(--border);
}

[data-testid="stSidebar"] .stButton button {
    background: transparent;
    color: var(--text);
    border: none;
    text-align: left;
    border-radius: 10px;
}

[data-testid="stSidebar"] .stButton button:hover {
    background: var(--hover);
}

.stButton button, [data-testid="stLinkButton"] a {
    border-radius: 12px;
}

[data-testid="stLinkButton"] a {
    background: var(--accent);
    border: 1px solid var(--accent);
    color: white;
}

[data-testid="stLinkButton"] a:hover {
    background: #0d8f6f;
    border-color: #0d8f6f;
    color: white;
}

[data-testid="stVerticalBlock"] .st-key-suggestion_0 button,
[data-testid="stVerticalBlock"] .st-key-suggestion_1 button,
[data-testid="stVerticalBlock"] .st-key-suggestion_2 button,
[data-testid="stVerticalBlock"] .st-key-suggestion_3 button {
    width: 100%;
}

.st-key-suggestion_0 button,
.st-key-suggestion_1 button,
.st-key-suggestion_2 button,
.st-key-suggestion_3 button {
    min-height: 90px;
    background: var(--surface);
    color: var(--text);
    border: 1px solid var(--border);
    text-align: left;
    white-space: normal;
}

.st-key-suggestion_0 button:hover,
.st-key-suggestion_1 button:hover,
.st-key-suggestion_2 button:hover,
.st-key-suggestion_3 button:hover {
    background: var(--hover);
    border-color: #555;
}

[data-testid="stChatMessage"] {
    background: transparent;
    padding: 1rem 0;
}

[data-testid="stChatInput"] {
    background: var(--surface) !important;
    border: 1px solid #4a4a4a !important;
    border-radius: 24px !important;
}

[data-testid="stChatInput"] textarea {
    color: var(--text) !important;
}

.welcome {
    text-align: center;
    margin: 10vh auto 2rem;
    max-width: 760px;
}

.welcome h1 {
    font-size: 2rem;
    font-weight: 600;
    color: var(--text);
}

.welcome p {
    color: var(--muted);
    line-height: 1.6;
}

.sources {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 10px;
}

.source-chip {
    font-size: 0.78rem;
    color: var(--muted);
    border: 1px solid var(--border);
    border-radius: 20px;
    padding: 4px 10px;
    background: #262626;
}

.notice {
    color: #f0b429;
    font-size: 0.85rem;
    margin-top: 8px;
}

.login-container {
    max-width: 560px;
    margin: 12vh auto 0;
    padding: 2rem;
    border: 1px solid var(--border);
    border-radius: 18px;
    background: var(--surface);
    text-align: center;
}

.profile-label {
    color: var(--muted);
    font-size: 0.75rem;
    letter-spacing: 0.06em;
}
</style>
"""

st.markdown(CSS, unsafe_allow_html=True)


# --------------------------------------------------
# Google OAuth helpers
# --------------------------------------------------

@st.cache_resource
def pending_states() -> set:
    """Shared temporary state store used to validate OAuth callbacks."""
    return set()


def login_url() -> str:
    """Create the Google OAuth authorization URL."""
    state = secrets.token_urlsafe(24)
    pending_states().add(state)

    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "prompt": "select_account",
    }

    return (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        + urllib.parse.urlencode(params)
    )


def handle_callback() -> None:
    """Exchange Google's authorization code for an ID token."""
    params = dict(st.query_params)

    if "error" in params:
        oauth_error = params.get("error", "Unknown OAuth error")
        st.query_params.clear()
        st.error(f"Google sign-in failed: {oauth_error}")
        st.stop()

    if "code" not in params:
        return

    code = params.get("code", "")
    state = params.get("state", "")
    st.query_params.clear()

    if not state or state not in pending_states():
        st.error("Login failed: invalid or expired state. Please sign in again.")
        st.stop()

    pending_states().discard(state)

    try:
        response = requests.post(
            "https://oauth2.googleapis.com/token",
            data = {
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET.get_secret_value(),
                "redirect_uri": REDIRECT_URI,
                "grant_type": "authorization_code",
            },
            timeout=15,
        )
        response.raise_for_status()

        token_data = response.json()
        google_id_token = token_data.get("id_token")

        if not google_id_token:
            st.error("Google did not return an ID token.")
            st.stop()

        st.session_state["id_token"] = google_id_token

    except requests.RequestException:
        st.error("Google token exchange failed. Please try signing in again.")
        st.stop()

    except ValueError:
        st.error("Google returned an invalid token response.")
        st.stop()


def api(method: str, path: str, **kwargs) -> requests.Response:
    """Call FastAPI using the signed-in user's Google ID token."""
    id_token = st.session_state.get("id_token")
    if not id_token:
        raise RuntimeError("User is not authenticated.")

    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {id_token}"

    return requests.request(
        method,
        f"{API_URL}{path}",
        headers=headers,
        timeout=REQUEST_TIMEOUT,
        **kwargs,
    )


def error_detail(response: requests.Response) -> str:
    try:
        body = response.json()
        if isinstance(body, dict):
            return str(body.get("detail", body))
        return str(body)
    except ValueError:
        return response.text or f"HTTP {response.status_code}"


def sign_out() -> None:
    """Clear the local Streamlit session and return to the login screen."""
    st.session_state.clear()
    st.rerun()


# Process an OAuth callback before checking the login state.
handle_callback()


# --------------------------------------------------
# Authentication and current user
# --------------------------------------------------

if not CLIENT_ID or not CLIENT_SECRET or not REDIRECT_URI:
    st.error(
        "Google OAuth configuration is incomplete. Check "
        "GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET and REDIRECT_URI."
    )
    st.stop()

if "id_token" not in st.session_state:

    st.markdown(
        """
        <div class="login-container">
            <h1>NovaRetail IT Support</h1>
            <p>
                Sign in with your company Google account to access
                the Enterprise IT Support Assistant.
            </p>
            <br>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <a href="{html.escape(login_url(), quote=True)}"
           target="_self"
           style="
               display: inline-block;
               background: #10a37f;
               color: white;
               padding: 12px 25px;
               border-radius: 10px;
               text-decoration: none;
               font-weight: 600;
           ">
            Sign in with Google
        </a>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.stop()


if "me" not in st.session_state:
    try:
        me_response = api("GET", "/me")

        if not me_response.ok:
            st.error(
                f"Authentication failed ({me_response.status_code}): "
                f"{error_detail(me_response)}"
            )
            st.info("Check the FastAPI logs and Google token validation.")

            if st.button("Back to sign in"):
                sign_out()
            st.stop()

        user_data = me_response.json()
        if not isinstance(user_data, dict) or not user_data.get("email"):
            st.error("The /me endpoint returned invalid user information.")
            sign_out()

        st.session_state["me"] = user_data

    except requests.RequestException as exc:
        st.error(f"Unable to connect to the authentication API: {exc}")
        st.stop()


me = st.session_state["me"]
user_email = me["email"]
user_role = str(me.get("role", "user")).lower()
is_admin = user_role == "admin"


# --------------------------------------------------
# Chat session state
# --------------------------------------------------

def new_chat_id() -> str:
    return uuid.uuid4().hex


def init_state() -> None:
    if "chats" not in st.session_state:
        chat_id = new_chat_id()
        st.session_state.chats = {
            chat_id: {
                "title": "New chat",
                "messages": [],
            }
        }
        st.session_state.active = chat_id

    # Recover safely if the active chat was removed or is invalid.
    if st.session_state.get("active") not in st.session_state.chats:
        st.session_state.active = next(iter(st.session_state.chats))


def start_new_chat() -> None:
    chat_id = new_chat_id()
    st.session_state.chats[chat_id] = {
        "title": "New chat",
        "messages": [],
    }
    st.session_state.active = chat_id


# --------------------------------------------------
# FastAPI communication for the RAG assistant
# --------------------------------------------------

def ask_backend(question: str, thread_id: str):
    google_id_token = st.session_state.get("id_token")

    if not google_id_token:
        raise RuntimeError("Google authentication token is missing. Please sign in again.")

    headers = {
        "Authorization": f"Bearer {google_id_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "question": question,
        "thread_id": thread_id,
    }

    response = requests.post(
        f"{API_URL}/ask",
        headers=headers,
        json=payload,
        timeout=REQUEST_TIMEOUT,
    )

    response.raise_for_status()
    return response.json()
# --------------------------------------------------
# Sidebar
# --------------------------------------------------

def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("## 💬 NovaRetail IT")

        with st.container(border=True):
            st.markdown(
                '<div class="profile-label">SIGNED IN AS</div>',
                unsafe_allow_html=True,
            )
            st.markdown(f"**{html.escape(user_email)}**")

            if is_admin:
                st.success("Administrator")
            else:
                st.info("Standard User")

        if st.button("＋ New chat", use_container_width=True):
            start_new_chat()
            st.rerun()

        st.markdown("---")
        st.caption("YOUR CONVERSATIONS")

        for chat_id, chat in reversed(list(st.session_state.chats.items())):
            label = chat["title"]
            if chat_id == st.session_state.active:
                label = f"› {label}"

            if st.button(
                label,
                key=f"chat_{chat_id}",
                use_container_width=True,
            ):
                st.session_state.active = chat_id
                st.rerun()

        st.markdown("---")
        st.caption("ENTERPRISE IT SUPPORT ASSISTANT")

        if st.button("Sign out", use_container_width=True):
            sign_out()


# --------------------------------------------------
# Render source references
# --------------------------------------------------

def render_sources(sources: list) -> None:
    if not sources:
        return

    source_labels = []
    for source in sources:
        if isinstance(source, dict):
            # Support either a source filename or a structured source object.
            label = (
                source.get("file")
                or source.get("filename")
                or source.get("source")
                or str(source)
            )
            if source.get("chunk") is not None:
                label = f"{label} (chunk {source['chunk']})"
        else:
            label = str(source)

        source_labels.append(str(label))

    chips = "".join(
        f'<span class="source-chip">{html.escape(label)}</span>'
        for label in source_labels
    )

    st.markdown(
        f'<div class="sources">{chips}</div>',
        unsafe_allow_html=True,
    )


# --------------------------------------------------
# Welcome screen and suggested prompts
# --------------------------------------------------

def render_welcome():
    st.markdown(
        """
        <div class="welcome">
            <h1>How can I help with IT today?</h1>
            <p>
                Ask about VPN, passwords, MFA, software installation,
                email, device security, or company IT policies.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    selected_prompt = None
    columns = st.columns(2, gap="medium")

    for index, (title, prompt) in enumerate(SUGGESTIONS):
        with columns[index % 2]:
            with st.container(key=f"suggestion_{index}"):
                if st.button(
                    f"**{title}**\n\n{prompt}",
                    key=f"suggestion_button_{index}",
                    use_container_width=True,
                ):
                    selected_prompt = prompt

    return selected_prompt


# --------------------------------------------------
# Render previous chat messages
# --------------------------------------------------

def render_messages(messages: list[dict]) -> None:
    for message in messages:
        role = message["role"]
        avatar = "🧑‍💻" if role == "user" else "🛠️"

        with st.chat_message(role, avatar=avatar):
            st.markdown(message["content"])

            if message.get("notice"):
                st.markdown(
                    '<div class="notice">'
                    f"{html.escape(message['notice'])}"
                    "</div>",
                    unsafe_allow_html=True,
                )

            render_sources(message.get("sources", []))


# --------------------------------------------------
# Process a user question
# --------------------------------------------------

def handle_turn(question: str) -> None:
    chat_id = st.session_state.active
    chat = st.session_state.chats[chat_id]

    # Generate the conversation title from its first question.
    if chat["title"] == "New chat":
        chat["title"] = question[:TITLE_CHARS]
        if len(question) > TITLE_CHARS:
            chat["title"] += "…"

    # Save and display the user message.
    chat["messages"].append({
        "role": "user",
        "content": question,
    })

    with st.chat_message("user", avatar="🧑‍💻"):
        st.markdown(question)

    # Call the Enterprise IT Support RAG backend.
    with st.chat_message("assistant", avatar="🛠️"):
        with st.spinner("Searching IT documentation..."):
            result = ask_backend(
                question=question,
                thread_id=chat_id,
            )

        st.markdown(result["answer"])

        notice = None
        if result["blocked"]:
            notice = "This response was blocked by the assistant's safety checks."
        elif result["degraded"]:
            notice = "The service is currently operating with limited functionality."

        if notice:
            st.markdown(
                '<div class="notice">'
                f"{html.escape(notice)}"
                "</div>",
                unsafe_allow_html=True,
            )

        render_sources(result["sources"])

    # Save the assistant response for subsequent Streamlit reruns.
    chat["messages"].append({
        "role": "assistant",
        "content": result["answer"],
        "sources": result["sources"],
        "notice": notice,
    })


# --------------------------------------------------
# Main application
# --------------------------------------------------

def main() -> None:
    init_state()
    render_sidebar()

    active_chat = st.session_state.chats[st.session_state.active]
    selected_prompt = None

    if not active_chat["messages"]:
        selected_prompt = render_welcome()
    else:
        render_messages(active_chat["messages"])

    typed_prompt = st.chat_input(
        "Ask NovaRetail IT Support anything..."
    )

    prompt = typed_prompt or selected_prompt

    if prompt:
        prompt = prompt.strip()
        if prompt:
            handle_turn(prompt)
            st.rerun()


if __name__ == "__main__":
    main()
