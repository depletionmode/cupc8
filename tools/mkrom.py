#!/usr/bin/env python3
"""Build a CUPC/8 ROM image (doc/hardware/memory-map.md, "ROM image layout").

  mkrom.py boot.bin kernel.bin [--basic BASIC.PRG] -o rom.bin [--load 0x1000] [--entry 0x1000]
  mkrom.py --info rom.bin

  $00000  boot ROM (max 2 KB)
  $00800  kernel header (16 bytes)
  $00810  kernel body (to $07fff at most)
  $08000  BASIC's header (16 bytes, as the kernel's: load and entry $7000)
  $08800  BASIC's body (basic/build.sh's BASIC.PRG without its "C8P" header),
          then 0s to a 256-byte boundary (the kernel copies whole pages and
          sums them)
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
KERNEL_END = 0x8000                             # the kernel body ends before BASIC's header
BASIC_HDR, BASIC_BODY = 0x8000, 0x8800
BASIC_BASE, BASIC_MAX = 0x7000, 0x5000          # $7000-$bfff: the BASIC program is at $c000


def header(load, length, entry, body_sum):
    h = bytearray(16)
    h[0:4] = MAGIC
    h[4] = 1                                    # header version
    h[5] = 0                                    # flags
    struct.pack_into("<HHH", h, 6, load, length, entry)
    h[12] = body_sum
    h[13] = (-sum(h[0:13])) & 0xFF              # bytes 0..13 sum to 0
    return bytes(h)


def build(boot, kernel, load, entry, basic=None):
    if len(boot) > BOOT_MAX:
        sys.exit("boot ROM is %d bytes, max %d" % (len(boot), BOOT_MAX))
    if load + len(kernel) > RAM_TOP:
        sys.exit("kernel does not fit: $%04x + %d bytes runs past $%04x" %
                 (load, len(kernel), RAM_TOP))
    if BODY_OFF + len(kernel) > KERNEL_END:
        sys.exit("kernel is %d bytes: past ROM $%05x, where BASIC starts" % (len(kernel), KERNEL_END))
    rom = bytearray(b"\xff" * ROM_SIZE)
    rom[0:len(boot)] = boot
    body_sum = sum(kernel) & 0xFF
    rom[HDR_OFF:HDR_OFF + 16] = header(load, len(kernel), entry, body_sum)
    rom[BODY_OFF:BODY_OFF + len(kernel)] = kernel
    if basic is not None:
        if basic[:4] == b"C8P\x01":
            basic = basic[4:]
        if not 0 < len(basic) <= BASIC_MAX:
            sys.exit("BASIC is %d bytes: 1 to %d fit $7000-$bfff" % (len(basic), BASIC_MAX))
        rom[BASIC_HDR:BASIC_HDR + 16] = header(BASIC_BASE, len(basic), BASIC_BASE, sum(basic) & 0xFF)
        padded = basic + bytes(-len(basic) % 256)
        rom[BASIC_BODY:BASIC_BODY + len(padded)] = padded
    return bytes(rom)


def info(rom):
    ok = show(rom, HDR_OFF, BODY_OFF, "kernel")
    if rom[BASIC_HDR:BASIC_HDR + 4] == MAGIC:
        ok = show(rom, BASIC_HDR, BASIC_BODY, "BASIC") and ok
    else:
        print("BASIC    : none (ROM $%05x)" % BASIC_HDR)
    return 0 if ok else 1


def show(rom, hdr_off, body_off, what):
    h = rom[hdr_off:hdr_off + 16]
    load, length, entry = struct.unpack_from("<HHH", h, 6)
    ok_magic = h[0:4] == MAGIC
    ok_hdr = sum(h[0:14]) & 0xFF == 0
    body = rom[body_off:body_off + length]
    ok_body = (sum(body) & 0xFF) == h[12]
    if what == "kernel":
        print("boot ROM : %d bytes used of %d" % (len(rom[:BOOT_MAX].rstrip(b"\xff")), BOOT_MAX))
    print("%-9s: ROM $%05x" % (what, hdr_off))
    print("magic    : %s (%s)" % (h[0:4].decode("latin1"), "ok" if ok_magic else "BAD"))
    print("version  : %d" % h[4])
    print("load     : $%04x" % load)
    print("length   : %d bytes (ends at $%04x)" % (length, load + length))
    print("entry    : $%04x" % entry)
    print("checksums: header %s, body %s" % ("ok" if ok_hdr else "BAD", "ok" if ok_body else "BAD"))
    return ok_magic and ok_hdr and ok_body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+", help="boot.bin kernel.bin, or a rom with --info")
    ap.add_argument("-o", "--out")
    ap.add_argument("--basic", help="BASIC.PRG (basic/build.sh) for ROM $08000")
    ap.add_argument("--load", type=lambda v: int(v, 0), default=0x1000)
    ap.add_argument("--entry", type=lambda v: int(v, 0), default=0x1000)
    ap.add_argument("--info", action="store_true")
    args = ap.parse_args()

    if args.info:
        return info(open(args.files[0], "rb").read())
    if len(args.files) != 2 or not args.out:
        ap.error("need boot.bin kernel.bin -o rom.bin")
    rom = build(open(args.files[0], "rb").read(), open(args.files[1], "rb").read(),
                args.load, args.entry, open(args.basic, "rb").read() if args.basic else None)
    with open(args.out, "wb") as f:
        f.write(rom)
    print("wrote %s (%d KB)" % (args.out, len(rom) // 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
