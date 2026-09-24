#!/usr/bin/env python3
"""STO-002: the storage card's FAT images against a PC's FAT reader.

    fatcheck.py mkimg IMG
        a FAT16 volume as a PC formats it (mkfs.fat), with files a PC wrote
        (pyfatfs): PC.TXT, EMPTY.TXT, DELME.TXT
    fatcheck.py check IMG [EXPECT_DIR] [--absent NAME...] [--size NAME=BYTES...]
        every file in EXPECT_DIR is in the image's root with the same bytes,
        the --absent names are not, the --size files have that size, and
        fsck.fat finds nothing wrong

pyfatfs (pinned) lives in a venv under $CUPC8_SDK (~/.local/share/cupc8-sdk/pyfat),
made on first use.
"""
import os
import subprocess
import sys
import tempfile
import warnings

SDK = os.environ.get("CUPC8_SDK", os.path.expanduser("~/.local/share/cupc8-sdk"))
VENV = os.path.join(SDK, "pyfat")
PINS = ["pyfatfs==1.1.0", "fs==2.4.16", "setuptools<81"]


def ensure_pyfatfs():
    try:
        import pyfatfs  # noqa: F401
        return
    except ImportError:
        pass
    py = os.path.join(VENV, "bin", "python")
    if os.path.realpath(sys.prefix) == os.path.realpath(VENV):
        raise SystemExit("fatcheck: pyfatfs missing from " + VENV)
    if not os.path.exists(py):
        subprocess.run([sys.executable, "-m", "venv", VENV], check=True)
    if subprocess.run([py, "-c", "import pyfatfs"], capture_output=True).returncode:
        subprocess.run([py, "-m", "pip", "install", "-q", *PINS], check=True)
    os.execv(py, [py, *sys.argv])


def partition_offset(path):
    """byte offset of the FAT volume: 0 for a bare volume, else the first MBR partition's"""
    with open(path, "rb") as f:
        s = f.read(512)
    if s[510:512] != b"\x55\xaa":
        raise SystemExit("fatcheck: %s: no boot signature" % path)
    # a volume boot record starts with a jump; an MBR (FatFs, a PC's card) does not
    if s[0] in (0xEB, 0xE9) and s[11:13] == b"\x00\x02":
        return 0
    lba = int.from_bytes(s[446 + 8:446 + 12], "little")
    return lba * 512


def open_fs(path):
    warnings.simplefilter("ignore")
    from pyfatfs.PyFatFS import PyFatFS
    return PyFatFS(path, offset=partition_offset(path), preserve_case=False)


def fsck(path):
    off = partition_offset(path)
    with open(path, "rb") as f:
        f.seek(off)
        vol = f.read()
    with tempfile.NamedTemporaryFile(suffix=".img") as t:
        t.write(vol)
        t.flush()
        r = subprocess.run(["fsck.fat", "-n", t.name], capture_output=True, text=True)
    out = r.stdout + r.stderr
    # -n reports what it would change; a clean volume has no such lines
    bad = [l for l in out.splitlines() if l and not l.startswith(("fsck.fat", "Checking", "/tmp", "Leaving"))
           and "files," not in l and "clusters" not in l]
    return r.returncode, bad, out


def mkimg(path):
    if os.path.exists(path):
        os.unlink(path)
    subprocess.run(["mkfs.fat", "-C", "-F", "16", "-s", "1", "-n", "PCCARD", path, "4096"], check=True, capture_output=True)
    fs = open_fs(path)
    fs.writebytes("/PC.TXT", b'10 PRINT "WRITTEN ON A PC"\r\n' * 40)
    fs.writebytes("/EMPTY.TXT", b"")
    fs.writebytes("/DELME.TXT", b"delete me\r\n")
    fs.close()
    print("fatcheck: %s: PC.TXT, EMPTY.TXT, DELME.TXT" % path)


def check(path, expect_dir, absent, sizes):
    fails = []
    fs = open_fs(path)
    names = {n.upper() for n in fs.listdir("/")}
    if expect_dir:
        for name in sorted(os.listdir(expect_dir)):
            want = open(os.path.join(expect_dir, name), "rb").read()
            if name.upper() not in names:
                fails.append("%s missing" % name)
                continue
            got = fs.readbytes("/" + name)
            if got != want:
                fails.append("%s: %d bytes, want %d%s" % (name, len(got), len(want),
                             "" if len(got) != len(want) else " (contents differ)"))
    for name in absent:
        if name.upper() in names:
            fails.append("%s should be deleted" % name)
    for name, size in sizes:
        if name.upper() not in names:
            fails.append("%s missing" % name)
        elif fs.getsize("/" + name) != size:
            fails.append("%s: %d bytes, want %d" % (name, fs.getsize("/" + name), size))
    fs.close()
    rc, bad, out = fsck(path)
    if rc or bad:
        fails.append("fsck.fat: " + (" / ".join(bad) or out.strip()))
    for f in fails:
        print("fatcheck: FAIL %s: %s" % (path, f))
    print("fatcheck: %s: %d files, %s" % (path, len(names), "ok" if not fails else "%d failures" % len(fails)))
    return 1 if fails else 0


def main():
    ensure_pyfatfs()
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "mkimg":
        mkimg(args[1])
        return 0
    if len(args) >= 2 and args[0] == "check":
        path, rest = args[1], args[2:]
        expect = None
        if rest and not rest[0].startswith("--"):
            expect, rest = rest[0], rest[1:]
        absent, sizes, mode = [], [], None
        for a in rest:
            if a in ("--absent", "--size"):
                mode = a
            elif mode == "--absent":
                absent.append(a)
            elif mode == "--size":
                n, s = a.split("=")
                sizes.append((n, int(s)))
        return check(path, expect, absent, sizes)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
