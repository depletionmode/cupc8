#!/usr/bin/env python3
"""Build a CUPC/8 ROM image (doc/hardware/memory-map.md, "ROM image layout").

  mkrom.py boot.bin kernel.bin -o rom.bin [--load 0x1000] [--entry 0x1000]
  mkrom.py --info rom.bin

  $00000  boot ROM (max 2 KB)
  $00800  kernel header (16 bytes)
  $00810  kernel body
  rest    erased ($ff)
"""
import argparse
import struct
import sys

BOOT_MAX = 0x800
HDR_OFF = 0x800
BODY_OFF = 0x810
ROM_SIZE = 512 * 1024
MAGIC = b"CUP8"
RAM_TOP = 0xE000


def header(load, length, entry, body_sum):
    h = bytearray(16)
    h[0:4] = MAGIC
    h[4] = 1                                    # header version
    h[5] = 0                                    # flags
    struct.pack_into("<HHH", h, 6, load, length, entry)
    h[12] = body_sum
    h[13] = (-sum(h[0:13])) & 0xFF              # bytes 0..13 sum to 0
    return bytes(h)


def build(boot, kernel, load, entry):
    if len(boot) > BOOT_MAX:
        sys.exit("boot ROM is %d bytes, max %d" % (len(boot), BOOT_MAX))
    if load + len(kernel) > RAM_TOP:
        sys.exit("kernel does not fit: $%04x + %d bytes runs past $%04x" %
                 (load, len(kernel), RAM_TOP))
    rom = bytearray(b"\xff" * ROM_SIZE)
    rom[0:len(boot)] = boot
    body_sum = sum(kernel) & 0xFF
    rom[HDR_OFF:HDR_OFF + 16] = header(load, len(kernel), entry, body_sum)
    rom[BODY_OFF:BODY_OFF + len(kernel)] = kernel
    return bytes(rom)


def info(rom):
    h = rom[HDR_OFF:HDR_OFF + 16]
    load, length, entry = struct.unpack_from("<HHH", h, 6)
    ok_magic = h[0:4] == MAGIC
    ok_hdr = sum(h[0:14]) & 0xFF == 0
    body = rom[BODY_OFF:BODY_OFF + length]
    ok_body = (sum(body) & 0xFF) == h[12]
    print("boot ROM : %d bytes used of %d" % (len(rom[:BOOT_MAX].rstrip(b"\xff")), BOOT_MAX))
    print("magic    : %s (%s)" % (h[0:4].decode("latin1"), "ok" if ok_magic else "BAD"))
    print("version  : %d" % h[4])
    print("load     : $%04x" % load)
    print("length   : %d bytes (ends at $%04x)" % (length, load + length))
    print("entry    : $%04x" % entry)
    print("checksums: header %s, body %s" % ("ok" if ok_hdr else "BAD", "ok" if ok_body else "BAD"))
    return 0 if (ok_magic and ok_hdr and ok_body) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", help="boot.bin kernel.bin, or a rom with --info")
    ap.add_argument("-o", "--out")
    ap.add_argument("--load", type=lambda v: int(v, 0), default=0x1000)
    ap.add_argument("--entry", type=lambda v: int(v, 0), default=0x1000)
    ap.add_argument("--info", action="store_true")
    args = ap.parse_args()

    if args.info:
        return info(open(args.files[0], "rb").read())
    if len(args.files) != 2 or not args.out:
        ap.error("need boot.bin kernel.bin -o rom.bin")
    rom = build(open(args.files[0], "rb").read(), open(args.files[1], "rb").read(),
                args.load, args.entry)
    with open(args.out, "wb") as f:
        f.write(rom)
    print("wrote %s (%d KB)" % (args.out, len(rom) // 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
