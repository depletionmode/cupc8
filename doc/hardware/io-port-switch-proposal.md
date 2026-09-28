# IC-005: replace the IO card's port switch (proposal)

**Status: proposal, not applied.** `hw/boards/io.py` still fits the
SY6280AAC. The change below needs David's approval before the IO board
agent applies it. Background: [IC-005 switch audit](ic005-switch-audit.md).

Checks: `python3 hw/power/io_port_switch.py` (behavioural decks plus TI's
TPS61023 model, in `build/power`), tests: `python3 test/hw/test_io_port_switch.py`.

## Recommendation

**TI TPS2553DBVR-1** (LCSC **C111738**), the latch-off version of the
TPS2553, SOT-23-6 (DBV). JLC extended part, **14,185 in stock**
(2026-09-28, `hw/tools/jlcparts.py`), $0.29 at 1 / $0.23 at 50. The build
places 2 (2 IO cards), so stock is ~7,000× the 2× rule.

Datasheet: TI SLVS841F (Aug 2016), https://www.ti.com/lit/ds/symlink/tps2553.pdf,
sha256 `88e453700cea2b263cdb5b44fce1e883e0f6d3b975457f879ac1423eeea42071`.

Why this part:

| Need | SY6280AAC (fitted) | TPS2553DBVR-1 |
|---|---|---|
| Guaranteed limit at the setting | none at 12 kΩ (only 0.75–1.25 A at 6.8 kΩ, 25 °C) | min/max equations over process and −40…125 °C (9.5.1), tested at 20k/49.9k/210k (7.5) |
| Fault output | none (a VBUS divider stands in) | open-drain FAULT, 5–10 ms deglitch on overcurrent (guaranteed), immediate on over-temperature |
| After a fault | constant current, thermal cycling | latches off after the deglitch; EN toggle restarts |
| Reverse current | not specified | off when VOUT > VIN + 95…190 mV for 2–6 ms; IREV ≤ 1 µA |
| IN absolute max | 6.0 V | 7.0 V (6.5 V recommended) |
| RDS(on) | 80 mΩ typ, no max | 85 mΩ typ, **135 mΩ max** (DBV, −40…125 °C) |
| Turn-on | 130 µs typ | ≤ 3 ms, rise 1.1–1.5 ms at 6.5 V (1 µF / 100 Ω) |

Candidates rejected:

- **TPS2553DBVR** (C55266, 59,254 stock, $0.54): same die, constant
  current. A drop-in alternative if David prefers no firmware change; a
  short then thermal-cycles the switch indefinitely at up to 3.4 W instead
  of stopping after ≤ 10 ms, and the card draws ~1 A from the slot for as
  long as the short lasts.
- **TPS2051C / TPS2001C**: fixed limit (0.5 A-class, wide spread); no
  window that guarantees 500 mA under the budget.
- **AP22802 / AP22811 / TPAP22802**: fixed ~2 A-class limit.
- **AP2552/AP2553** (SOT-26, 68–325 stock) and **MIC2009/MIC2019**
  (SOT-23-6, 0–250 stock): adjustable with a flag, but JLC stock is thin
  (MIC2009YM6-TR 250, AP2552W6-7 325); their limit tolerances were not
  evaluated further.
- **TPS2554/TPS2557**: VSON-10, 7 in stock.

## The limit window

TI's equations (9.5.1), RILIM in kΩ:
`IOS(min) = 25230 / RILIM^1.016`, `IOS(max) = 22980 / RILIM^0.94` mA.
They are the design curves of figure 23, which "include current-limit
tolerance due to temperature and process"; they exclude the resistor. The
tested rows of 7.5 sit inside them to 0.26 % (20k, 210k min) and are tighter
at 49.9k (565 mA max against the equation's 582). The check widens the
equations by that 0.26 % envelope.

**RILIM = 46.4 kΩ 1 %, 100 ppm/°C** (0402WGF4642TCE, C52378, 3,171 stock).
With 1 % and 100 ppm/°C over a 0…85 °C resistor (±60 K from 25 °C) the
resistor spans ±1.6 %:

- minimum: 25230 / (46.4 × 1.016)^1.016 × 0.9974 = **501.9 mA**
- maximum: 22980 / (46.4 × 0.984)^0.94 = **633.0 mA**

Against the requirement:

| Requirement | Value | Check |
|---|---|---|
| A 500 mA keyboard (USB 2.0 high-power device) is never limited | 501.9 mA min | S1 pass (+0.4 %) |
| IO card +5V, 500 mA keyboard, worst corner, vs slot.md 0.80 A | 0.767 A (unchanged: the switch is after the boost) | S4 pass (+4.1 %) |
| Boost inductor at the max limit, worst card input 3.58 V, vs the 2.7 A valley limit | 1.03 A | S2 pass (+62 %) |
| Machine VBUS current, worst corner, port at the max limit, vs the eFuse's 2.63 A min | 2.06 A | S3 pass (+21 %) |
| Keyboard VBUS, worst DC corner, 500 mA through 135 mΩ | 4.776 V vs 4.40 V | S5 pass |
| U5 IN at the eFuse's OVLO trip max (pass-through) vs 6.5 V recommended | 5.806 V | S6 pass |
| Junction at 500 mA, 40 °C | 46 °C | S10 pass |

The 500 mA margin is thin by construction: 47.0k (basic part) would give
496.7 mA min and fails S1. **45.3k** is the alternative if David wants
margin on the minimum (514 mA min, 647 mA max; the card then reaches
~1.06 A in the residual case below).

**Residual (not closable by any switch in this class).** A device that draws
between 500 mA and the actual limit (≤ 633 mA) is out of USB spec but is
neither limited nor flagged. At the worst corner the IO card's +5V then
reaches **1.026 A**, over slot.md's 0.80 A and the slot PTC's 0.92 A hold at
40 °C. Only the boost sits on the IO card's slot +5V (the RP2040 is on 3V3),
so the consequence is the slot PTC tripping and dropping the keyboard port;
the machine total stays 21 % under the eFuse's minimum limit (S3). No
available switch has a tolerance tight enough to guarantee both ≥ 500 mA and
≤ 0.58 A (the port current at which the card reaches the PTC hold).

**The catalogue wording is self-contradictory.** "Current limit set to
≤ 500 mA" cannot coexist with delivering 500 mA to a keyboard. Proposed
wording for IC-005 (David or the catalogue owner to apply):

```
checks = "port switch limit guaranteed 500..633 mA (TPS2553-1, RILIM 46.4k 1 %); FAULT (open drain, 5..10 ms deglitch) to GPIO8 and latch-off on overcurrent; attach < 5 ms in limit; short transient within U5/TPS61023 absolute maxima (model)"
cmd = "python3 hw/tools/boardcheck.py io power && python3 hw/power/io_port_switch.py && python3 test/hw/test_io_port_switch.py && python3 hw/power/rp2040_vreg.py io build/hw/io && python3 test/hw/test_rp2040_vreg.py"
```

## FAULT to GPIO8

GPIO8 (`VBUS_nFAULT`) is already an input that firmware reads active-low
with its pull-up on (`fw/rp2040/io/main.c`), so FAULT goes to GPIO8 and the
VBUS divider goes. No pins.yaml change: the net name and GPIO stay.
Free GPIOs exist (e.g. GPIO9–15) if David also wants a VBUS-low sense; not
proposed.

- Pull-up **10 kΩ to 3V3** (C25744, basic). At 3.465 V it sinks 0.35 mA,
  inside the 1 mA at which VOL ≤ 180 mV is specified: 0.18 V against the
  RP2040's VIL 0.8 V (S7). Released: 3.135 V − (1 µA FAULT + 1 µA GPIO) ×
  10k = 3.115 V against VIH 2.0 V (S8). A 1 kΩ pull-up fails S7 (VOL
  unspecified above 1 mA): the mutation test.
- EN: active high, VIL ≤ 0.66 V; R11 100 kΩ × 0.5 µA = 50 mV holds it off
  in reset (S9).

## Schematic / BOM change (for the IO board agent, after approval)

Replace `hw/boards/io.py` lines 54–80 (the U5/R10/R12/R13 block; R11,
C20–C22 unchanged) with:

```python
    # ---- VBUS: TPS2553DBVR-1 from the boost's output (IC-005,
    # doc/hardware/io-port-switch-proposal.md). IOS(min) = 25230/R^1.016,
    # IOS(max) = 22980/R^0.94 mA (R in kOhm): 46.4k 1 % -> 502..633 mA
    # guaranteed. Latches off 5..10 ms into an overcurrent with FAULT low;
    # toggling EN restarts it.
    u5 = s.add("jlc:TPS2553DBVR-1", "U5", "TPS2553DBVR-1", "jlc:SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL",
               at=(200 * G, 20 * G), fields={"LCSC": "C111738"})
    s.connect(u5, "IN", "VBOOST")
    s.connect(u5, "OUT", "VBUS")
    s.connect(u5, "GND", "GND")
    s.connect(u5, "ILIM", "ILIM")
    s.connect(u5, "EN", "VBUS_EN")
    s.connect(u5, "FAULT", "VBUS_nFAULT")
    r10 = rc.passive(s, "R", "R10", "46k4", (186 * G, 30 * G), lcsc="C52378")
    rc.two(s, r10, "ILIM", "GND")
    r11 = rc.passive(s, "R", "R11", "100k", (186 * G, 46 * G))       # EN must not float (RP2040 in reset)
    rc.two(s, r11, "VBUS_EN", "GND")
    c20 = ...  (unchanged)
    c21 = ...  (unchanged)
    c22 = ...  (unchanged)
    c25 = rc.passive(s, "C", "C25", "1u", (206 * G, 12 * G))         # at U5 IN: 100 nF rings IN to 8.5 V in a short (T5)
    rc.two(s, c25, "VBOOST", "GND")
    # FAULT is open drain, active low: pulled up to the card's 3V3 for GPIO8
    r12 = rc.passive(s, "R", "R12", "10k", (200 * G, 46 * G))
    rc.two(s, r12, "3V3", "VBUS_nFAULT")
```

BOM delta per IO card:

| Ref | Was | Becomes | LCSC | Stock |
|---|---|---|---|---|
| U5 | SY6280AAC, SOT-23-5 (C55136) | TPS2553DBVR-1, SOT-23-6 | C111738 | 14,185 |
| R10 | 12 kΩ ISET (C25752) | 46.4 kΩ 1 % 0402, ILIM | C52378 | 3,171 |
| R12 | 15 kΩ VBUS→GPIO8 (C25756) | 10 kΩ 3V3→GPIO8 | C25744 (basic) | 22.9 M |
| R13 | 22 kΩ GPIO8→GND (C25768) | removed | — | — |
| C25 | — | 1 µF 25 V X5R 0402 at U5 IN | C52923 (basic) | 6.2 M |

Pin/footprint impact: **not pin compatible.** SY6280 (SOT-23-5): 1 OUT,
2 GND, 3 ISET, 4 EN, 5 IN. TPS2553 DBV (SOT-23-6): **1 IN, 2 GND, 3 EN,
4 FAULT, 5 ILIM, 6 OUT**. Same 2.9 × 1.6 mm body class; the footprint
`jlc:SOT-23-6_L2.9-W1.6-P0.95-LS2.8-BL` is already in `hw/lib/jlc.pretty`.
Needed outside this proposal (not edited here, per the rules):

- `hw/lib/jlc.kicad_sym`: a `TPS2553DBVR-1` symbol (pins IN, GND, EN,
  FAULT, ILIM, OUT).
- `hw/parts/C111738.yaml`: the pin table above (`ccw: [1, 6]`) from
  SLVS841F section 6, and the JLC rotation entry.
- `hw/boards/io.py` PLACEMENT: drop R13, place C25 at U5 pin 1 (IN) with
  its ground next to U5 pin 2; U5's
  silk-trim special cases in `prepare()` (lines ~160–195) reference the
  SOT-23-5 body marks and must be redone. The U5 area is re-routed.
- **Layout requirement from the model (T5):** C25 (1 µF) at U5 IN, and
  U5 IN no more than ~10 nH (≈ 10 mm of track) from C23/C24 (today about
  7 mm). See the transient model.
- `hw/power/design.py` (after approval): `SY6280_RON_TYP/MAX` → 0.085 /
  0.135, θJA 182.6; POW-006 B16 and POW-007 P1 lose 7.5 mV at 500 mA
  (4.784 → 4.776 V; 4.697 → ~4.690 V), both still over 4.40 V.
- power.md "IO card keyboard boost" and the audit doc.
- **Firmware** (`fw/rp2040/io/main.c`): with the latch-off part, after
  FAULT the port stays off until EN is toggled. Add a retry: on FAULT, drive
  VBUS_EN low, wait (e.g. 1 s), drive it high; keep reporting status bit 4.
  No card command changes, so no simulator change is implied; if the
  simulator models the fault bit's behaviour, mirror the retry there.

## Transient model

The model is `hw/power/io_port_switch.py`. The switch is behavioural; its
parameters come from SLVS841F: the guaranteed IOS window, RDS(on), the
5–10 ms FAULT deglitch, latch-off, and UVLO (typical 2.35 V). Two numbers
are **not guaranteed**, so both are swept: the short-circuit response time
tIOS (2 µs typical; 20 µs as a stress value, the top of figure 15's
typical curve) and how fast the clamp falls from the overdriven peak to IOS
(0.1 or 1 µs). The switch's minimum RDS(on) is also unpublished; the peak
uses 60 mΩ (70 % of the 85 mΩ typical).

**T1, attach (behavioural).** EN switches the port on into 120 µF (C21
+20 %) plus a device's 10 µF, with a 100 mA unconfigured-device load, at
the **minimum** limit (502 mA) and an instant gate. The switch is in current
limit for **1.37 ms** and VBUS reaches 4.40 V 1.25 ms after EN. The
shortest FAULT deglitch is 5 ms (+73 %, 25 % required), so an attach never
flags a fault or latches the port off.

**T2/T3, short and latch (behavioural).** 500 mA steady, then a 20 mΩ short
behind 50 nH (at the receptacle) or 0.5 µH (a cable's far end), at each
response time. One millisecond later the switch holds its limit (≤ 633 mA),
and after the 10 ms maximum deglitch the -1 latches off (0 mA at the end).
FAULT goes low 5–10 ms after the limit engages, or at once on thermal
shutdown. U5 dissipates at most 5.43 V × 0.633 A = 3.44 W for ≤ 10.02 ms,
**≤ 34.4 mJ** per event. The constant-current TPS2553 would instead keep
thermal-cycling for as long as the short lasts.

**T4–T6, peak and excursions (TI's TPS61023 model).** POW-007's chain at
vSafe5V max, with the switch in place of the SY6280, 10 nH and 5 mΩ of
track from C23/C24 to U5 IN, and the proposed 1 µF at IN. Each excursion is
moved up 0.313 V, from the model's 5.118 V regulation to the 5.431 V
pass-through maximum:

| Response | Clamp | Short | Peak | U5 IN min…max (+0.313 V) |
|---|---|---|---|---|
| 2 µs typ | 0.1 µs | plug, 50 nH | 14.9 A | 3.61 … 5.79 (6.10) V |
| 2 µs typ | 0.1 µs | cable, 0.5 µH | 2.8 A | 4.89 … 5.22 V |
| 2 µs typ | 1 µs | plug | 17.4 A | 3.24 … 5.22 V |
| 2 µs typ | 1 µs | cable | 3.8 A | 4.73 … 5.22 V |
| 20 µs stress | either | plug | 22.0 A | 2.10 … 5.12 V |
| 20 µs stress | either | cable | 16.4 A | 2.03 … 5.12 V |

- T4: the boost's output (TPS61023 VOUT, 6.0 V absolute) never rises above
  its pre-short level: **5.431 V** worst (+0.57 V).
- T5: U5 IN at most **6.10 V** against 7.0 V absolute (+0.90 V). With TI's
  0.1 µF minimum instead of 1 µF it rings to **8.5 V** (the mutation test
  `test_mutation_100n_at_in_fails_the_in_overshoot`); with 100 nF and only
  2 nH of track, 5.94 V. Hence C25 = 1 µF.
- T6: U5 IN at least **3.24 V** at the typical response. At the 20 µs
  stress the boost capacitors sag until IN reaches UVLO (2.0–2.1 V
  minimum). Without the UVLO in the model the stress cases reached −0.87 V
  at IN (−3.75 V with 100 nF): that is the model running past a shutdown
  the part performs, but it is also why the stress response is not a
  guarantee of anything.
- The peak (15–22 A at a receptacle short) is drawn from C23/C24 and the
  1 µF, not from the slot: the TPS61023 keeps its inductor inside its own
  limit.

**Reverse current (datasheet, not simulated).** If the slot's +5V
collapses while the port capacitors hold VBUS up, the switch conducts
backwards through RDS(on) until VOUT − VIN exceeds 95–190 mV for 2–6 ms.
It then opens (IREV ≤ 1 µA), pulls FAULT low and, being the -1, stays off
until EN toggles. That protects the TPS61023's output from back-feed.

**What remains unbounded.** The peak current, the response time and the
clamp speed are typical or assumed. So are the 10 nH track and the 60 mΩ
peak RDS(on). None of them affects the guaranteed limit window, the
FAULT timing or the latch-off, which is what IC-005 asks for. The
excursion results (T4–T6) are layout- and model-dependent: re-run
`io_port_switch.py` against the routed board once U5 is placed. A
first-article short test (scope on U5 IN, VBUS, FAULT) would close it.

## Checks and tests

```
python3 hw/power/io_port_switch.py        # S0-S10, T1-T6: all pass (~25 s, 13 ngspice runs)
python3 test/hw/test_io_port_switch.py    # 8 tests, ~10 s
```

The mutation tests fail the checks on purpose: RILIM 47.5k (S1, 491 mA
minimum), a 5 % resistor (S1), a 1 kΩ FAULT pull-up (S7, VOL unspecified
above 1 mA), and 100 nF at IN (T5). A further test confirms the equation
window encloses every tested datasheet row.
