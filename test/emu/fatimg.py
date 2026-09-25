#!/usr/bin/env python3
"""The host's FAT reader for the storage card tests: FAT images made, filled
and checked on the host with pyfatfs (tools/fetch_sdks.sh puts it in a
pinned venv, $CUPC8_SDK/pyfat), independently of the card's FatFs.

    fatimg.py mkfs IMG SIZE_MB {12|16|32}
    fatimg.py put IMG NAME FILE          (FILE - : stdin)
    fatimg.py get IMG NAME               (the bytes on stdout)
    fatimg.py ls IMG                     (JSON: [[name, size], ...] of the root)
    fatimg.py fill IMG NAME              (one file as large as the free space allows)
    fatimg.py check IMG                  (every file readable, FATs agree; fsck.fat -n too if installed)

Run with $CUPC8_SDK/pyfat/bin/python (test/emu/test_storage.mjs does).
"""

import json
import os
import shutil
import subprocess
import sys
import warnings

warnings.filterwarnings("ignore")
from pyfatfs.PyFat import PyFat  # noqa: E402
from pyfatfs.PyFatFS import PyFatFS  # noqa: E402


def mkfs(img, mb, bits):
    """as a PC formats a card: mkfs.fat (dosfstools) if installed, else pyfatfs"""
    with open(img, "wb") as f:
        f.truncate(int(mb) << 20)
    if shutil.which("mkfs.fat"):
        subprocess.run(["mkfs.fat", "-F", bits, "-n", "CUPC8", img], check=True, capture_output=True)
        return
    kind = {"12": PyFat.FAT_TYPE_FAT12, "16": PyFat.FAT_TYPE_FAT16, "32": PyFat.FAT_TYPE_FAT32}[bits]
    pf = PyFat()
    pf.mkfs(img, kind, size=int(mb) << 20, label="CUPC8")
    pf.close()


def main():
    cmd, img = sys.argv[1], sys.argv[2]
    if cmd == "mkfs":
        mkfs(img, sys.argv[3], sys.argv[4])
        return 0
    fs = PyFatFS(img, read_only=cmd in ("get", "ls", "check"))
    try:
        if cmd == "put":
            data = sys.stdin.buffer.read() if sys.argv[4] == "-" else open(sys.argv[4], "rb").read()
            fs.writebytes("/" + sys.argv[3], data)
        elif cmd == "get":
            sys.stdout.buffer.write(fs.readbytes("/" + sys.argv[3]))
        elif cmd == "ls":
            print(json.dumps([[n, fs.getsize("/" + n)] for n in sorted(fs.listdir("/"))]))
        elif cmd == "fill":
            # one file over every free cluster, counted from the BPB (pyfatfs's
            # FAT table can be longer than the volume's cluster count)
            pf = fs.fs
            b = pf.bpb_header
            fatsz = b["BPB_FATSz16"] or b["BPB_FATSz32"]
            tot = b["BPB_TotSec16"] or b["BPB_TotSec32"]
            root = (b["BPB_RootEntCnt"] * 32 + b["BPB_BytsPerSec"] - 1) // b["BPB_BytsPerSec"]
            data = tot - b["BPB_RsvdSecCnt"] - b["BPB_NumFATs"] * fatsz - root
            clusters = data // b["BPB_SecPerClus"]
            free = sum(1 for c in range(2, clusters + 2) if pf.fat[c] == 0)
            fs.writebytes("/" + sys.argv[3], b"\xaa" * (free * pf.bytes_per_cluster))
            print(free * pf.bytes_per_cluster)
        elif cmd == "check":
            for n in fs.listdir("/"):
                if fs.isfile("/" + n):
                    fs.readbytes("/" + n)
            print("ok")
    finally:
        fs.close()
    if cmd == "check" and shutil.which("fsck.fat"):
        r = subprocess.run(["fsck.fat", "-n", img], capture_output=True, text=True)
        # FAT32's FSInfo free count is only a hint (and pyfatfs does not keep
        # it), so that one finding is not a fault; anything else is
        lines = [l for l in (r.stdout + r.stderr).splitlines()
                 if l.strip() and not l.startswith("fsck.fat ") and "Leaving filesystem unchanged" not in l
                 and not l.startswith(os.path.basename(img) + ":") and not l.startswith(img + ":")
                 and "Free cluster summary wrong" not in l and "Auto-correcting" not in l]
        if r.returncode != 0 and lines:
            print("\n".join(lines))
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
