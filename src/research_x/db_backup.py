from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SAFE_BACKUP_ID = re.compile(r"^[A-Za-z0-9_.-]+$")
BACKUP_SCHEMA_VERSION = 2


def create_sqlite_backup(
    db_path: str | Path,
    *,
    backup_dir: str | Path | None = None,
    label: str | None = None,
) -> dict[str, Any]:
    source = Path(db_path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(f"SQLite database does not exist: {source}")
    root = _backup_root(source, backup_dir)
    root.mkdir(parents=True, exist_ok=True)

    backup_id = _backup_id(source, label)
    backup_path = _backup_path(root, backup_id)
    if backup_path.exists():
        raise FileExistsError(f"backup already exists: {backup_path}")

    with (
        sqlite3.connect(_read_only_uri(source), uri=True) as source_conn,
        sqlite3.connect(backup_path) as backup_conn,
    ):
        source_conn.backup(backup_conn)

    created_at = datetime.now(tz=UTC).isoformat()
    manifest = {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "backup_id": backup_id,
        "created_at": created_at,
        "source_db_path": str(source),
        "source_open_mode": "read_only",
        "backup_path": str(backup_path),
        "source_size_bytes": source.stat().st_size,
        "backup_size_bytes": backup_path.stat().st_size,
        "source_sha256": _sha256(source),
        "backup_sha256": _sha256(backup_path),
    }
    manifest_path = _manifest_path(backup_path)
    manifest["manifest_path"] = str(manifest_path)
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return manifest


def rollback_sqlite_backup(
    db_path: str | Path,
    *,
    backup_id: str,
    backup_dir: str | Path | None = None,
) -> dict[str, Any]:
    target = Path(db_path).expanduser().resolve()
    root = _backup_root(target, backup_dir)
    backup_path = _backup_path(root, backup_id)
    manifest_path = _manifest_path(backup_path)
    if not backup_path.exists():
        raise FileNotFoundError(f"backup does not exist: {backup_path}")
    if not manifest_path.exists():
        raise FileNotFoundError(f"backup manifest does not exist: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("backup_id") != backup_id:
        raise ValueError(f"backup manifest id does not match requested backup: {backup_id}")
    if manifest.get("backup_sha256") != _sha256(backup_path):
        raise ValueError(f"backup checksum mismatch: {backup_path}")
    source_db_path = manifest.get("source_db_path")
    if source_db_path is None:
        raise ValueError(f"backup manifest is missing source_db_path: {manifest_path}")
    if Path(source_db_path).expanduser().resolve() != target:
        raise ValueError(
            "backup source does not match rollback target: "
            f"source={source_db_path} target={target}"
        )

    target.parent.mkdir(parents=True, exist_ok=True)
    with (
        sqlite3.connect(_read_only_uri(backup_path), uri=True) as source_conn,
        sqlite3.connect(target) as target_conn,
    ):
        source_conn.backup(target_conn)

    result = dict(manifest)
    result.update(
        {
            "restored_at": datetime.now(tz=UTC).isoformat(),
            "restored_db_path": str(target),
            "restored_size_bytes": target.stat().st_size,
            "restored_sha256": _sha256(target),
        }
    )
    return result


def _backup_root(db_path: Path, backup_dir: str | Path | None) -> Path:
    root = Path(backup_dir).expanduser() if backup_dir is not None else db_path.parent / "backups"
    return root.resolve()


def _backup_id(source: Path, label: str | None) -> str:
    timestamp = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    suffix = _safe_id_part(label or source.stem)
    return f"{timestamp}-{suffix}"


def _safe_id_part(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip(".-")
    return normalized or "x-data"


def _backup_path(root: Path, backup_id: str) -> Path:
    if not SAFE_BACKUP_ID.fullmatch(backup_id):
        raise ValueError(f"unsafe backup id: {backup_id}")
    root_resolved = root.resolve()
    candidate = (root_resolved / f"{backup_id}.sqlite3").resolve()
    if candidate.parent != root_resolved:
        raise ValueError(f"backup path escapes backup directory: {backup_id}")
    return candidate


def _manifest_path(backup_path: Path) -> Path:
    return backup_path.with_suffix(backup_path.suffix + ".manifest.json")


def _read_only_uri(path: Path) -> str:
    return f"{path.resolve().as_uri()}?mode=ro"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
