#!/usr/bin/env python3
"""SIM-013: examples/edit (EDIT.PRG), the full-screen text editor, on the simulator.

Builds EDIT.PRG, puts it on a FAT image with tools/fatcheck.py, runs it with
exec and types at it with --type; reads the screen with --dump-text and the
files as a PC reads them (fatcheck check):
  - a new file: typed, a line end, up and End, F2: saved as CR LF text;
  - a PC's file (CR LF): opened, edited mid-line with Home, Down and Delete,
    the status line (name, *, line, column) and the rows on the screen; not
    saved, so the file is as it was;
  - Esc with unsaved changes asks, a second Esc quits (nothing written);
  - 100 lines: PgDn twice scrolls the screen; a 100-character line: End
    scrolls it sideways;
  - a file over 16 KB is refused, back at the prompt;
  - the same session on the e-ink cards (eink, eink750): saved, on screen.

    python3 test/sim/test_edit.py
"""

import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_cli  # noqa: E402  (its sim build and runner)

ROOT = test_cli.ROOT
failures = 0


def check(name, cond, detail=""):
    global failures
    if cond:
        print("ok: " + name)
    else:
        failures += 1
        print("FAIL: " + name + (("\n" + detail) if detail else ""))


def fatcheck(*args):
    return subprocess.run([sys.executable, os.path.join(ROOT, "tools", "fatcheck.py"), *args],
                          capture_output=True, text=True)


def card(work, name, files):
    """A blank FAT image with EDIT.PRG and files ({NAME: bytes})."""
    img = os.path.join(work, name)
    fatcheck("blank", img, "4096")
    fatcheck("put", img, "EDIT.PRG", os.path.join(work, "EDIT.PRG"))
    for fname, data in files.items():
        src = os.path.join(work, fname + ".src")
        open(src, "wb").write(data)
        fatcheck("put", img, fname, src)
    return img


def holds(work, img, fname, data):
    """The image has fname with exactly these bytes (and fsck is clean)."""
    expect = tempfile.mkdtemp(dir=work)
    open(os.path.join(expect, fname), "wb").write(data)
    r = fatcheck("check", img, expect)
    return r.returncode == 0, r.stdout + r.stderr


def edit(slots, img, keys):
    """exec EDIT.PRG on these slot cards, then keys; the screen's rows at the end."""
    text, out = test_cli.sim("--slots", slots, "--sd", img, '--type:exec "EDIT.PRG"\\n' + keys)
    return text.split("\n"), out


def main():
    test_cli.build()
    work = tempfile.mkdtemp(prefix="sim-edit-")
    prg = os.path.join(work, "EDIT.PRG")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "mkprg.py"),
                        os.path.join(ROOT, "examples", "edit", "edit.s"), "-o", prg],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("mkprg: " + r.stdout + r.stderr)
    hdmi = "hdmi,io,storage"

    # a new file: typed, saved
    img = card(work, "new.img", {})
    rows, out = edit(hdmi, img, "NOTES.TXT\\nhello world\\nsecond{UP}{END}!{F2}")
    check("new file: the status line after F2", rows[0].startswith(" EDIT NOTES.TXT  line 1 col 13  saved"), "\n".join(rows) + out)
    check("new file: the text on rows 1-2", rows[1:3] == ["hello world!", "second"], "\n".join(rows))
    check("new file: the keys on row 29", rows[29].startswith(" F2 save   Esc quit"), "\n".join(rows))
    ok, detail = holds(work, img, "NOTES.TXT", b"hello world!\r\nsecond")
    check("new file: saved as CR LF text", ok, detail)

    # a PC's file: edited, not saved
    pc = b"first line\r\nsecond line\r\nthird line\r\n"
    img = card(work, "pc.img", {"PC.TXT": pc})
    rows, out = edit(hdmi, img, "pc.txt\\n{DOWN}{HOME}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}{DEL}X{RIGHT}{DOWN}\\x08")
    check("PC's file: the status line (*, line 3, column 2)",
          rows[0].startswith(" EDIT pc.txt *  line 3 col 2"), "\n".join(rows) + out)
    check("PC's file: the edited rows", rows[1:5] == ["first line", "Xline", "tird line", ""], "\n".join(rows))
    ok, detail = holds(work, img, "PC.TXT", pc)
    check("PC's file: not saved, as it was", ok, detail)

    # Esc with unsaved changes: asks, then quits; nothing written
    img = card(work, "esc.img", {})
    rows, out = edit(hdmi, img, "NEW.TXT\\nabc\\e")
    check("Esc with changes asks", "unsaved! Esc quits, F2 saves" in rows[0], "\n".join(rows) + out)
    rows, out = edit(hdmi, img, "NEW.TXT\\nabc\\e\\e")
    check("a second Esc quits to the prompt", any(r.startswith(">>") for r in rows) and "EDIT" not in rows[0],
          "\n".join(rows) + out)
    r = fatcheck("check", img, tempfile.mkdtemp(dir=work), "--absent", "NEW.TXT")
    check("... and wrote nothing", r.returncode == 0, r.stdout + r.stderr)

    # scrolling: 100 lines, and a line of 100 characters
    lines = b"".join(b"line %d\r\n" % i for i in range(1, 101))
    wide = bytes(ord("a") + i % 26 for i in range(100)) + b"\r\n"
    img = card(work, "long.img", {"LONG.TXT": lines, "WIDE.TXT": wide})
    rows, out = edit(hdmi, img, "long.txt\\n{PGDN}{PGDN}")
    check("PgDn twice: line 55", rows[0].startswith(" EDIT long.txt  line 55 col 1"), "\n".join(rows) + out)
    check("... on the last row, line 28 on the first", rows[1] == "line 28" and rows[28] == "line 55", "\n".join(rows))
    rows, out = edit(hdmi, img, "long.txt\\n{PGDN}{PGDN}{PGUP}")
    check("PgUp: line 28, the screen stays", rows[0].startswith(" EDIT long.txt  line 28 col 1") and rows[1] == "line 28",
          "\n".join(rows) + out)
    rows, out = edit(hdmi, img, "wide.txt\\n{END}")
    check("End on a 100-character line: column 101, scrolled 21 sideways",
          rows[0].startswith(" EDIT wide.txt  line 1 col 101") and rows[1] == wide[21:100].decode(), "\n".join(rows) + out)

    # a file over 16 KB is refused
    img = card(work, "big.img", {"BIG.TXT": b"x" * 17000})
    rows, out = edit(hdmi, img, "big.txt\\n")
    check("a file over 16 KB is refused", "edit: the file is bigger than 16 KB" in rows, "\n".join(rows) + out)

    # the e-ink cards: the same editor
    for kind in ("eink", "eink750"):
        img = card(work, kind + ".img", {})
        rows, out = edit("%s,io,storage" % kind, img, "INK.TXT\\non paper\\nline two{F2}")
        check(kind + ": the editor on the panel",
              rows[0].startswith(" EDIT INK.TXT  line 2 col 9  saved") and rows[1:3] == ["on paper", "line two"],
              "\n".join(rows) + out)
        ok, detail = holds(work, img, "INK.TXT", b"on paper\r\nline two")
        check(kind + ": saved", ok, detail)

    shutil.rmtree(work, True)
    if failures:
        print("FAILED %d check(s)" % failures)
        sys.exit(1)
    print("ALL EDIT CHECKS PASSED")


if __name__ == "__main__":
    main()
