"""Context-aware LLM client with an optional local Ollama fallback."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

from llm_config import get_llm_config


@dataclass
class LLMResponse:
    content: str
    model: str = ""
    backend: str = "unknown"
    tokens_used: int = 0
    raw: Optional[Dict[str, Any]] = None


_OLLAMA_PROBE = {"checked_at": 0.0, "available": False}


def _ollama_available() -> bool:
    now = time.monotonic()
    if now - float(_OLLAMA_PROBE["checked_at"]) < 30:
        return bool(_OLLAMA_PROBE["available"])
    available = False
    try:
        response = httpx.get(
            os.environ.get("OLLAMA_TAGS_URL", "http://127.0.0.1:11434/api/tags"),
            timeout=1.0,
        )
        available = response.status_code == 200 and bool(
            response.json().get("models", [])
        )
    except Exception:
        available = False
    _OLLAMA_PROBE.update({"checked_at": now, "available": available})
    return available


class LLMClient:
    """A short-lived client resolved from the current authenticated user."""

    def __init__(self):
        self._config = get_llm_config(include_secret=True)
        self._has_cloud = bool(
            self._config.get("key")
            and self._config.get("base_url")
            and self._config.get("model")
        )
        self._has_ollama = _ollama_available()
        self._active_backend = (
            self._config.get("provider") if self._has_cloud
            else ("ollama" if self._has_ollama else "none")
        )

    @property
    def available(self) -> bool:
        return self._has_cloud or self._has_ollama

    @property
    def active_backend(self) -> str:
        return str(self._active_backend or "none")

    def chat(
        self,
        messages: List[Dict],
        system: str = "",
        temperature: float = 0.3,
        max_tokens: int = 2000,
    ) -> LLMResponse:
        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        if self._has_cloud:
            try:
                return self._call_cloud(
                    full_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception:
                self._active_backend = "ollama" if self._has_ollama else "failed"

        if self._has_ollama:
            try:
                return self._call_ollama(
                    full_messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except Exception:
                self._active_backend = "failed"
        return LLMResponse(content="", backend=self.active_backend)

    def _call_cloud(
        self,
        messages: List[Dict],
        *,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        provider = str(self._config["provider"])
        model = str(self._config["model"])
        response = httpx.post(
            f"{str(self._config['base_url']).rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {self._config['key']}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        self._active_backend = provider
        return LLMResponse(
            content=str(content or "").strip(),
            model=model,
            backend=provider,
            tokens_used=int(data.get("usage", {}).get("total_tokens", 0) or 0),
            raw=data,
        )

    def _call_ollama(
        self,
        messages: List[Dict],
        *,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        model = os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
        response = httpx.post(
            os.environ.get(
                "OLLAMA_CHAT_URL",
                "http://127.0.0.1:11434/api/chat",
            ),
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": temperature,
                    "num_predict": max_tokens,
                },
            },
            timeout=60.0,
        )
        response.raise_for_status()
        data = response.json()
        self._active_backend = "ollama"
        return LLMResponse(
            content=str(data.get("message", {}).get("content", "")).strip(),
            model=model,
            backend="ollama",
        )


class _ContextualLLM:
    """Compatibility proxy for modules that import the historical global name."""

    @property
    def available(self) -> bool:
        return LLMClient().available

    @property
    def active_backend(self) -> str:
        return LLMClient().active_backend

    def chat(self, *args, **kwargs) -> LLMResponse:
        return LLMClient().chat(*args, **kwargs)


llm = _ContextualLLM()


def get_llm() -> LLMClient:
    return LLMClient()


def is_llm_available() -> bool:
    return LLMClient().available


def reload_llm_client(api_key: str = "") -> bool:
    """Compatibility hook; credentials are now resolved for every request."""
    return is_llm_available()
