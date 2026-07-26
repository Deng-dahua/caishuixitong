"""Read-only LLM configuration.

Secrets are supplied by the deployment environment and are never persisted in
the web root or returned by an API.
"""
from __future__ import annotations

import os
from urllib.parse import urlparse


PROVIDERS = {
    "deepseek": ("https://api.deepseek.com/v1", "deepseek-chat"),
    "zhipu": ("https://open.bigmodel.cn/api/paas/v4", "glm-4-flash"),
    "doubao": ("https://ark.cn-beijing.volces.com/api/v3", "doubao-lite-32k"),
    "qwen": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-turbo"),
    "openai": ("https://api.openai.com/v1", "gpt-4o-mini"),
}


def get_llm_config(*, include_secret: bool = True) -> dict:
    provider = os.environ.get("LLM_PROVIDER", "deepseek").strip().lower()
    if provider not in PROVIDERS:
        provider = "deepseek"
    default_url, default_model = PROVIDERS[provider]
    base_url = os.environ.get("LLM_BASE_URL", default_url).strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise RuntimeError("LLM_BASE_URL must be a valid HTTPS URL")
    result = {
        "provider": provider,
        "base_url": base_url,
        "model": os.environ.get("LLM_MODEL", default_model).strip() or default_model,
    }
    if include_secret:
        result["key"] = os.environ.get("LLM_API_KEY", "").strip()
    return result


def public_llm_status() -> dict:
    config = get_llm_config(include_secret=True)
    key = config.pop("key", "")
    return {
        "ok": True,
        "has_key": bool(key),
        "last4": key[-4:] if len(key) >= 4 else "",
        **config,
        "managed_by": "environment",
    }
