"""Version 1 - Interactive AI Escape Room (prompt-only Game Master).

Run:  streamlit run v1/app.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

from common.config import get_api_key  # noqa: E402
from common.llm import GeminiClient, LLMError  # noqa: E402
from v1.prompt import ESCAPE_MARKER, INTRO, SYSTEM_PROMPT  # noqa: E402

st.set_page_config(page_title="AI Escape Room - v1", page_icon="🗝️")


def reset_game():
    st.session_state.messages = [{"role": "assistant", "content": INTRO}]
    st.session_state.escaped = False


@st.cache_resource
def get_client():
    return GeminiClient()


if "messages" not in st.session_state:
    reset_game()

st.title("🗝️ The Locked Library - v1")
st.caption("Version 1: the LLM alone is the Game Master (no game state outside the conversation).")

with st.sidebar:
    st.header("How to play")
    st.markdown(
        "- Describe your actions in plain English.\n"
        "- Examine objects, pick things up, use items, try codes.\n"
        "- The game remembers the conversation, nothing else."
    )
    if st.button("🔄 Restart game", use_container_width=True):
        reset_game()
        st.rerun()

if not get_api_key():
    st.error("No API key found. Copy `.env.example` to `.env` and add your GEMINI_API_KEY.")
    st.stop()

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if st.session_state.escaped:
    st.success("🎉 You escaped! Press *Restart game* to play again.")
    st.stop()

prompt = st.chat_input("What do you do?")
if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # The model sees the whole conversation every turn - that is its only "memory".
    history = [{"role": "user", "content": "(The game begins.)"}] + st.session_state.messages
    with st.chat_message("assistant"):
        try:
            with st.spinner("The Game Master is thinking..."):
                reply = get_client().generate(SYSTEM_PROMPT, history, temperature=0.8)
        except LLMError as exc:
            reply = f"⚠️ The Game Master is unavailable: {exc}"
        escaped = ESCAPE_MARKER in reply
        reply = reply.replace(ESCAPE_MARKER, "").strip()
        st.markdown(reply)

    st.session_state.messages.append({"role": "assistant", "content": reply})
    if escaped:
        st.session_state.escaped = True
        st.rerun()
