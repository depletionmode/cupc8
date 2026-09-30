# Fab waivers and hand checks

Written by people, not generated: `tools/fabready.py` copies this file into
`fab-readiness.md`. Every waiver says what the rule is, what we do instead,
why, and who decided.

## Waivers

| Rule | What we do | Why | Decided |
|---|---|---|---|
| PCIe CEM card-edge bevel 20° ± 5° (Fig. 6-3) | 30° bevel on every card | JLC offers only 30° or 45°; 30° is the nearest, and what JLC recommends for easy insertion. MECH-002 accepts exactly 30° as this waiver. | David, 2026-09-24 |
| "Every part is assembled by JLC" (milestone-1.md) | The Wi-Fi antenna lead (C709347) and SMA antenna (C1509156) are ordered from JLC loose and plugged in by hand | JLC does not assemble cable parts. Plugging an RF lead in is not soldering. | David (milestone-1.md, antenna row) |
| verification.md 3.3: a missing CPU card | Out of scope | A machine without its CPU card is broken hardware. | David, 2026-09-24 |
| verification.md 3.3: a card pulled while running | Out of scope | Cards are plugged or removed only with the power off (`slot.md`). | David, 2026-09-24 |
| `hw/power` current budgets: 10 % margin (POW-006) | POW-006 B5, the machine on a 1.5 A source (radio off, SD writes refused, SD reading, a 500 mA keyboard), needs 5 %. It is 1.383 A, 7.8 % under 1.5 A. | Every tolerance is at its worst at once (vSafe5V min, the Type-C cable's full drop, every resistance at its max, every load at its max), and the case still fits the source class. The full machine is specified on a 3.0 A source. | David, 2026-09-25 |
| YC-007 system-card USB impedance and D+/D- capacitance balance | Accept the existing routing for first articles only; retain the failed SI checks and test physical USB before a larger run | All 32 modeled cable cases and edge checks pass, but routed impedance and 19–26 % capacitance imbalance fail the design limits. Possible issue: failed enumeration, intermittent disconnects or unreliable transfers with some cables/hosts; a later board revision may be needed. See `first-article-plan.md`, system-card USB acceptance check. | David, 2026-09-30: "accept it for now and note it as a possible issue" |
| CC-007 / MB-007 CPU-bus input voltage stress | First articles use CPU RN1–RN8 = 68 ohm (C52984) and main R21–R34 = 56 ohm (C25196); retain the failed electrical checks | The series-resistor sweep did not find a pair that meets every normal-corner limit. Residual overshoot remains a first-run risk; acceptance does not guarantee FPGA input reliability. Measure the receiving FPGA pins in first-article checks F5–F8 before a larger run. This acceptance does not cover slot MISO. See `m1-live-status.md`, decisions of 2026-09-29. | David, 2026-09-29 |
| IC-007 IO-card full-speed USB impedance | Accept the routed pair for first articles; retain the failed impedance check and measure/test physical USB | The routed impedance lower bound exceeds 99 ohm over about 13.5/15.6 mm; other modeled subchecks pass. Real keyboard enumeration and transfers remain first-article requirements. Acceptance is not an electrical pass. | David, 2026-09-29 |
| Project 0.30 mm copper-to-cut clearance at the card key notch | Exactly A11/A12/B11/B12 against their matching notch cuts use 0.20 mm; all other copper/cuts keep 0.30 mm | Preserve standard PCIe CEM finger/notch geometry. Order high-precision 0.10 mm outline tolerance, Confirm Production File and the do-not-trim note. On at least two boards of every card type, MECH-101 requires a measured notch-wall-to-finger gap >= 0.10 mm, intact fingers and correct socket fit/contact continuity. See `card-notch-decision-applied-20260928.md` and `first-article-plan.md`. | David, 2026-09-28 |
| RP2040 exposed-pad open via | Leave the single U1.57 GND via in the paste gutter open on GPU, IO, storage, e-ink and system cards; no paid plugging | The accepted via is distinct from the other via-in-pad defects, which require design fixes. Inspect first-article exposed-pad soldering; a dry joint or voiding requires plugging on the next run. | David, 2026-09-29 |
| GPU RP2040 datasheet clock limit | Exactly 252 MHz with VREG 1.20 V is a declared M1 requirement | PicoDVI uses this operating point; silicon margin varies. GC-102 requires every GPU card used to produce DVI for at least one hour near 40 C ambient without glitches, dropouts or lockups. This is not a general overclock waiver. See `power.md` and `first-article-plan.md`. | David, 2026-09-28 |
| Co-simulation coverage of 50 explicitly named boundary nets | Preserve the fixed-name waivers in `hw/cosim/coverage.py` and their mutation regressions | Test access/passive loops: 12 nets; card control: 18; unused firmware/header: 12; ESP pins: 8. First articles verify slot reset/program controls (MB-106), ESP boot/UART/LED behavior (WC-101), and GPU HPD plus DDC/EDID with a real monitor (GC-105). Added or changed nets require a new coverage decision. | David, 2026-09-29 |
| IO boost vendor-model convergence at maximum switch current | Permit the documented TPS61023 numerical retry in 5 mA steps where that model does not converge | Binding T5/T6 stress cases still run at the actual 647.4 mA bound without retry. This is a numerical workaround, not a lower physical current limit; measure the fitted TPS2553 current limit in first articles. See `power.md` and `m1-live-status.md`. | David, 2026-09-29 |

These decisions authorize the documented first-article scope. Failed electrical
rows remain failed. Slot MISO voltage stress and sustained-fault copper heating
have no waiver. The current M1 load is the reset-qualification target; hypothetical
additional fully loaded future slots are advisory (David, 2026-09-30).

## Hand checks (to do before ordering, with a date)

| Check | Done |
|---|---|
| 4.9: every board's CPL rendered over its Gerbers, each part's pin 1 and rotation checked by eye (BRD-001 checks rotations against JLC's footprints; this is the backstop) | |
| JLC's order page: each board's options match its `fab/order.json` (layers, 1.6 mm, ENIG, ENIG gold fingers and 30° bevel on cards, Confirm Production File, the do-not-trim note, impedance control on 4- and 6-layer boards) | |
| The antenna lead is SMA female (jack) and the antenna SMA male, not RP-SMA | |
| Parts with low stock reserved in the JLC parts inventory (the ROM chips, the FPGAs: `parts.md`, Risks) | |
