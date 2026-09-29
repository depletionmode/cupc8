# MB-005: deriving the input-loop requirement, 2026-09-28

**Status: decided (David, 2026-09-28): option 2.** `design.R_RECEPTACLE`
is now the ≤ 60 mΩ board-side loop at the hottest corner, with the ≤ 20 °C
rise rule at 3.213 A for every full-current conductor; the main board's
input corner was re-laid for it (`hw/boards/main_power_corner.py`) and
`hw/power/main_input_heat.py` checks the routed board. The analysis below
is kept as the record of the decision. The reproducible sweep is `hw/power/mb005_loop_sweep.py`, with its
test in `test/hw/test_mb005_loop_sweep.py`.

## Where the 20 mΩ enters

`hw/power/design.py` defines `R_RECEPTACLE = assume("main", "USB-C
receptacle + VBUS/GND copper to the fuse: <= 20 mOhm loop", 0.020)`. It is
an input assumption, not a figure derived from any load. It enters every
model through one path:

- `design.r_in(worst)` = cable (VBUS + GND) + `R_RECEPTACLE` + input PTC +
  eFuse RON + `R_5VSYS`. The worst corner uses vSafe5V min (4.75 V), the
  full Type-C cable IR drop (500 mV VBUS + 250 mV GND at 3 A, so 250 mΩ),
  PTC 30 mΩ max, eFuse 45 mΩ max and 5V_SYS copper 20 mΩ.
- `r_in` feeds POW-006 (`budget.chain`), and through it POW-001
  (`buck.py`), POW-003 (`buck.py wifi-card`), POW-007 (`boost.py`) and
  POW-008 (`hdmi.py`).
- POW-004 (`inrush.py`) uses cable + `R_RECEPTACLE` directly as the attach
  source impedance.
- `main_input_heat.py` (MB-005 I1) compares the routed positive copper alone
  against the same 20 mΩ.
- POW-005 (CC) and THM-001 do not use it.

## What the spec already counts in the cable

USB Type-C Cable and Connector Specification R2.0 (August 2019):

- **§4.4.1 IR Drop:** "The maximum allowable cable IR drop for ground … shall
  be 250 mV and for VBUS shall be 500 mV through the cable to the cable's
  maximum rated VBUS current capacity … **The IR drop includes the contact
  resistance of the mated plug and receptacles at each end.**"
  `design.CABLE_R_VBUS/GND` take exactly this limit at 3 A.
- **§3.7.8.1 LLCR:** 40 mΩ max initial and 50 mΩ max after environmental
  stress, per mated contact (the figure the connector decision note quotes).
- **Table 4-36:** the sink vRd windows "include consideration for the effect
  that the IR drop across the cable GND has on the voltage across the Sink's
  Rd".
- **Table 4-3, vSinkPD_min:** the spec's own sink budget is "750 mV = 500 mV
  + 250 mV (maximum IR drop)" below the source. vSafe5V at the source
  receptacle is 4.75–5.5 V (USB 2.0/3.2 via §4.4.2).

So the model's worst-case cable (250 mΩ loop at 3 A) **already includes our
receptacle's mated VBUS and GND contacts**. Adding 2 × USB-IF contact
maxima on top of `R_RECEPTACLE` counts them twice. The board-side term only
has to cover the receptacle terminations (solder and tails) and the
VBUS/GND copper to the fuse and eFuse. One caveat: I read this from the
§4.4.1 text. Figure 4-1, which shows the measurement points, did not
extract as text, so David should confirm it.

## The sweep: largest loop each existing check allows

Only `R_RECEPTACLE` moves. Every check keeps its own limit and its own
required margin (`need`). All values are at the hottest corner the model
uses: the worst corner's resistances are all maxima.

| Check | Limit (existing) | Loop at which it fails | At 20 mΩ |
|---|---|---|---|
| **POW-006 B5**: 1.5 A source, radio off | ≤ 1.5 A with 5 % margin (**waiver**, fab-waivers.md) | **89.8 mΩ** | 1.383 A, 7.8 % |
| POW-006 B10: IO card +5V | ≤ 0.80 A (slot.md), no margin | 121.2 mΩ | 0.750 A |
| POW-006 B10b: IO card vs slot PTC hold | 0.92 A, 10 % | 165.7 mΩ | 0.750 A |
| X1: PWR_HI with the GND offset a pull-up Rp sees (C4 + cable GND drop + half the loop, at 1.74 A) | trip ≤ 3.0 A class min | 215.9 mΩ | 143 mV offset |
| X2: eFuse IN at a 3.0 A draw | ≥ UVLO 2.7 V + 20 % (POW-004 I4's margin) | 223.3 mΩ | 3.850 V |
| X3: 3V3_STBY (HT7533 → MAX16054) stays in regulation at the M1 worst load | VIN − 0.1 V ≥ 3.366 V | 302.9 mΩ | 4.129 V |
| POW-006 B2 / B18: eFuse min limit, slot 5–6 headroom | as in budget.py | 341 / 346 mΩ | pass |
| POW-006 B1, B4, B6, B7, B9, B9b, B17b | as in budget.py | > 350 mΩ | pass |
| POW-006 B16/B17 keyboard port (DC) | ≥ 4.40 V | does not move: the boost regulates | 4.784 V |

The X rows are analytic and are not existing checks. They cover the
behaviour the task names: CC detection, eFuse UVLO and the POWER button's
supply. Past about 400 mΩ `budget.chain` has no solution (the
constant-power loads collapse), so the search stops at 350 mΩ.

**ngspice decks** (`--spice 20,60,90,120,160`, all corners):

| Test | 20 → 160 mΩ | Fails? |
|---|---|---|
| POW-001 3V3 buck | P9 dropout margin 664 → 338 mV. P8 5V_SYS once up 3.93 → 3.63 V. Step and overshoot move < 7 mV. | No |
| POW-004 inrush | I4l receptacle minimum **rises** 3.32 → 3.98 V (more damping of the cable ring). I2 surge falls. | No |
| POW-007 keyboard boost | P1w port minimum 4.698 → 4.685 V at 120 mΩ (+285 mV over 4.40). P4 inductor 0.75 → 0.80 A. | No, to 120 mΩ. At 160 mΩ the TI model hits "timestep too small" in the high corner step: a solver failure, not a limit. |
| POW-008 HDMI | H3 PTC current 0.096 → 0.106 A (hold 0.17 A). H5 converter input 3.75 → 3.39 V (≥ 1.3 V). H4 improves. | No |
| POW-003 Wi-Fi card (routed board) | F1w ESP32 minimum 2.979 → 2.974 V | **Already fails at 20 mΩ** (−21 mV). This is independent of the loop (0.04 mV/mΩ); it belongs to the Wi-Fi card work. |

### Derived limit

- **Hard ceiling: 89.8 mΩ board-side loop**, bound by POW-006 B5 at its
  waived 5 % margin. B5 is only green because of that waiver: at the
  standard 10 % it fails even at 0 mΩ (1.372 A against 1.35 A). If the
  waiver were ever withdrawn, B5 would fail whatever the loop, and the next
  binding check is **B10 at 121.2 mΩ**.
- **Recommended design value: ≤ 60 mΩ.** That leaves 30 mΩ (33 %) to the
  B5 edge. B5 is then 1.407 A (6.2 %) and B10 0.768 A (4 % under 0.80 A).
  No ngspice check loses more than about 0.1 V of margin: POW-001 P9 drops
  from 664 to 578 mV and POW-008 H5 from 2.45 to 2.35 V.

## Copper self-heating at the 3.213 A eFuse limit

The TPS25947 regulates at its limit and does not trip. The input PTC's
40 °C hold is 3.15 A, so it need not trip at 3.2 A either. A load just
under 3.213 A (for example a partial 5V_SYS short) is therefore a
**continuous** condition, and the copper must survive it in steady state.
The 754 mW is not spread evenly: the J1–F1 run is a single 0.5 mm F.Cu
track about 16 mm long (plus a via), dissipating about **24 mW per mm**.

The estimate uses the IPC-2221B fit (I = k·ΔT^0.44·A^0.725). The outer-layer
k is used as the IPC-2152-style estimate for all layers, because IPC-2152
finds inner traces run about as cool as outer ones. The inner-layer k gives
an upper bound. An adjacent plane (In1 GND) would lower these figures, but
by an amount that needs IPC-2152's plane charts or a board thermal
simulation.

| Segment at 3.213 A | ΔT estimate | Upper bound |
|---|---|---|
| J1–F1 F.Cu 0.5 mm, nominal 1 oz (34.8 µm) | **62 °C** | 299 °C |
| J1–F1 F.Cu 0.5 mm, sensitivity copper (0.4 mm × 24.9 µm) | **155 °C (off chart)** | — |
| F1–U2 In2 0.5 mm / In3 1.0 mm, each alone, sensitivity copper | 562 / 179 °C (they share the current; off chart) | — |
| Outer 2.0 mm drawn, sensitivity copper | 16 °C | 76 °C |
| Outer 3.0 mm drawn, sensitivity copper | 8 °C | 39 °C |

The current route is not self-consistent with its own 115 °C corner:
40 °C ambient plus 62 °C is about 102 °C even at nominal copper, and the
finished-minimum sensitivity copper runs off the charts. That is before the
eFuse's own 63 °C and the other nearby sources. For **ΔT ≤ 20 °C at
3.213 A**, each full-current conductor needs about 53 mil² of finished
copper: **≥ 1.75 mm drawn on outer 1 oz at the 80 %/24.9 µm sensitivity
factors** (1.0 mm at nominal 1 oz), or an equivalent pour. For ≤ 10 °C it
needs 2.6 mm. At 2 mm drawn the outer copper is 0.59 mΩ/mm at 115 °C, so
meeting the thermal rule with a 40 mm path already gives about 23 mΩ of
positive copper. **On this board, heating sets the copper width before the
voltage budget does.** USB Type-C §3.7.8.4 allows the mated connector
itself +30 °C at 5 A, so a 20 °C board-copper rule is in proportion.

## The current routed board against the derived value

At the 115 °C sensitivity corner (`main_input_heat.py`):

| Term | mΩ |
|---|---|
| Positive copper J1→F1 + F1→U2 | 73.06 (57.4 at 40 °C, 63.6 at 70 °C) |
| GND return copper | not extracted (the relocation trial's In1-only scenario is 2.25) |
| Receptacle terminations and solder | not bounded |
| Mated contacts, spec-literal (inside the cable's 250 mΩ, §4.4.1) | 0 |
| Mated contacts, counted again conservatively (4 × 50 mΩ per rail, shared) | 25 |
| Mated contacts, counted again, one contact per rail | 100 |

- **Spec-literal:** 73.06 + GND + solder against 60 mΩ. It fails by more
  than 13 mΩ. It fits under the 89.8 mΩ ceiling only if GND plus solder is
  under 16.7 mΩ, and it fails the heating rule regardless.
- **Contacts counted again (four-way):** 98.1 mΩ + GND. It fails even the
  89.8 mΩ ceiling.
- **The relocation trial** (16.60 positive + 2.25 GND = 18.85 mΩ) passes
  every option below with room to spare. It still has four opens and ten
  DRC findings.

## Options for David

1. **Keep 20 mΩ, with contacts counted inside it** (the status quo; see
   main-mb005-connector-decision-20260928.md). This needs a ≤ 4 mΩ
   mated-pair guarantee that no catalogue part offers, plus a large reroute.
   MB-005 stays red indefinitely. No downstream check needs this: the
   tightest one allows 4.5 times as much.
2. **Adopt the derived requirement, spec-literal (recommended):**
   board-side loop (receptacle terminations + VBUS/GND copper to F1/U2)
   **≤ 60 mΩ at the hottest corner**, with the mated contacts carried by
   the cable's §4.4.1 budget as the model already does. Add a thermal
   requirement: **ΔT ≤ 20 °C at 3.213 A continuous** for the input copper
   (≥ 1.75 mm outer 1 oz drawn, or a pour). The current board needs
   J1–F1 and F1–U2 widened or poured on outer copper, about 73 → about
   25 mΩ. No connector qualification is needed beyond a standard compliant
   USB-C receptacle. Trade-off: it relies on §4.4.1's definition. A cable
   that only just meets the IR limit is already the model's worst case, so
   nothing is lost there.
3. **Adopt the derived ceiling but also count the contacts again:** loop
   including four-way-shared USB-IF contact maxima (25 mΩ) ≤ 85 mΩ, so
   copper and solder ≤ 60 mΩ. This carries only 4.8 mΩ of margin to B5's
   waiver edge, but it needs no argument about what the cable figure
   includes. The relocation trial meets it (43.85 mΩ). The current route
   does not (98.1 + GND). Take the same thermal rule as option 2.

Either derived option also makes clear which failure is the real one on
the current board: **copper heating at the fault corner**, not voltage
drop.

## Reproduce

```
python3 hw/power/mb005_loop_sweep.py                        # budget + analytic edges, heating table (<1 s)
python3 hw/power/mb005_loop_sweep.py --spice 20,60,90,120   # ngspice decks in scratch dirs (~15 min)
python3 test/hw/test_mb005_loop_sweep.py
```

The ngspice runs write to temporary directories, not `build/power`.
