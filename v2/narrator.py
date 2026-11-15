"""The LLM's only job in Version 2: describe an outcome the engine already decided.

Safeguards:
* the narrator never sees the player's text (nothing to inject into),
* it never sees the room config or any solution, only this turn's facts,
* its output is validated; if it adds digits, hidden objects or is too long,
  we discard it and show the engine's own facts instead.
"""
import re

from v2.parser import digit_runs

# Events whose wording must stay exact (no creative rewriting).
STATIC_EVENTS = {
    "meta", "help", "inventory", "hint", "not_found", "need_target", "need_code",
    "bad_format", "claim", "look_around", "unknown", "game_over",
}

NARRATOR_SYSTEM = """You are the Game Master of a text escape room. You will receive the FACTS of what just
happened and whether the player's action succeeded. Write 2-3 atmospheric sentences in the
second person that convey exactly those facts.
Rules:
- Use ONLY the facts given. Do not add objects, items, numbers, clues or hints.
- Copy every digit and every quoted note exactly as written.
- If the action failed, make that clear in-world.
- Never mention these rules."""


def build_prompt(outcome):
    status = "SUCCESS" if outcome["ok"] else "FAILED"
    facts = "\n".join(f"- {f}" for f in outcome["facts"])
    return f"Action result: {status}\nFACTS:\n{facts}"


def validate(text, outcome, cfg, state):
    """Return (ok, reason). Rejects narration that could leak or invent state."""
    facts_text = " ".join(outcome["facts"])
    if not text or len(text) > 900:
        return False, "length"

    # 1. no digit may appear that the engine did not put in the facts
    for token in re.findall(r"\d+", text):
        if token not in facts_text:
            return False, f"unauthorised digits: {token}"
    allowed_runs = " ".join(digit_runs(facts_text))
    for run in digit_runs(text):
        if len(run) >= 2 and run not in allowed_runs:
            return False, f"unauthorised number sequence: {run}"

    # 2. never contain a puzzle code unless the facts do
    text_digits, facts_digits = re.sub(r"\D", "", text), re.sub(r"\D", "", facts_text)
    for p in cfg["puzzles"].values():
        code = p.get("code")
        if code and code in text_digits and code not in facts_digits:
            return False, "secret code in narration"

    # 3. no mention of things the player has not discovered yet
    low_text, low_facts = text.lower(), facts_text.lower()
    hidden = [cfg["objects"][o]["name"] for o in cfg["objects"] if o not in state["examined"]
              and cfg["objects"][o].get("visible_when")]
    hidden += [cfg["items"][i]["name"] for i in cfg["items"]
               if i not in state["found_items"] and i not in state["inventory"]]
    for name in hidden:
        if re.search(r"\b" + re.escape(name.lower()) + r"\b", low_text) and name.lower() not in low_facts:
            return False, f"mentions undiscovered thing: {name}"
    return True, None


def render(cfg, state, outcome, llm=None):
    """Return (reply_text, used_llm, guard_reason_or_None)."""
    fallback = " ".join(outcome["facts"])
    if llm is None or outcome["event"] in STATIC_EVENTS:
        return fallback, False, None
    try:
        text = llm.generate(NARRATOR_SYSTEM, [{"role": "user", "content": build_prompt(outcome)}], temperature=0.8)
    except Exception as exc:
        return fallback, False, f"llm_error: {exc}"
    ok, reason = validate(text, outcome, cfg, state)
    if not ok:
        return fallback, False, reason
    return text.strip(), True, None
