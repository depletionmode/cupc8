# Filled-region and silkscreen text evidence — 2026-09-28

`tools/fab_neck_coverage.py` reads the current receipt-bound copper and
silkscreen Gerbers. It runs the existing plotted minimum-width and neck
witness checks, then gives an exact pass only to a simple, isolated,
orthogonal filled region whose scanline span meets the board's width rule.
Regions with holes, repaired contours, nonorthogonal edges, or touching ink
are explicitly deferred. `--require-complete` exits nonzero if any region is
deferred; it is a release gate, while the default command is diagnostic.

| Board | Copper filled regions | Silk filled regions | Exact isolated passes | Deferred |
| --- | ---: | ---: | ---: | ---: |
| main | 27 | 22 | 0 | 49 |
| cpu | 28 | 21 | 0 | 49 |
| gpu | 16 | 26 | 0 | 42 |
| io | 18 | 23 | 0 | 41 |
| storage | 18 | 24 | 0 | 42 |
| wifi | 21 | 20 | 0 | 41 |
| eink | 21 | 24 | 0 | 45 |
| system | 26 | 24 | 0 | 50 |

All eight diagnostic runs completed. `python3 tools/fab_neck_coverage.py
main --require-complete` exits 1 with `filled-region proof incomplete:
main`. The synthetic regression accepts an isolated orthogonal region at the
0.100 mm rule, rejects an 0.080 mm neck on copper and silkscreen, and defers
a wide sloped region. Run `python3 test/hw/test_fab_neck_coverage.py`.
These are partial width proofs; zero current regions qualify for an exact
isolated pass. The existing witness checks may still find a definite narrow
neck in a deferred region, but passing those witnesses is not a complete
minimum-width proof.

For silkscreen text, the existing `hw/tools/silktextaudit.py` was rerun on all
eight current receipts and compared their Gerbers with a fresh export. Its
reports are in `build/hw/silk-text-current/` outside the receipt-owned board
directories. Each board's source minimum is 0.8 mm, and the source inventory
passes: main 369 visible text objects, CPU 53, GPU 57, IO 57, storage 47,
Wi-Fi 28, e-ink 59, system 59. The reports bind each board receipt, PCB, and
both silkscreen Gerber hashes. Gerber operations do not identify which strokes
are text or which strokes form a glyph, so these source-backed heights are not
an independent plotted text-height proof. The final fabrication gate remains
red for that reason, as well as the deferred filled-region widths.

The seven card notches still fail the 0.300 mm copper-to-edge rule at
0.200 mm. All CPL reviews remain unsigned and require per-designator human
placement, pin-one, polarity and rotation review.
