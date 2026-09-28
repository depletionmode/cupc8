# Printable board review packet

`tools/board_review_packet.py` produces an unsigned A4 PDF with two pages per
board: top and bottom PCB renders, then the Top CPL placement overlay. Each
page names the board and view, says review is pending, and prints the SHA-256
of the board's `evidence.json` receipt. The render and overlay pages also print
their source PNG hashes. The overlays are regenerated from the verified PCB,
CPL, and edge plot into a sibling directory of the PDF. Neither the PDF nor
these overlays are a human approval or a `cpl-review.json` receipt.

From the repository root, after all eight board builds finish:

```sh
python3 tools/board_review_packet.py --output build/review-packet/cupc8-boards.pdf
```

The command validates every requested board with `boardevidence.validate`
before it creates output. A missing, stale, or changed receipt or artifact
stops the run. The default board list is main, CPU, GPU, e-ink, I/O, storage,
Wi-Fi, and system. During a rebuild, `--boards main cpu gpu io storage wifi`
can produce a partial packet for only those boards with valid receipts.

The script needs Python Pillow, KiCad's `pcbnew` Python module and `kicad-cli`,
and `rsvg-convert`, which are also used by the overlay renderer. `--repo-root`
and `--build-root` let an isolated checkout use the canonical source and build
directory without changing any board build outputs.
