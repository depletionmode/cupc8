# Card notch: current artifact audit (2026-09-28)

`python3 tools/notch_stack_current.py` validates each of the seven current
`build/hw/<board>/evidence.json` receipts, compares the PCB to the exported
fabrication files, and measures the key-adjacent copper pads against the
plotted Edge.Cuts notch walls. The source is the current per-board PCB and
Gerber pair; this is a nominal plotted-geometry check, not a finished-board
measurement.

| Cards | Pad centres | Pad width | Plotted notch | Clearance on A/B faces |
| --- | ---: | ---: | ---: | ---: |
| CPU, GPU, IO, storage, Wi-Fi, e-ink | 10.00 / 13.00 mm | 0.70 mm | 1.90 mm | 0.20 mm on each side |
| System | 21.50 / 24.50 mm | 0.70 mm | 1.90 mm | 0.20 mm on each side |

All seven fail the project's 0.30 mm nominal notch-to-copper rule by
0.10 mm per side. The 3.00 mm adjacent-finger pitch and symmetric geometry
make the result common to both faces. Shifting the notch changes which side
is worse without increasing the sum of the two clearances.

`hw/mech/fit.py` records a 3.00 ± 0.01 mm finger centre pitch, 1.90 ± 0.06 mm
notch, and 0.70 ± 0.05 mm finger width. At the most favorable allowed pitch
(3.01 mm), smallest notch (1.84 mm), and narrowest finger (0.65 mm), the
largest *simultaneous* centered clearance is `(3.01 - 1.84 - 0.65)/2 = 0.26`
mm. A 0.30 mm clearance on both sides requires at least a 3.09 mm centre gap
even at those favorable dimensions. Thus a notch-only or finger-width-only
change at the current centres cannot meet the project rule across this model's
allowed dimensions. These are necessary geometric bounds; insertion clearance,
contact wipe, and manufacturing offsets could impose stricter conditions.

The repository's UMAX 3183 source drawing (`hw/datasheets/C404113_UMAX-3183-10200P1T.pdf`,
page 1) labels the key rib 1.78 ± 0.05 mm. The Sofng x4 source drawing
(`hw/datasheets/C19188869_PCIE-64P11L.pdf`, page 1) labels a 1.78 mm rib and
also prints a general `.XX ± 0.15` tolerance; the drawing does not settle
whether that general tolerance applies to the rib. Neither PDF here gives a
qualified worst-case rib-to-contact-tip location and wipe envelope across all
selected socket variants. The PDFs therefore do not qualify a shifted/narrow
pad design or a socket substitution.

To close the gate, obtain the chosen x1/x4/x8 socket manufacturers' controlled
drawings or written dimensions for rib width and position, contact-tip width
and position, required minimum wipe, and insertion allowance; obtain the fab's
finished routed-notch width/position and finger copper tolerances. Then revise
the finger centres and widths, footprint, and board plots together and run the
full stack at worst-case limits. The existing 0.65 mm pad / 0.08 mm outward
shift proposal reaches only 0.305 mm *nominal* clearance and has no tolerance
margin; it is a study case, not a release fix. A different qualified interconnect
is another possible design route. No canonical board source is changed by this
audit.

Focused checks run:

```text
python3 tools/notch_stack_current.py                 # 7/7 current receipts and export parity; each face 0.20 mm
python3 -m unittest test.hw.test_notch_stack_current  # 3 tests, OK
```

The synthetic regression exercises the present failure, notch offset, and the
fixed-pitch dimensional bound. Candidate counterexample catalogue command:
`python3 -m unittest test.hw.test_notch_stack_current`.
