"""Stream a zstd JSONL delivery as newline-aligned byte blocks, never holding more than 64 MiB."""

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import zstandard

ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"
MAX_BUFFER = 64 * 1024 * 1024
CHUNK = 4 * 1024 * 1024
# A block is cut once it reaches this size; the buffer then holds at most one more chunk.
BLOCK_BYTES = MAX_BUFFER - CHUNK
# The file was written with a long-distance window (the explorer decoded it with --long=31).
MAX_WINDOW = 2**31


@dataclass(frozen=True)
class Block:
    data: bytes  # whole lines, each ending in \n
    oversize: int = 0  # lines discarded for exceeding the buffer since the previous block


def is_zstd(path: str | Path) -> bool:
    with open(path, "rb") as f:
        return f.read(4) == ZSTD_MAGIC


def stream_blocks(path: str | Path, block_bytes: int = BLOCK_BYTES) -> Iterator[Block]:
    """Yield blocks of whole lines of about `block_bytes`; none exceeds `block_bytes` plus one read
    chunk. A line that alone fills that buffer is dropped and counted in the next `oversize`."""
    chunk_bytes = max(1, min(CHUNK, block_bytes // 4))
    parts: list[bytes] = []
    size = 0
    skipping = False  # inside an oversize line, discarding until its newline
    oversize = 0
    with open(path, "rb") as f:
        reader = zstandard.ZstdDecompressor(max_window_size=MAX_WINDOW).stream_reader(f)
        while True:
            chunk = reader.read(chunk_bytes)
            if not chunk:
                break
            if skipping:
                nl = chunk.find(b"\n")
                if nl < 0:
                    continue
                chunk = chunk[nl + 1 :]
                skipping = False
                if not chunk:
                    continue
            parts.append(chunk)
            size += len(chunk)
            if size < block_bytes:
                continue
            buf = b"".join(parts)
            cut = buf.rfind(b"\n")
            if cut < 0:  # one line fills the whole buffer
                oversize += 1
                skipping = True
                parts, size = [], 0
                continue
            yield Block(buf[: cut + 1], oversize)
            oversize = 0
            rest = buf[cut + 1 :]
            parts, size = ([rest], len(rest)) if rest else ([], 0)
    tail = b"".join(parts)
    if tail.strip():
        yield Block(tail if tail.endswith(b"\n") else tail + b"\n", oversize)
    elif oversize:
        yield Block(b"", oversize)


def stream_lines(path: str | Path) -> Iterator[bytes]:
    """One line at a time, without its newline."""
    for block in stream_blocks(path):
        yield from block.data.split(b"\n")[:-1]
