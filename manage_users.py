"""Offline administrator CLI.  Passwords are prompted, never command arguments."""
from __future__ import annotations

import argparse
import getpass
import json
import sqlite3
import sys

from security import create_user, init_security_db, list_users, reset_password, revoke_all_sessions


def _password_twice() -> str:
    first = getpass.getpass("Password: ")
    second = getpass.getpass("Repeat password: ")
    if first != second:
        raise ValueError("passwords do not match")
    return first


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage local application users")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create")
    create.add_argument("username")
    create.add_argument("--role", choices=("admin", "user"), default="user")
    create.add_argument("--companies", default="", help="comma-separated company IDs")

    reset = sub.add_parser("reset-password")
    reset.add_argument("username")

    revoke = sub.add_parser("revoke-sessions")
    revoke.add_argument("username")
    sub.add_parser("list")

    args = parser.parse_args()
    init_security_db()
    try:
        if args.command == "create":
            companies = [int(value) for value in args.companies.split(",") if value.strip()]
            user_id = create_user(
                args.username,
                _password_twice(),
                role=args.role,
                company_ids=companies,
            )
            print(f"Created user #{user_id}.")
        elif args.command == "reset-password":
            reset_password(args.username, _password_twice())
            print("Password reset and existing sessions revoked.")
        elif args.command == "revoke-sessions":
            print(f"Revoked {revoke_all_sessions(args.username)} session(s).")
        else:
            print(json.dumps(list_users(), ensure_ascii=False, indent=2))
    except (ValueError, sqlite3.IntegrityError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
