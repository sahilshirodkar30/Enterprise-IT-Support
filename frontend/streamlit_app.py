
import os
import uuid
import html
from dotenv import load_dotenv
import requests
import streamlit as st

from pathlib import Path
from dotenv import load_dotenv
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load project .env
load_dotenv(PROJECT_ROOT / ".env")
# --------------------------------------------------
# Configuration
# --------------------------------------------------

API_URL = os.getenv("API_URL", "http://127.0.0.1:8000").rstrip("/")
API_TOKEN = os.getenv("API_TOKEN", "")
REQUEST_TIMEOUT = 90
TITLE_CHARS = 40

SUGGESTIONS = [
    ("🔑 Reset my password", "How do I reset my password after an account lockout?"),
    ("🌐 VPN won't connect", "My VPN won't connect from home. What should I check?"),
    ("🔐 Set up MFA", "How do I set up multi-factor authentication on a new phone?"),
    ("💻 Lost laptop", "What should I do if my company laptop is lost or stolen?"),
]


# --------------------------------------------------
# Page configuration
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
    max-width: 850px;
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

.stButton button {
    border-radius: 12px;
}

.suggestion button {
    width: 100%;
    min-height: 85px;
    background: var(--surface);
    color: var(--text);
    border: 1px solid var(--border);
    text-align: left;
    white-space: normal;
}

.suggestion button:hover {
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
    margin: 12vh auto 2rem;
}

.welcome h1 {
    font-size: 2rem;
    font-weight: 600;
}

.welcome p {
    color: var(--muted);
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
</style>
"""

st.markdown(CSS, unsafe_allow_html=True)


# --------------------------------------------------
# Session state
# --------------------------------------------------

def new_chat_id() -> str:
    return uuid.uuid4().hex


def init_state():
    if "chats" not in st.session_state:
        chat_id = new_chat_id()

        st.session_state.chats = {
            chat_id: {
                "title": "New chat",
                "messages": [],
            }
        }

        st.session_state.active = chat_id


def start_new_chat():
    chat_id = new_chat_id()

    st.session_state.chats[chat_id] = {
        "title": "New chat",
        "messages": [],
    }

    st.session_state.active = chat_id


# --------------------------------------------------
# FastAPI communication
# --------------------------------------------------

def ask_backend(question: str, thread_id: str) -> dict:
    """
    Sends the question to FastAPI /ask.

    Expected response:
    {
        "thread_id": "...",
        "answer": "...",
        "blocked": false,
        "degraded": false,
        "sources": []
    }
    """
    print("API_TOKEN",API_TOKEN)
    if not API_TOKEN:
        return {
            "answer": "API authentication token is missing. Configure API_TOKEN in your Streamlit environment.",
            "sources": [],
            "blocked": False,
            "degraded": True,
        }

    headers = {
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "question": question,
        "thread_id": thread_id,
    }

    try:
        response = requests.post(
            f"{API_URL}/ask",
            json=payload,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )

    except requests.Timeout:
        return {
            "answer": "The IT support service took too long to respond. Please try again.",
            "sources": [],
            "blocked": False,
            "degraded": True,
        }

    except requests.ConnectionError:
        return {
            "answer": "Cannot connect to the IT support API. Please check whether FastAPI is running.",
            "sources": [],
            "blocked": False,
            "degraded": True,
        }

    except requests.RequestException:
        return {
            "answer": "Unable to communicate with the IT support service.",
            "sources": [],
            "blocked": False,
            "degraded": True,
        }

    if response.status_code == 401:
        return {
            "answer": "Authentication failed. Check whether API_TOKEN matches the FastAPI DEV_AUTH_TOKEN.",
            "sources": [],
            "blocked": False,
            "degraded": True,
        }

    if response.status_code == 422:
        return {
            "answer": "Invalid request. Please check your message length and try again.",
            "sources": [],
            "blocked": False,
            "degraded": False,
        }

    if response.status_code != 200:
        return {
            "answer": f"The IT support API returned an error ({response.status_code}). Please try again later.",
            "sources": [],
            "blocked": False,
            "degraded": True,
        }

    try:
        data = response.json()

        return {
            "answer": data["answer"],
            "sources": data.get("sources", []),
            "blocked": data.get("blocked", False),
            "degraded": data.get("degraded", False),
        }

    except (ValueError, KeyError, TypeError):
        return {
            "answer": "The IT support API returned an invalid response.",
            "sources": [],
            "blocked": False,
            "degraded": True,
        }


# --------------------------------------------------
# Sidebar
# --------------------------------------------------

def render_sidebar():

    with st.sidebar:

        st.markdown("## 💬 NovaRetail IT")

        if st.button("＋ New chat", use_container_width=True):
            start_new_chat()
            st.rerun()

        st.markdown("---")
        st.caption("YOUR CONVERSATIONS")

        for chat_id, chat in reversed(
            list(st.session_state.chats.items())
        ):

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
        st.caption("Enterprise IT Support Assistant")


# --------------------------------------------------
# Sources
# --------------------------------------------------

def render_sources(sources: list[str]):

    if not sources:
        return

    chips = "".join(
        f'<span class="source-chip">{html.escape(str(source))}</span>'
        for source in sources
    )

    st.markdown(
        f'<div class="sources">{chips}</div>',
        unsafe_allow_html=True,
    )


# --------------------------------------------------
# Welcome screen
# --------------------------------------------------

def render_welcome():

    st.markdown(
        """
        <div class="welcome">
            <h1>How can I help with IT today?</h1>
            <p>
                Ask me about VPN, passwords, MFA,
                software installation, email, or lost devices.
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
# Render previous messages
# --------------------------------------------------

def render_messages(messages: list[dict]):

    for message in messages:

        role = message["role"]

        avatar = "🧑‍💻" if role == "user" else "🛠️"

        with st.chat_message(role, avatar=avatar):

            st.markdown(message["content"])

            if message.get("notice"):
                st.markdown(
                    f'<div class="notice">{html.escape(message["notice"])}</div>',
                    unsafe_allow_html=True,
                )

            render_sources(message.get("sources", []))


# --------------------------------------------------
# Handle user question
# --------------------------------------------------

def handle_turn(question: str):

    chat_id = st.session_state.active
    chat = st.session_state.chats[chat_id]

    # Generate chat title from the first question.
    if chat["title"] == "New chat":

        chat["title"] = question[:TITLE_CHARS]

        if len(question) > TITLE_CHARS:
            chat["title"] += "…"

    # Save user message.
    chat["messages"].append({
        "role": "user",
        "content": question,
    })

    with st.chat_message("user", avatar="🧑‍💻"):
        st.markdown(question)

    # Call FastAPI.
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
                f'<div class="notice">{html.escape(notice)}</div>',
                unsafe_allow_html=True,
            )

        render_sources(result["sources"])

    # Save assistant response.
    chat["messages"].append({
        "role": "assistant",
        "content": result["answer"],
        "sources": result["sources"],
        "notice": notice,
    })


# --------------------------------------------------
# Main application
# --------------------------------------------------

def main():

    init_state()

    render_sidebar()

    active_chat = st.session_state.chats[
        st.session_state.active
    ]

    selected_prompt = None

    if not active_chat["messages"]:
        selected_prompt = render_welcome()

    else:
        render_messages(active_chat["messages"])

    typed_prompt = st.chat_input(
        "Message NovaRetail IT Support..."
    )

    prompt = typed_prompt or selected_prompt

    if prompt:

        prompt = prompt.strip()

        if prompt:
            handle_turn(prompt)
            st.rerun()


main()
