"""Current user's private LLM configuration."""
from __future__ import annotations

from typing import Optional

from llm_credentials import get_default_credential, list_credentials
from llm_providers import PROVIDERS, public_provider_catalog
from request_context import get_current_user_id


def get_llm_config(
    *,
    include_secret: bool = True,
    user_id: Optional[int] = None,
) -> dict:
    """Return the authenticated user's default provider configuration.

    There is intentionally no process-wide API-key fallback: a request without
    an authenticated user never receives another user's credential.
    """
    resolved_user_id = int(user_id) if user_id is not None else get_current_user_id()
    if resolved_user_id is None:
        return {
            "provider": "",
            "base_url": "",
            "model": "",
            **({"key": ""} if include_secret else {}),
        }

    credential = get_default_credential(int(resolved_user_id))
    if not credential:
        return {
            "provider": "",
            "base_url": "",
            "model": "",
            **({"key": ""} if include_secret else {}),
        }

    result = {
        "provider": credential["provider"],
        "base_url": credential["base_url"],
        "model": credential["model"],
    }
    if include_secret:
        result["key"] = credential["key"]
    return result


def public_llm_status(*, user_id: Optional[int] = None) -> dict:
    resolved_user_id = int(user_id) if user_id is not None else get_current_user_id()
    if resolved_user_id is None:
        return {
            "ok": True,
            "has_key": False,
            "last4": "",
            "provider": "",
            "provider_name": "",
            "model": "",
            "managed_by": "current_user",
        }

    credentials = list_credentials(int(resolved_user_id))
    default = next((item for item in credentials if item["is_default"]), None)
    if not default:
        return {
            "ok": True,
            "has_key": False,
            "last4": "",
            "provider": "",
            "provider_name": "",
            "model": "",
            "credential_count": len(credentials),
            "managed_by": "current_user",
        }
    return {
        "ok": True,
        "has_key": True,
        "last4": default["last4"],
        "provider": default["provider"],
        "provider_name": PROVIDERS[default["provider"]]["name"],
        "model": default["model"],
        "credential_count": len(credentials),
        "managed_by": "current_user",
    }


def public_llm_providers() -> list[dict]:
    return public_provider_catalog()
