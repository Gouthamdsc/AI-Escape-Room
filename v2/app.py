"""Version 2 - Reliable AI Escape Room (structured state + validation).

Run:  streamlit run v2/app.py
Works without an API key too (the Game Master then answers with the engine's own text).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

from common.config import get_api_key  # noqa: E402
from common.llm import GeminiClient, LLMError  # noqa: E402
from v2 import engine, game  # noqa: E402

st.set_page_config(page_title="AI Escape Room - v2", page_icon="🔐", layout="wide")
CFG = engine.load_config()


@st.cache_resource
def get_llm():
    if not get_api_key():
        return None
    try:
        return GeminiClient()
    except LLMError:
        return None


def reset_game():
    st.session_state.state = engine.new_state(CFG)
    st.session_state.chat = [{"role": "assistant", "content": CFG["intro"]}]
    st.session_state.last = None


if "state" not in st.session_state:
    reset_game()

llm = get_llm()
state = st.session_state.state

st.title("🔐 The Locked Library - v2")
st.caption("Version 2: Python owns the game state and rules; the LLM only narrates and interprets wording.")

# ---- handle input first so the sidebar below shows the updated state -------
prompt = st.chat_input("What do you do?")
if prompt:
    st.session_state.chat.append({"role": "user", "content": prompt})
    use_llm = st.session_state.get("use_llm", True) and llm is not None
    with st.spinner("The Game Master is thinking..."):
        result = game.play_turn(CFG, state, prompt, llm=llm if use_llm else None)
    if result["restarted"]:
        st.session_state.chat = [{"role": "assistant", "content": CFG["intro"]}]
        st.session_state.last = None
    else:
        st.session_state.chat.append({"role": "assistant", "content": result["reply"]})
        st.session_state.last = result

state = st.session_state.state

# ------------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Your status")
    inv = [CFG["items"][i]["name"] for i in state["inventory"]]
    st.markdown("**Inventory:** " + (", ".join(inv) if inv else "empty"))
    st.markdown("**Door:** " + ("🔓 unlocked" if state["flags"]["door_unlocked"] else "🔒 locked"))
    st.markdown("**Journal**")
    if state["clues"]:
        for cid in state["clues"]:
            st.markdown(f"- {CFG['clues'][cid]}")
    else:
        st.caption("No clues found yet.")
    st.divider()
    if llm is None:
        st.info("No Gemini key found - running in offline mode (engine text only).")
    else:
        st.checkbox("Use Gemini for narration and fuzzy wording", value=True, key="use_llm")
    show_debug = st.checkbox("Show debug panel", value=False)
    if st.button("🔄 Restart game", use_container_width=True):
        reset_game()
        st.rerun()
    if show_debug and st.session_state.last:
        last = st.session_state.last
        st.caption("Last turn")
        st.json({"parsed_action": last["action"], "parsed_by": last["source"],
                 "outcome": {"ok": last["outcome"]["ok"], "event": last["outcome"]["event"]} if last["outcome"] else None,
                 "narrated_by_llm": last["used_llm"], "guard_rejection": last["guard"]})

# ------------------------------------------------------------------ chat log
for msg in st.session_state.chat:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if state["flags"]["escaped"]:
    st.success("🎉 You escaped The Locked Library! Type *restart* or press the button to play again.")
