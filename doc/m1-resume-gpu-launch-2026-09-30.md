# GPU GC-007 local launch repair, 2026-09-30

The source repair in `hw/boards/gpu.py` is integrated after scratch geometry and field checks. **Canonical receipt-bound GC-007 remains pending** until the root's sequential board queue regenerates GPU. No routing job was started by this worker.

## Bounded changes

- Move the D1 chip-side bend 0.5 mm away from the resistor-array pad copper.
- Move the D1/D0/clock connector-side departure bends away from the array pads.
- Move U6.3's existing 0.6/0.3 mm GND via 0.21 mm towards the ESD package, preserving its connection. Guard its expected fan-out geometry.
- Shift the adjacent D0N and CKP launch corners 0.05 mm apart to retain the unchanged 0.2 mm clearance.
- Narrow only the first 0.25 mm of each of the six D1/D0/clock departure diagonals from 0.25 to 0.175 mm, symmetrically. The remaining copper uses the previous width; the existing minimum is 0.15 mm.

Existing resistor values, limits, footprint libraries, board tools and other card sources are unchanged by this repair.

## Evidence

All scratch artifacts are in `/tmp/cupc8-gc007-local`.

1. Candidate12 fixed the parked candidate9 clearance problem: zero errors, warnings and unconnected items in `candidate12-drc-all.json`. Its field report still had one short failing sample per D1/D0/clock (80.45/81.38/82.56 ohm).
2. Candidate13 added the six short narrow launches. `candidate13-drc.json` passes full `--severity-all --all-track-errors`, zero violations and zero unconnected items.
3. `candidate13-gc007.json` has **no electrical failures**. Its sole failure is deliberately `board receipt not checked (--no-evidence)`, so it is not a canonical pass.

| Lane | Trace lower-bound range, ohm | Highest upper estimate, ohm | Below/above/undecided, mm | Skew, ps |
| --- | --- | --- | --- | --- |
| D2 | 96.18–103.98 | 105.16 | 0 / 0 / 0 | 0.286 |
| D1 | 90.23–108.58 | 109.77 | 0 / 0 / 0 | 0.676 |
| D0 | 90.98–108.75 | 109.94 | 0 / 0 / 0 | 0.144 |
| Clock | 92.25–108.64 | 109.83 | 0 / 0 / 0 | 4.112 |

The nominal ESD loss, line loss and swing checks pass; the existing doubled typical ESD-capacitance sensitivity remains a diagnostic. Impedance margins are small and require the canonical field check, without changing the 90–110 ohm criterion.

4. To exclude improvement solely from changed sample placement, `original-failing-cuts.py` independently solves the three original failing XY cuts on candidate13. Lower/upper results: D1 90.243/91.224, D0 91.152/92.144, clock 92.332/93.336 ohm (`original-failing-cuts.json`).
5. `gpu-candidate13.py` generates the changes through the actual board source. `source-preroute.py` runs the regular schematic/ERC/netlist/board generation, then deliberately stops at the autoroute function before any Freerouting invocation. All source guards pass (`source-preroute.log`).
6. `verify-generated.py` compares all 138 generated TMDS/HD segments with candidate13: widths/layers/nets match, endpoints differ by at most 1 nm from Python-to-KiCad coordinate conversion. It then uses that same source to replace only TMDS/HD copper plus the guarded GND escape on the fresh root GPU copper. Full DRC passes zero warnings/errors/unconnected items (`source-generated-on-fresh-drc.json`). This modified scratch board has no manufacturing receipt.

The source before integration is preserved as `gpu-before-integration.py`. Candidate13 scripts, input hashes, frozen source files, field reports and development boards are retained. The root owns the next full GPU pipeline and current receipt; run the canonical GC-007 field check on that exact output afterward.
