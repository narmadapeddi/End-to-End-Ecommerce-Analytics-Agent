"""Minimal local Ollama client for Qwen3 4B."""

from __future__ import annotations

import json
import os
from json import JSONDecodeError
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


OLLAMA_GENERATE_URL = "http://127.0.0.1:11434/api/generate"
MODEL_NAME = os.getenv("OLIST_LLM_MODEL", "qwen3:1.7b")
REQUEST_TIMEOUT_SECONDS = 300


class OllamaConnectionError(ConnectionError):
    """Raised when the local Ollama service cannot be reached."""


class OllamaAPIError(RuntimeError):
    """Raised when Ollama returns an invalid or unsuccessful API response."""


def _visible_answer(generated_text: str) -> str:
    """Return Qwen's user-facing answer if a reasoning trace is included."""

    if "</think>" in generated_text:
        generated_text = generated_text.rsplit("</think>", maxsplit=1)[1]
    return generated_text.strip()


def generate_response(prompt: str) -> str:
    """Send a prompt to local Qwen3 4B through Ollama and return its text."""

    if not isinstance(prompt, str):
        raise TypeError("prompt must be a string.")
    if not prompt.strip():
        raise ValueError("prompt cannot be empty.")

    payload = json.dumps(
        {
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "think": False,
        }
    ).encode("utf-8")

    request = Request(
        OLLAMA_GENERATE_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise OllamaAPIError(
            f"Ollama API returned HTTP {error.code}: {details}"
        ) from error
    except URLError as error:
        raise OllamaConnectionError(
            "Could not connect to Ollama at http://127.0.0.1:11434. "
            "Make sure Ollama is installed and running. "
            f"Details: {error.reason}"
        ) from error
    except TimeoutError as error:
        raise OllamaConnectionError(
            f"Ollama did not respond within {REQUEST_TIMEOUT_SECONDS} seconds."
        ) from error

    try:
        result = json.loads(response_body)
    except JSONDecodeError as error:
        raise OllamaAPIError(
            f"Ollama returned invalid JSON: {response_body[:500]}"
        ) from error

    if "error" in result:
        raise OllamaAPIError(f"Ollama API error: {result['error']}")

    generated_text = result.get("response")
    if not isinstance(generated_text, str):
        raise OllamaAPIError("Ollama response did not contain generated text.")

    return _visible_answer(generated_text)
