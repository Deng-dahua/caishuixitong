"""One-time migration of the legacy deployment key into a user's private store."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from llm_credentials import migrate_legacy_credential
from security import init_security_db


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default="admin")
    parser.add_argument("--provider", default="deepseek")
    parser.add_argument("--model", default="deepseek-v4-flash")
    args = parser.parse_args()

    api_key = os.environ.get("LLM_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("legacy LLM_API_KEY is not available")

    init_security_db()
    credential = migrate_legacy_credential(
        username=args.username,
        provider=args.provider,
        model=args.model,
        api_key=api_key,
    )
    print(
        "Migrated legacy credential to "
        f"{args.username}/{credential['provider']}/{credential['model']} "
        f"(ending ...{credential['last4']})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
