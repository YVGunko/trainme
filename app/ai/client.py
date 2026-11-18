"""One OpenAI-compatible chat call, with no knowledge of workouts.

The provider is chosen by configuration, not by code, because the shape of the
request is identical for DeepSeek, Groq, and most others. That keeps a provider
change to an environment variable instead of a rewrite.

No SDK: this is a single POST with a JSON body, and the project already talks to
HTTP this way. A dependency would only wrap the same request.

The key is read from the environment and never logged, never returned, and never
put in an error message.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

# DeepSeek is the default because it takes Alipay and its flash model is cheap
# enough that a hundred recommendations cost cents.
DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-flash"

# A recommendation is a small structured answer. A minute is already generous,
# and an unbounded wait would hold a web request open.
_TIMEOUT_SECONDS = 120


class LlmNotConfigured(Exception):
    """Raised when no API key is set."""


class LlmError(Exception):
    """Raised when the provider refuses or fails the call."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class LlmRateLimited(LlmError):
    """Raised when the provider answers 429 or says the quota is exhausted."""


def is_configured() -> bool:
    return bool(os.environ.get("LLM_API_KEY", "").strip())


def chat(
    messages: list[dict[str, str]],
    schema: dict[str, Any],
    temperature: float = 0.2,
) -> dict[str, Any]:
    """Send the messages and return the parsed JSON object the model answered.

    ``schema`` is passed as a JSON schema when the provider supports it. The
    answer is parsed here, so a caller never receives text to interpret itself.
    """
    key = os.environ.get("LLM_API_KEY", "").strip()
    if not key:
        raise LlmNotConfigured
    base = (os.environ.get("LLM_BASE_URL") or DEFAULT_BASE_URL).strip().rstrip("/")
    model = (os.environ.get("LLM_MODEL") or DEFAULT_MODEL).strip()

    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        # Both keys are sent: providers that understand json_schema use it and
        # ignore json_object, and the reverse. DeepSeek reads json_object.
        "response_format": {"type": "json_object"},
        "stream": False,
    }
    answer = _post(f"{base}/chat/completions", key, body)
    return _content(answer, schema)


def _post(url: str, key: str, body: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "authorization": f"Bearer {key}",
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        raise _http_error(error) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        # The message from a socket error can carry the URL but never the key,
        # because the key travels in a header.
        raise LlmError(f"Provider connection failed: {type(error).__name__}") from error
    except (UnicodeError, json.JSONDecodeError) as error:
        raise LlmError("Provider answered with something that is not JSON") from error
    if not isinstance(payload, dict):
        raise LlmError("Provider answered with an unexpected shape")
    return payload


def _http_error(error: urllib.error.HTTPError) -> LlmError:
    detail = ""
    try:
        raw = error.read().decode(errors="replace")
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            inner = parsed.get("error")
            if isinstance(inner, dict):
                detail = str(inner.get("message") or "")
            elif isinstance(inner, str):
                detail = inner
    except (UnicodeError, json.JSONDecodeError, OSError, ValueError):
        detail = ""
    name = f"Provider error {error.code}"
    if detail:
        name = f"{name}: {detail[:200]}"
    if error.code == 429:
        return LlmRateLimited(name, 429)
    if error.code == 402:
        # DeepSeek answers 402 when the prepaid balance is empty.
        return LlmRateLimited(f"{name} (balance may be empty)", 402)
    return LlmError(name, error.code)


def _content(answer: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    choices = answer.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LlmError("Provider returned no choices")
    first = choices[0]
    message = first.get("message") if isinstance(first, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise LlmError("Provider returned an empty answer")
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as error:
        raise LlmError("Answer was not valid JSON") from error
    if not isinstance(parsed, dict):
        raise LlmError("Answer was not a JSON object")
    missing = [key for key in schema.get("required", []) if key not in parsed]
    if missing:
        raise LlmError(f"Answer is missing {missing[0]}")
    return parsed


__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "LlmError",
    "LlmNotConfigured",
    "LlmRateLimited",
    "chat",
    "is_configured",
]
