import os
import uuid

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")
API_TOKEN = os.getenv("API_TOKEN", "")  # replace with real login in production
REQUEST_TIMEOUT = 60
TITLE_CHARS = 40

SUGGESTIONS = [
    ("Reset my password", "How do I reset my password after an account lockout?"),
    ("VPN won't connect", "My VPN won't connect from home. What should I check?"),
    ("Set up MFA", "How do I set up multi-factor authentication on a new phone?"),
    ("Laptop lost or stolen", "What should I do if my company laptop is lost or stolen?"),
]

st.set_page_config(page_title="IT Support Assistant", page_icon="💬", layout="wide")

CSS = """
:root {
  --bg: #212121;
  --sidebar: #171717;
  --surface: #2f2f2f;
  --surface-hover: #3a3a3a;
  --border: #383838;
  --text: #ececec;
  --muted: #9a9a9a;
  --accent: #10a37f;
}

html, body, [data-testid="stAppViewContainer"], .stApp {
  background: var(--bg) !important;
  color: var(--text);
  font-family: "Söhne", "Segoe UI", system-ui, -apple-system, sans-serif;
}

/* Hide Streamlit chrome */
#MainMenu, footer, [data-testid="stHeader"], [data-testid="stDecoration"] {
  visibility: hidden;
  height: 0;
}

/* Sidebar */
[data-testid="stSidebar"] {
  background: var(--sidebar) !important;
  border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] .block-container { padding: 1rem 0.75rem; }
[data-testid="stSidebar"] .stButton > button {
  width: 100%;
  justify-content: flex-start;
  background: transparent;
  color: var(--text);
  border: none;
  border-radius: 10px;
  padding: 0.55rem 0.75rem;
  font-size: 0.9rem;
  font-weight: 400;
  text-align: left;
}
[data-testid="stSidebar"] .stButton > button:hover {
  background: var(--surface-hover);
  color: var(--text);
}
.sidebar-title {
  font-size: 0.75rem;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin: 1rem 0.5rem 0.4rem;
}
.new-chat > button {
  border: 1px solid var(--border) !important;
  background: var(--surface) !important;
}

/* Main column */
.block-container {
  max-width: 820px;
  padding-top: 2rem;
  padding-bottom: 7rem;
}

/* Welcome screen */
.welcome {
  text-align: center;
  margin: 12vh auto 2.5rem;
}
.welcome h1 {
  font-size: 2rem;
  font-weight: 600;
  margin-bottom: 0.4rem;
}
.welcome p { color: var(--muted); margin: 0; }

.suggestion-grid .stButton > button {
  width: 100%;
  height: 100%;
  min-height: 84px;
  background: var(--surface);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 0.9rem 1rem;
  text-align: left;
  white-space: normal;
  font-size: 0.9rem;
}
.suggestion-grid .stButton > button:hover {
  background: var(--surface-hover);
  border-color: #4a4a4a;
}
.suggestion-grid .stButton > button p {
  font-weight: 600;
  margin-bottom: 0.2rem;
}

/* Chat messages */
[data-testid="stChatMessage"] {
  background: transparent;
  padding: 1rem 0;
  gap: 0.9rem;
}
[data-testid="stChatMessage"] p,
[data-testid="stChatMessage"] li {
  font-size: 1rem;
  line-height: 1.7;
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
  flex-direction: row-reverse;
}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) > div:nth-child(2) {
  background: var(--surface);
  border-radius: 18px;
  padding: 0.6rem 1rem;
  max-width: 80%;
  margin-left: auto;
}
[data-testid="stChatMessage"] [data-testid="chatAvatarIcon-assistant"] {
  background: var(--accent);
}

/* Source chips */
.sources {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-top: 0.6rem;
}
.source-chip {
  font-size: 0.78rem;
  color: var(--muted);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 0.2rem 0.6rem;
  background: #262626;
}

/* Blocked and degraded notices */
.notice {
  font-size: 0.85rem;
  color: #f0b429;
  margin-top: 0.4rem;
}

/* Input bar */
[data-testid="stBottom"], [data-testid="stBottomBlockContainer"] {
  background: var(--bg) !important;
}
[data-testid="stChatInput"] {
  background: var(--surface) !important;
  border: 1px solid #4a4a4a !important;
  border-radius: 24px !important;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.25);
  max-width: 820px;
  margin: 0 auto;
}
[data-testid="stChatInput"]:focus-within {
  border-color: #6b6b6b !important;
}
[data-testid="stChatInput"] textarea {
  color: var(--text) !important;
  font-size: 1rem;
}
[data-testid="stChatInput"] button {
  background: var(--text) !important;
  color: var(--bg) !important;
  border-radius: 50% !important;
}
[data-testid="stChatInput"] button:disabled {
  background: #4a4a4a !important;
  color: var(--muted) !important;
}

/* Spinner text */
[data-testid="stSpinner"] { color: var(--muted); }

::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-thumb { background: #3a3a3a; border-radius: 8px; }
"""

st.markdown(f"<style>{CSS}</style>", unsafe_allow_html=True)


def new_chat_id() -> str:
    return uuid.uuid4().hex


def init_state() -> None:
    if "chats" not in st.session_state:
        cid = new_chat_id()
        st.session_state.chats = {cid: {"title": "New chat", "messages": []}}
        st.session_state.active = cid


def start_new_chat() -> None:
    cid = new_chat_id()
    st.session_state.chats[cid] = {"title": "New chat", "messages": []}
    st.session_state.active = cid


def ask_backend(question: str, thread_id: str) -> dict:
    """Call /ask. Returns a dict with answer, sources, blocked, degraded."""
    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    payload = {"question": question, "thread_id": thread_id}
    try:
        resp = requests.post(
            f"{API_URL}/ask", json=payload, headers=headers, timeout=REQUEST_TIMEOUT
        )
    except requests.RequestException:
        return {
            "answer": "I can't reach the support service right now. Please try again shortly.",
            "sources": [], "blocked": False, "degraded": True,
        }

    if resp.status_code == 401:
        return {
            "answer": "Your session has expired. Please sign in again.",
            "sources": [], "blocked": False, "degraded": True,
        }
    if resp.status_code == 422:
        return {
            "answer": "That message is too long or invalid. Please shorten it and try again.",
            "sources": [], "blocked": False, "degraded": False,
        }
    if resp.status_code != 200:
        return {
            "answer": "Something went wrong on our side. Please try again.",
            "sources": [], "blocked": False, "degraded": True,
        }
    return resp.json()


def render_sidebar() -> None:
    with st.sidebar:
        st.markdown("### 💬 IT Support")
        st.container(key="new-chat")
        if st.button("＋  New chat", key="new_chat_btn", use_container_width=True):
            start_new_chat()
            st.rerun()

        st.markdown('<div class="sidebar-title">Chats</div>', unsafe_allow_html=True)
        for cid, chat in reversed(list(st.session_state.chats.items())):
            label = chat["title"]
            if cid == st.session_state.active:
                label = f"› {label}"
            if st.button(label, key=f"chat_{cid}", use_container_width=True):
                st.session_state.active = cid
                st.rerun()


def render_sources(sources: list[str]) -> None:
    if not sources:
        return
    chips = "".join(f'<span class="source-chip">{s}</span>' for s in sources)
    st.markdown(f'<div class="sources">{chips}</div>', unsafe_allow_html=True)


def render_welcome() -> str | None:
    st.markdown(
        """
        <div class="welcome">
          <h1>How can I help with IT today?</h1>
          <p>Ask about VPN, passwords, MFA, software, email, or lost devices.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    picked = None
    cols = st.columns(2, gap="small")
    for i, (title, prompt) in enumerate(SUGGESTIONS):
        with cols[i % 2]:
            with st.container(key=f"sugg-{i}"):
                if st.button(f"**{title}**\n\n{prompt}", key=f"sugg_btn_{i}",
                             use_container_width=True):
                    picked = prompt
    return picked


def render_messages(messages: list[dict]) -> None:
    for msg in messages:
        avatar = "🧑‍💻" if msg["role"] == "user" else "🛠️"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])
            if msg.get("notice"):
                st.markdown(f'<div class="notice">{msg["notice"]}</div>',
                            unsafe_allow_html=True)
            render_sources(msg.get("sources", []))


def handle_turn(question: str) -> None:
    chat = st.session_state.chats[st.session_state.active]
    if chat["title"] == "New chat":
        chat["title"] = question[:TITLE_CHARS] + ("…" if len(question) > TITLE_CHARS else "")

    chat["messages"].append({"role": "user", "content": question})
    with st.chat_message("user", avatar="🧑‍💻"):
        st.markdown(question)

    with st.chat_message("assistant", avatar="🛠️"):
        with st.spinner("Searching IT documentation…"):
            result = ask_backend(question, st.session_state.active)

        st.markdown(result["answer"])
        notice = None
        if result.get("blocked"):
            notice = "This message was declined by the assistant's safety checks."
        elif result.get("degraded"):
            notice = "Service was limited for this answer."
        if notice:
            st.markdown(f'<div class="notice">{notice}</div>', unsafe_allow_html=True)
        render_sources(result.get("sources", []))

    chat["messages"].append({
        "role": "assistant",
        "content": result["answer"],
        "sources": result.get("sources", []),
        "notice": notice,
    })


def main() -> None:
    init_state()
    render_sidebar()

    chat = st.session_state.chats[st.session_state.active]
    prompt = None

    if not chat["messages"]:
        prompt = render_welcome()
    else:
        render_messages(chat["messages"])

    typed = st.chat_input("Message IT Support…")
    prompt = typed or prompt

    if prompt:
        handle_turn(prompt.strip())
        st.rerun()


main()