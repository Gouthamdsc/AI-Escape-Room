"""One turn of Version 2:  text -> parser -> engine -> narrator -> reply."""
import re

from v2 import engine, narrator, parser

MAX_INPUT = 400


def sanitize(text):
    text = re.sub(r"[\x00-\x1f\x7f]", " ", text or "")
    return text.strip()[:MAX_INPUT]


def play_turn(cfg, state, text, llm=None, use_llm_parser=True, use_llm_narrator=True):
    """Play one player message. `state` is updated in place only by the engine."""
    text = sanitize(text)
    if not text:
        return {"reply": "Say what you want to do.", "action": None, "outcome": None,
                "source": None, "used_llm": False, "guard": None, "restarted": False}

    action, source = parser.parse(cfg, text, llm if use_llm_parser else None)

    if action["action"] == "restart":
        state.clear()
        state.update(engine.new_state(cfg))
        return {"reply": cfg["intro"], "action": action, "outcome": None, "source": source,
                "used_llm": False, "guard": None, "restarted": True}

    if state["flags"]["escaped"]:
        return {"reply": "You have already escaped! Type 'restart' to play again.", "action": action,
                "outcome": None, "source": source, "used_llm": False, "guard": None, "restarted": False}

    state["turn"] += 1
    outcome = engine.apply_action(cfg, state, action)
    reply, used_llm, guard = narrator.render(cfg, state, outcome, llm if use_llm_narrator else None)

    state["log"].append({"turn": state["turn"], "player": text, "action": action["action"],
                         "ok": outcome["ok"], "event": outcome["event"]})
    return {"reply": reply, "action": action, "outcome": outcome, "source": source,
            "used_llm": used_llm, "guard": guard, "restarted": False}
