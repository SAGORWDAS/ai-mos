"""Package reviewable source without local accounts, secrets, databases or dependencies."""

import hashlib
import os
import sys
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
destination = (
    Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else root.parent / "ai-mos-source.zip"
)
if destination.is_relative_to(root):
    raise SystemExit("Choose an archive destination outside the source folder")
excluded = {
    ".git",
    ".venv",
    "node_modules",
    ".next",
    ".run",
    ".tmp",
    ".tmp-pack",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "out",
    "dist",
    "build",
}
files = []
for current, directories, names in os.walk(root):
    directories[:] = sorted(name for name in directories if name not in excluded)
    for name in sorted(names):
        path = Path(current) / name
        if path.is_symlink() or ".egg-info" in str(path.relative_to(root)):
            continue
        if name.startswith(".env") and name != ".env.example":
            continue
        if name.endswith((".db", ".db-wal", ".db-shm", ".db-journal", ".pyc", ".tsbuildinfo")):
            continue
        files.append(path)
destination.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in files:
        archive.write(path, "ai-mos/" + path.relative_to(root).as_posix())
with zipfile.ZipFile(destination) as archive:
    if archive.testzip() is not None:
        raise SystemExit("Archive integrity check failed")
digest = hashlib.sha256(destination.read_bytes()).hexdigest()
destination.with_suffix(".zip.sha256").write_text(
    digest + "  " + destination.name + "\n", encoding="ascii"
)
print(f"Packaged {len(files)} source files; archive integrity verified.")
