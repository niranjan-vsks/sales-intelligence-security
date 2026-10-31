"""Independent check of 1b: decompress the whole zstd file in-process, count newlines and bytes,
and confirm the frame decodes to the end of the compressed input."""
import sys
import time

import zstandard

path = sys.argv[1]
t0 = time.time()
lines = nbytes = 0
with open(path, "rb") as fh:
    dctx = zstandard.ZstdDecompressor(max_window_size=2**31)
    with dctx.stream_reader(fh, read_across_frames=True, closefd=False) as r:
        while True:
            buf = r.read(64 * 1024 * 1024)
            if not buf:
                break
            lines += buf.count(b"\n")
            nbytes += len(buf)
    consumed = fh.tell()
import os
print({"lines": lines, "decompressed_bytes": nbytes, "compressed_bytes_consumed": consumed,
       "compressed_size": os.path.getsize(path), "seconds": round(time.time() - t0, 1)})
