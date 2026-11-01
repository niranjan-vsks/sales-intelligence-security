"""Cheap, stable identity for a delivery, computed before any decompression."""

import hashlib
from pathlib import Path

HEAD_BYTES = 64 * 1024 * 1024
_READ = 8 * 1024 * 1024


def compute_file_id(path: str | Path) -> str:
    """`<sha256 of the first 64 MiB, hex>-<total byte length>`.

    The card writes the separator as ':', which is not a legal character in a Windows directory
    name and file_id names a directory under SIS_DATA, so '-' is used instead.
    """
    path = Path(path)
    h = hashlib.sha256()
    remaining = HEAD_BYTES
    with open(path, "rb") as f:
        while remaining > 0:
            chunk = f.read(min(_READ, remaining))
            if not chunk:
                break
            h.update(chunk)
            remaining -= len(chunk)
    return f"{h.hexdigest()}-{path.stat().st_size}"
