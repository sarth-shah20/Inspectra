"""Content fingerprints invalidate caches when local model or pack artifacts change."""

import hashlib
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=16)
def _hash_files(entries: tuple[tuple[str, int, int], ...]) -> str:
    digest = hashlib.sha256()
    for name, _, _ in entries:
        path = Path(name)
        digest.update(path.name.encode())
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def artifact_fingerprint(path: Path) -> str:
    path = Path(path)
    paths = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
    return _hash_files(
        tuple((str(p.resolve()), p.stat().st_mtime_ns, p.stat().st_size) for p in paths)
    )
