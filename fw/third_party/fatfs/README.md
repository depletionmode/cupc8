# FatFs R0.15a (ChaN), vendored

The storage card's file system (`doc/hardware/storage-card.md`), used by
`fw/storage/core`.

- Source: <http://elm-chan.org/fsw/ff/arc/ff15a.zip>, sha256
  `74737b1cafa1a67a3f722dd0d1a44767c5b54d37b6300ad3825a904cbe88fc3c`.
- Files: `ff.c`, `ff.h`, `diskio.h`, `ffconf.h`, `00readme.txt`,
  `00history.txt` from `source/`, and `LICENSE.txt` (a 1-clause BSD-style
  licence). `diskio.c` is ours (`fw/storage/core/diskio.c`); `ffunicode.c`
  and `ffsystem.c` are not needed (no LFN, no RTOS).
- Unmodified except `ffconf.h`:
  - `FF_USE_MKFS 1`: the host tests and tools format images (the linker drops
    it from the card firmware, which never formats);
  - `FF_CODE_PAGE 437`: US, ASCII names;
  - `FF_FS_NORTC 1`, 2026-01-01: the card has no clock;
  - `FF_FS_LOCK 5`: the 4 file handles and the directory scan, so a file
    cannot be open for write and read at once.
  - LFN stays off (8.3 names), `FF_FS_REENTRANT 0`: only one core runs FatFs.
