"""Allowlisted OpenAI-compatible model providers.

Base URLs are fixed by the application.  Users may select a provider and model,
but cannot supply an arbitrary endpoint that could receive accounting data.
"""
from __future__ import annotations

import re


PROVIDERS = {
    "deepseek": {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-v4-flash",
        "models": ["deepseek-v4-flash", "deepseek-v4-pro"],
    },
    "doubao": {
        "name": "豆包（火山方舟）",
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "default_model": "doubao-seed-2-0-lite-260215",
        "models": [
            "doubao-seed-2-0-lite-260215",
            "doubao-seed-2-0-pro-260215",
        ],
    },
    "qwen": {
        "name": "通义千问（阿里云百炼）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
        "models": ["qwen-plus", "qwen-turbo", "qwen-max"],
    },
    "zhipu": {
        "name": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-5.2",
        "models": ["glm-5.2", "glm-4.7", "glm-4-flash"],
    },
    "kimi": {
        "name": "Kimi",
        "base_url": "https://api.moonshot.cn/v1",
        "default_model": "kimi-k3",
        "models": ["kimi-k3", "kimi-k2.6", "kimi-k2.7-code-highspeed"],
    },
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "models": ["gpt-4o-mini"],
    },
}

_MODEL_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


def validate_provider(provider: str) -> str:
    normalized = (provider or "").strip().lower()
    if normalized not in PROVIDERS:
        raise ValueError("不支持的模型服务商")
    return normalized


def validate_model(provider: str, model: str | None) -> str:
    normalized_provider = validate_provider(provider)
    value = (model or PROVIDERS[normalized_provider]["default_model"]).strip()
    if not _MODEL_RE.fullmatch(value):
        raise ValueError("模型名称格式不正确")
    return value


def public_provider_catalog() -> list[dict]:
    return [
        {
            "id": provider,
            "name": config["name"],
            "default_model": config["default_model"],
            "models": list(config["models"]),
        }
        for provider, config in PROVIDERS.items()
    ]
