"""Run the same scenarios against Version 1 (prompt-only) and record what happens.

Needs a Gemini key in .env.  Run from the repo root:  python scripts/probe_v1.py
Writes docs/V1_TRANSCRIPTS.md - read it and fill in the 'Version 1 result' column of
docs/TEST_CASES.md from what the model actually did. LLM output varies between runs,
so run it a few times and note how often the rules are broken.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.llm import GeminiClient  # noqa: E402
from scripts.scenarios import SCENARIOS  # noqa: E402
from v1.prompt import ESCAPE_MARKER, INTRO, SYSTEM_PROMPT  # noqa: E402


def main():
    client = GeminiClient()
    lines = ["# Version 1 transcripts (prompt-only Game Master)", "",
             f"Model: `{client.model}`. Output varies between runs.", ""]
    for title, messages in SCENARIOS.items():
        history = [{"role": "user", "content": "(The game begins.)"},
                   {"role": "assistant", "content": INTRO}]
        lines += [f"## {title}", ""]
        escaped = False
        for m in messages:
            history.append({"role": "user", "content": m})
            reply = client.generate(SYSTEM_PROMPT, history, temperature=0.8)
            escaped = escaped or ESCAPE_MARKER in reply
            clean = reply.replace(ESCAPE_MARKER, "").strip()
            history.append({"role": "assistant", "content": clean})
            lines += [f"**Player:** {m}", "", f"**Game Master:** {clean}", ""]
        lines += [f"*Game declared escaped:* **{escaped}**", ""]
    out = Path(__file__).resolve().parents[1] / "docs" / "V1_TRANSCRIPTS.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
