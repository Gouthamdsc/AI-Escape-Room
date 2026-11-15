"""Version 2 game engine: all rules, state and validation live here, in Python.

The LLM never decides whether an action succeeds. The engine takes a structured
action (e.g. {"action": "use", "item": "brass_key", "target": "safe"}), validates
it against the game state, updates the state, and returns an *outcome* made of
plain facts. The narrator (LLM) may only describe those facts.
"""
import json
from pathlib import Path

CONFIG_PATH = Path(__file__).with_name("game_config.json")

NOT_FOUND = "You don't see anything like that here."


def load_config(path=CONFIG_PATH):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def new_state(cfg):
    return {
        "inventory": [],
        "examined": [],
        "found_items": [],  # items the player has discovered and may pick up
        "clues": [],
        "flags": {
            "drawer_open": False,
            "safe_open": False,
            "door_unlocked": False,
            "escaped": False,
        },
        "attempts": {},
        "hint_levels": {},
        "turn": 0,
        "log": [],
    }


def out(ok, event, facts, **extra):
    return {"ok": ok, "event": event, "facts": list(facts), **extra}


def _add(lst, value):
    if value not in lst:
        lst.append(value)


def is_visible(cfg, state, oid):
    obj = cfg["objects"].get(oid)
    if obj is None:
        return False
    cond = obj.get("visible_when")
    return not cond or cond["examined"] in state["examined"]


def visible_objects(cfg, state):
    return [o for o in cfg["objects"] if is_visible(cfg, state, o)]


# ----------------------------------------------------------------- handlers
def _examine(cfg, state, a):
    oid, iid = a.get("target"), a.get("item")
    if oid is None and iid is not None:
        if iid in state["inventory"]:
            return out(True, "examine_item", [cfg["items"][iid]["description"]])
        return out(False, "not_found", [NOT_FOUND])
    if oid is None or not is_visible(cfg, state, oid):
        return out(False, "not_found", [NOT_FOUND])

    obj = cfg["objects"][oid]
    ex = obj["examine"]
    text = ex["text"]
    for flag, flag_text in obj.get("flag_texts", {}).items():
        if state["flags"].get(flag):
            text = flag_text
    facts = [text]

    _add(state["examined"], oid)
    for iid2 in ex.get("reveals_items", []):
        _add(state["found_items"], iid2)
    for cid in ex.get("reveals_clues", []):
        _add(state["clues"], cid)

    need = ex.get("needs_item")
    if need and need["item"] in state["inventory"]:
        facts.append(need["text"])
        for cid in need.get("reveals_clues", []):
            _add(state["clues"], cid)
    return out(True, "examine", facts)


def _take(cfg, state, a):
    iid, oid = a.get("item"), a.get("target")
    if iid is None:
        if oid and is_visible(cfg, state, oid):
            return out(False, "cant_take", [f"You can't take the {cfg['objects'][oid]['name']}."])
        return out(False, "not_found", [NOT_FOUND])
    name = cfg["items"][iid]["name"]
    if iid in state["inventory"]:
        return out(False, "already", [f"You already have the {name}."])
    if iid not in state["found_items"]:
        return out(False, "not_found", [NOT_FOUND])
    state["inventory"].append(iid)
    return out(True, "take", [f"You take the {name}."])


def _solve(cfg, state, pid):
    p = cfg["puzzles"][pid]
    state["flags"][p["flag"]] = True
    for iid in p["on_solve"].get("reveals_items", []):
        _add(state["found_items"], iid)
    for cid in p["on_solve"].get("reveals_clues", []):
        _add(state["clues"], cid)
    return out(True, "solved", p["on_solve"]["facts"], puzzle=pid)


def _use(cfg, state, a):
    iid, oid = a.get("item"), a.get("target")
    if iid is None or iid not in state["inventory"]:
        return out(False, "no_item", ["You aren't carrying anything like that."])
    item = cfg["items"][iid]
    if oid is None:
        return out(False, "need_target", [f"Use the {item['name']} on what?"])
    if not is_visible(cfg, state, oid):
        return out(False, "not_found", [NOT_FOUND])
    obj = cfg["objects"][oid]
    if item.get("use_on", {}).get(oid) == "examine":
        return _examine(cfg, state, {"target": oid})
    pid = obj.get("puzzle")
    p = cfg["puzzles"].get(pid) if pid else None
    if p and p["type"] == "item" and p["item"] == iid:
        if state["flags"][p["flag"]]:
            return out(False, "already", [p["already_text"]])
        return _solve(cfg, state, pid)
    return out(False, "no_effect", [f"Using the {item['name']} on the {obj['name']} has no effect."])


def _enter_code(cfg, state, a):
    oid, code = a.get("target"), a.get("code")
    if oid is None:
        return out(False, "need_target", ["Which lock do you want to try a code on?"])
    if not is_visible(cfg, state, oid):
        return out(False, "not_found", [NOT_FOUND])
    obj = cfg["objects"][oid]
    pid = obj.get("puzzle")
    p = cfg["puzzles"].get(pid) if pid else None
    if not p or p["type"] != "code":
        return out(False, "no_effect", [f"There is nothing on the {obj['name']} that takes a code."])
    if state["flags"][p["flag"]]:
        return out(False, "already", [p["already_text"]])
    if code is None:
        return out(False, "need_code", ["Which four digits do you want to enter? Type them out."])
    if len(code) != 4 or not code.isdigit():
        return out(False, "bad_format", ["A code must be exactly four digits."])

    state["attempts"][pid] = state["attempts"].get(pid, 0) + 1
    req = p.get("requires", {})
    prereqs_met = all(state["flags"].get(f) for f in req.get("flags", [])) and all(
        c in state["clues"] for c in req.get("clues", [])
    )
    if code == p["code"] and prereqs_met:
        return _solve(cfg, state, pid)
    return out(False, "code_wrong", [p["fail_text"]])


def _open(cfg, state, a):
    oid = a.get("target")
    if oid is None:
        return out(False, "need_target", ["What do you want to open?"])
    if not is_visible(cfg, state, oid):
        return out(False, "not_found", [NOT_FOUND])
    obj = cfg["objects"][oid]
    pid = obj.get("puzzle")
    p = cfg["puzzles"].get(pid) if pid else None
    if obj.get("is_exit"):
        if state["flags"]["door_unlocked"]:
            state["flags"]["escaped"] = True
            return out(True, "escaped", [cfg["exit_text"]])
        return out(False, "locked", [p["locked_text"]])
    if p:
        if state["flags"][p["flag"]]:
            return out(False, "already", [p["already_text"]])
        return out(False, "locked", [p["locked_text"]])
    return out(False, "no_effect", [f"The {obj['name']} can't be opened."])


def _inventory(cfg, state, a):
    if not state["inventory"]:
        return out(True, "inventory", ["You are carrying nothing."])
    names = [cfg["items"][i]["name"] for i in state["inventory"]]
    return out(True, "inventory", ["You are carrying: " + ", ".join(names) + "."])


def _look_around(cfg, state, a):
    names = [cfg["objects"][o]["name"] for o in visible_objects(cfg, state)]
    return out(True, "look_around", ["You can see: " + ", ".join(names) + "."])


def next_step(state):
    f, ex, inv, clues = state["flags"], state["examined"], state["inventory"], state["clues"]
    if "desk" not in ex:
        return "desk"
    if "magnifying_glass" not in inv:
        return "take_glass"
    if "bookshelf" not in ex:
        return "bookshelf"
    if "books_digits" not in clues:
        return "books"
    if not f["drawer_open"]:
        return "drawer"
    if "brass_key" not in inv and not f["safe_open"]:
        return "take_key"
    if "painting" not in ex:
        return "painting"
    if not f["safe_open"]:
        return "safe"
    if "clock_time" not in clues:
        return "clock"
    return "door"


def _hint(cfg, state, a):
    step = next_step(state)
    texts = cfg["hints"][step]
    level = state["hint_levels"].get(step, 0)
    state["hint_levels"][step] = level + 1
    return out(True, "hint", [texts[min(level, len(texts) - 1)]])


def _help(cfg, state, a):
    return out(True, "help", [cfg["help"]])


def _claim(cfg, state, a):
    """Player says something already happened. Only the real state counts."""
    oid, iid = a.get("target"), a.get("item")
    if oid:
        pid = cfg["objects"][oid].get("puzzle")
        p = cfg["puzzles"].get(pid) if pid else None
        if p and is_visible(cfg, state, oid):
            if state["flags"][p["flag"]]:
                return out(True, "claim", [p["already_text"]])
            return out(False, "claim", [p["locked_text"] + " Only what you actually do in the room counts."])
    if iid:
        if iid in state["inventory"]:
            return out(True, "claim", [f"Yes, you have the {cfg['items'][iid]['name']}."])
        return out(False, "claim", ["You aren't carrying that. Only what you actually do in the room counts."])
    return out(False, "claim", ["Only what you actually do in the room counts. Check your inventory or ask for a hint."])


def _meta(cfg, state, a):
    return out(
        False,
        "meta",
        ["The room does not answer to that. You are a prisoner in this library, not its owner. "
         "Try examining something or type 'hint'."],
    )


def _unknown(cfg, state, a):
    return out(False, "unknown", ["You're not sure how to do that. Try examining objects, taking or using items, or type 'help'."])


HANDLERS = {
    "examine": _examine,
    "take": _take,
    "use": _use,
    "enter_code": _enter_code,
    "open": _open,
    "inventory": _inventory,
    "look_around": _look_around,
    "hint": _hint,
    "help": _help,
    "claim": _claim,
    "meta": _meta,
    "unknown": _unknown,
}


def apply_action(cfg, state, action):
    """Validate and apply one structured action. Returns an outcome dict."""
    handler = HANDLERS.get(action.get("action"), _unknown)
    return handler(cfg, state, action)
