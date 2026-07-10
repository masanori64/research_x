import sqlite3

from research_x.cli import main
from research_x.db_backup import create_sqlite_backup, rollback_sqlite_backup


def test_sqlite_backup_and_rollback_restore_named_backup(tmp_path) -> None:
    db_path = tmp_path / "x_data.sqlite3"
    backup_dir = tmp_path / "backups"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO sample (value) VALUES ('before')")

    manifest = create_sqlite_backup(db_path, backup_dir=backup_dir, label="snapshot")
    assert manifest["source_open_mode"] == "read_only"
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE sample SET value = 'after' WHERE id = 1")

    result = rollback_sqlite_backup(
        db_path,
        backup_dir=backup_dir,
        backup_id=manifest["backup_id"],
    )

    assert result["backup_id"] == manifest["backup_id"]
    with sqlite3.connect(db_path) as conn:
        value = conn.execute("SELECT value FROM sample WHERE id = 1").fetchone()[0]
    assert value == "before"
    assert (backup_dir / f"{manifest['backup_id']}.sqlite3.manifest.json").exists()


def test_sqlite_rollback_rejects_unsafe_backup_id(tmp_path) -> None:
    db_path = tmp_path / "x_data.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")

    try:
        rollback_sqlite_backup(
            db_path,
            backup_dir=tmp_path / "backups",
            backup_id="../outside",
        )
    except ValueError as exc:
        assert "unsafe backup id" in str(exc)
    else:
        raise AssertionError("expected unsafe backup id to be rejected")


def test_sqlite_rollback_rejects_backup_for_different_target(tmp_path) -> None:
    source_db = tmp_path / "source.sqlite3"
    target_db = tmp_path / "target.sqlite3"
    backup_dir = tmp_path / "backups"
    for db_path in (source_db, target_db):
        with sqlite3.connect(db_path) as conn:
            conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")

    manifest = create_sqlite_backup(source_db, backup_dir=backup_dir, label="source")

    try:
        rollback_sqlite_backup(
            target_db,
            backup_dir=backup_dir,
            backup_id=manifest["backup_id"],
        )
    except ValueError as exc:
        assert "backup source does not match rollback target" in str(exc)
    else:
        raise AssertionError("expected rollback target mismatch to be rejected")


def test_db_backup_cli_creates_manifest(tmp_path) -> None:
    db_path = tmp_path / "x_data.sqlite3"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY)")

    assert main(
        [
            "db-backup",
            "--db",
            str(db_path),
            "--backup-dir",
            str(tmp_path / "backups"),
            "--label",
            "cli",
        ]
    ) == 0
    assert list((tmp_path / "backups").glob("*.sqlite3.manifest.json"))


def test_sqlite_backup_includes_committed_wal_data_without_write_access(tmp_path) -> None:
    db_path = tmp_path / "x_data.sqlite3"
    backup_dir = tmp_path / "backups"

    with sqlite3.connect(db_path) as writer:
        assert writer.execute("PRAGMA journal_mode=WAL").fetchone()[0] == "wal"
        writer.execute("PRAGMA wal_autocheckpoint=0")
        writer.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT)")
        writer.execute("INSERT INTO sample (value) VALUES ('committed-in-wal')")
        writer.commit()
        assert db_path.with_name(db_path.name + "-wal").exists()

        manifest = create_sqlite_backup(db_path, backup_dir=backup_dir, label="wal")

    assert manifest["source_open_mode"] == "read_only"
    with sqlite3.connect(manifest["backup_path"]) as backup:
        value = backup.execute("SELECT value FROM sample").fetchone()[0]
    assert value == "committed-in-wal"
