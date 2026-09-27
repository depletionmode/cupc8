#!/usr/bin/env python3
"""BOOT-004: distinguish an erased BASIC slot from a damaged header."""
import contextlib
import io
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import mkrom


def inspect(image):
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        status = mkrom.info(image)
    return status, output.getvalue()


kernel = b"\x80"
plain = mkrom.build(b"", kernel, 0x1000, 0x1000)
status, output = inspect(plain)
assert status == 0 and "BASIC    : none" in output, "FAIL: erased BASIC slot rejected"

with_basic = mkrom.build(b"", kernel, 0x1000, 0x1000, b"\x01")
status, output = inspect(with_basic)
assert status == 0 and "BASIC    : ROM" in output, "FAIL: valid BASIC header rejected"

damaged = bytearray(with_basic)
header, _ = mkrom.basic_offsets(len(kernel))
damaged[header] = ord("X")
status, output = inspect(damaged)
assert status == 1 and "BASIC    : invalid header" in output, \
    "FAIL: corrupt BASIC header was treated as absent"
print("BOOT-004 BASIC header inspection: 3 checks passed")
