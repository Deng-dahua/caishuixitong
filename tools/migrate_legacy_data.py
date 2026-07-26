"""One-way migration from a legacy project into the private data directory."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from runtime_storage import ACCOUNTING_DB, DATA_DIR, UPLOAD_DIR, safe_filename


DATABASE_CANDIDATES = (
    "accounting.db", "database.db", "tax-risk.db", "tax_audit.db", "audit.db",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def migrate_database(source_root: Path) -> dict:
    candidates = [source_root / name for name in DATABASE_CANDIDATES if (source_root / name).is_file()]
    if not candidates:
        return {"status": "not_found"}
    source = max(candidates, key=lambda path: path.stat().st_mtime)
    ACCOUNTING_DB.parent.mkdir(parents=True, exist_ok=True)
    if ACCOUNTING_DB.exists():
        raise FileExistsError(f"destination database already exists: {ACCOUNTING_DB}")
    source_connection = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    destination_connection = sqlite3.connect(str(ACCOUNTING_DB))
    try:
        source_connection.backup(destination_connection)
        integrity = destination_connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError(f"migrated database failed integrity_check: {integrity}")
    finally:
        source_connection.close()
        destination_connection.close()
    return {
        "status": "migrated",
        "source": str(source),
        "destination": str(ACCOUNTING_DB),
        "sha256": sha256(ACCOUNTING_DB),
    }


def migrate_uploads(source_root: Path) -> dict:
    legacy = source_root / "static" / "uploads" / "tax-risk-docs"
    if not legacy.is_dir():
        return {"status": "not_found", "files": 0}
    count = 0
    bytes_copied = 0
    for source in legacy.rglob("*"):
        if not source.is_file() or source.is_symlink():
            continue
        relative = source.relative_to(legacy)
        company = relative.parts[0] if relative.parts and relative.parts[0].isdigit() else "unassigned"
        destination_dir = UPLOAD_DIR / company
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = destination_dir / safe_filename(source.name)
        if destination.exists():
            suffix = hashlib.sha256(str(relative).encode("utf-8")).hexdigest()[:10]
            destination = destination.with_name(f"{destination.stem}_{suffix}{destination.suffix}")
        shutil.copy2(source, destination)
        count += 1
        bytes_copied += destination.stat().st_size
    return {"status": "migrated", "files": count, "bytes": bytes_copied}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    args = parser.parse_args()
    source_root = args.source_root.resolve()
    if not source_root.is_dir():
        parser.error("source root is not a directory")
    if source_root == Path(__file__).resolve().parents[1]:
        parser.error("source and destination projects must be different")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "migrated_at": int(time.time()),
        "source_root": str(source_root),
        "sessions": "not migrated; all legacy sessions are revoked",
        "api_keys": "not migrated; rotate and configure through the environment",
        "database": migrate_database(source_root),
        "uploads": migrate_uploads(source_root),
    }
    report_path = DATA_DIR / "migration_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
