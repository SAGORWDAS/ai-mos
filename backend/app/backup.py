"""Consistent local backups and verified restores to a new destination only."""

import argparse
import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path


def inventory(database):
    with closing(
        sqlite3.connect(f"file:{Path(database).as_posix()}?mode=ro", uri=True)
    ) as connection:
        if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Database integrity check failed")
        tables = [
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        return {
            name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            for name in sorted(tables)
        }


def copy_database(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if destination.exists():
        raise FileExistsError("Destination already exists; choose a new path")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix="backup-", suffix=".db", dir=destination.parent)
    os.close(descriptor)
    try:
        with closing(sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)) as original:
            with closing(sqlite3.connect(temporary)) as target:
                original.backup(target)
        counts = inventory(temporary)
        os.link(temporary, destination)
        return counts
    finally:
        Path(temporary).unlink(missing_ok=True)


def backup(source, destination):
    if Path(destination).with_suffix(Path(destination).suffix + ".manifest.json").exists():
        raise FileExistsError("Backup manifest already exists; choose a new path")
    counts = copy_database(source, destination)
    path = Path(destination)
    manifest = {
        "format": "ai-mos-sqlite-v1",
        "counts": counts,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    path.with_suffix(path.suffix + ".manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


def restore(source, destination):
    path = Path(source)
    manifest = json.loads(path.with_suffix(path.suffix + ".manifest.json").read_text())
    if manifest.get("sha256") != hashlib.sha256(path.read_bytes()).hexdigest():
        raise ValueError("Backup checksum mismatch")
    if manifest.get("counts") != inventory(path):
        raise ValueError("Backup row counts mismatch")
    counts = copy_database(path, destination)
    if counts != manifest["counts"]:
        raise ValueError("Restored row counts mismatch")
    return counts


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["backup", "restore"])
    parser.add_argument("source")
    parser.add_argument("destination")
    args = parser.parse_args()
    function = backup if args.operation == "backup" else restore
    print(json.dumps(function(args.source, args.destination), indent=2))
