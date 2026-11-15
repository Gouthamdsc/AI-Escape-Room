"""Tiny configuration helpers: read the API key and model name from the
environment (or from a local .env file that is NOT committed to git)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_env(path=None):
    """Load KEY=VALUE lines from .env into os.environ (existing vars win)."""
    p = Path(path) if path else ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_api_key():
    load_env()
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")


def get_model():
    load_env()
    return os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
