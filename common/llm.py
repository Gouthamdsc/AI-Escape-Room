"""Thin wrapper around the Google Gemini API (free tier).

Both game versions talk to the LLM only through GeminiClient.generate(), so
swapping in another provider means changing this one file.
"""
import time

from common.config import get_api_key, get_model


class LLMError(Exception):
    pass


class GeminiClient:
    def __init__(self, api_key=None, model=None):
        self.api_key = api_key or get_api_key()
        self.model = model or get_model()
        if not self.api_key:
            raise LLMError("No API key found. Set GEMINI_API_KEY (see .env.example).")
        try:
            from google import genai  # imported lazily so tests run without it
            from google.genai import types
        except ImportError as exc:  # pragma: no cover
            raise LLMError("Install the SDK first: pip install google-genai") from exc
        self._types = types
        self._client = genai.Client(api_key=self.api_key,)

    def generate(self, system, messages, temperature=0.7, json_mode=False):
        """messages: [{"role": "user"|"assistant", "content": str}, ...]"""
        types = self._types
        contents = [
            types.Content(
                role="user" if m["role"] == "user" else "model",
                parts=[types.Part(text=m["content"])],
            )
            for m in messages
        ]
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json" if json_mode else None,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        )
        last_error = None
        for attempt in range(2):
            try:
                response = self._client.models.generate_content(
                    model=self.model, contents=contents, config=config
                )
                text = (response.text or "").strip()
                if text:
                    return text
                last_error = LLMError("Empty response from model")
            except Exception as exc:  # network / quota / safety errors
                last_error = exc
            time.sleep(1.5)
        raise LLMError(f"Gemini request failed: {last_error}")
