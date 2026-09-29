# First-article measurement plan (M1)

> **Accepted by David (2026-09-28):** the four limits marked "proposed" below (>= 10 ohm rail short screen, 5 C top-to-junction allowance, x1.25 iCE40 core-current margin, 30 mVpp rail ripple) are accepted as written.

**Status: proposal, 2026-09-28.** Nothing here is in `test/catalogue.toml`
yet; the proposed entries are at the end. It closes the gates that analysis
cannot (`doc/m1-live-status.md`, "B. Needs outside data or measurement";
`verification.md` §5). Every acceptance limit below is one the models
already use, quoted with the file and line it comes from. Where a limit is
new (a short-circuit screen, a top-to-junction allowance), it says
**proposed** and David decides.

Results go into `doc/hardware/fa-results/` as JSON (see
[Recording results](#recording-results)). `tools/fa_results.py` reads them,
applies the limits (which live in the tool, not in the records) and reports
each gate green, red or pending.

## Contents

- [How to use this plan](#how-to-use-this-plan)
- [Equipment](#equipment)
- [Common methods](#common-methods): M-K Kelvin resistance, M-S scope on
  a rail, M-T temperature, M-I current, M-Z capacitor impedance
- [Stage 0: loose parts, before the boards arrive](#stage-0-loose-parts-before-the-boards-arrive):
  WC-103, CC-105, MB-114
- [Stage 1: unpowered inspection](#stage-1-unpowered-inspection-every-unit):
  MECH-101 (look and measure)
- [Stage 2: shorts and first power](#stage-2-shorts-and-first-power-every-unit):
  MB-107, MB-101, CC-102, GC-103, IC-102, WC-102, SC-101, EC-101, YC-101
- [Stage 3: fit and four-terminal resistance](#stage-3-fit-and-four-terminal-resistance-unpowered):
  MECH-101 (insert), MB-110, MB-108, CC-103, WC-104
- [Stage 4: functional bring-up](#stage-4-functional-bring-up-existing-rows):
  the existing MB-102..106, CC-101, GC-101, IC-101, WC-101, and GC-105 (GPU
  hot-plug detect and DDC/EDID)
- [Stage 5: power integrity under load](#stage-5-power-integrity-under-load):
  WC-105, MB-111, CC-104, GC-104, IC-103, SC-102, EC-102, YC-102, IC-104,
  MB-113
- [Stage 6: heat, stress and burn-in](#stage-6-heat-stress-and-burn-in):
  MB-109, WC-106, MB-112, GC-102
- [Recording results](#recording-results)
- [Proposed catalogue entries](#proposed-catalogue-entries)
- [Gate coverage](#gate-coverage)
- [What first articles cannot close](#what-first-articles-cannot-close)

## How to use this plan

**Order.** The stages run in order, and within a stage the fastest,
highest-risk checks come first. Nothing is powered until it has passed the
short screen (Stage 2). No card goes into a powered slot until MECH-101 has
shown that it seats and that reversed insertion is blocked (Stage 3). The
measurements that can destroy a board (MB-109 at 3.2 A) come last, and run
on one designated unit.

**The first-article batch.** JLC's minimums give 5 bare PCBs of each board,
of which you choose how many to assemble. Proposed:

| Board | Assembled | Bare kept | Use of the bare PCBs |
|---|---:|---:|---|
| main | 3 (unit 1: the measurement board, may be reworked; unit 2: clean reference; unit 3: the spare `debugging.md` §3 plans) | 2 | none |
| cpu, gpu, io, wifi, storage, eink, system | 3 each | 2 each | MB-110 contact coupons (a bare card's finger traces reach pads you can probe) |

Loose parts, ordered from LCSC at the same time as the batch (Stage 0):
10 × C45783, 5 each of C23733, C52923 and C1525, 5 × MAX16054AZT and
5 × HT7533-2 (the parts the main board fits), 1 × ESP32-C3-MINI-1U-N4
(optional, WC-105b). Ask LCSC for a single date code if you can; record the
lot/date code in each record's `notes`.

**Sample sizes** are in each measurement and in the tool
(`python3 tools/fa_results.py --list`). A board-level gate needs 2 units
(3 for the first-power screens, which every assembled unit gets anyway);
part-lot gates need 5 or 10 samples; the destructive MB-109 and the long
MB-112 need 1. GC-102 is a per-unit qualification: every GPU card that is
ever used, not just the first articles (`power.md` "GPU card RP2040
overclock", line 293).

**Who does what.** David runs the bench. Claude writes the test firmware
hooks this plan asks for (trigger GPIOs, continuous-load modes), turns
records into gates and updates the models when a measurement moves a
number.

**The full order.** Whether a failed or pending gate here holds the full
run is David's call (`m1-live-status.md`, "C. Needs David"). Each
measurement says which results would need a design change.

## Equipment

What a hobbyist bench can realistically hold, and where it is not enough.

| Instrument | Minimum | Used for | Not good enough |
|---|---|---|---|
| Bench supply | 0–6 V, 0–5 A, constant-current mode, ≤ 10 mV set resolution (1 mV for MB-113) | first power, Kelvin current source, MB-109 input | a supply whose current readout you trust for Kelvin work: use a DMM in series instead |
| Two DMMs | one with a 200 mV range at 10 µV resolution (4½ digits or better) and a µA range; thermocouple input helps | Kelvin voltage, shunt voltages, rail DC levels, µA currents | a 3½-digit DMM for Kelvin work (100 µV steps: 10 % error at 1 mV); any 2-wire resistance range below about 1 Ω (lead and probe contact are 50–300 mΩ and move) |
| Kelvin probes | four separate leads: two force (clips or wires), two sense (needle probes or pogo pins) | M-K | combined "Kelvin clips" whose jaws cannot land on a 1 mm pad |
| Oscilloscope | 100 MHz, 2 channels, 8-bit is fine, AC coupling down to 10 mV/div, 20 MHz bandwidth limit, CSV export; 10× probes with **spring ground tips** (≤ 1 cm) | M-S: rail droop, bursts, reset timing | the 15 cm ground lead (rings at tens of MHz and shows 50–200 mV of false spikes on a 1 V rail); the scope's DC accuracy (±2–3 % of full scale) for margins of tens of mV: take DC from the DMM. For TMDS eye (252 Mb/s) you would need ≥ 1.5 GHz; GC-102 is the functional substitute |
| Temperature | K-type thermocouples, 36–40 AWG fine wire, Kapton tape, thermal paste; a second thermocouple for ambient | M-T | an IR thermometer/gun (spot far larger than an SOT-23); an IR camera on bare metal, gold or glossy packages (emissivity errors of tens of °C) without a matte-black dot or Kapton on the target |
| IR camera (optional) | ≥ 160 × 120, with the target ≥ 3 × 3 pixels | finding the hot spot before placing a thermocouple | as the recorded value on small parts |
| 40 °C box | expanded-polystyrene box, 25–40 W heater (incandescent bulb or PTC heater), a thermostat module (for example a W1209), a small fan stirring the air but not blowing on the boards | GC-102, WC-105, WC-106, MB-111, MB-113, CC-104 | a hair dryer or hot-air station (uneven, unregulated) |
| Impedance | a NanoVNA (50 kHz–1.5 GHz) with the bias fixture in M-Z; better, an LCR meter or impedance analyser **with DC bias** (for example a makerspace's or university lab's HP 4284A / Keysight E4980A) | M-Z: capacitor C and ESR under bias | an ESR meter or a handheld LCR meter (DE-5000 class): no DC bias, and the bias loss (−55 % at 5.5 V) is the quantity being measured. At most a screen for gross ESR |
| DC electronic load | 0–5 A, constant-current, ≥ 25 W | MB-109, MB-112, IC-104 | power resistors alone (cannot sweep to find the eFuse limit) |
| USB-C | a USB-C plug breakout rated 5 A, with ≥ 20 AWG leads; a USB power meter | injecting the bench supply into J1; sanity check of input power | a USB power meter's current as a recorded value (±1–2 % plus offset; fine as a sanity check) |
| Optics | USB microscope or 10× loupe, with a **stage micrometer** (0.01 mm divisions) for calibration; digital calipers | MECH-101 | calipers for the 0.10 mm notch-wall-to-finger gap (their jaw and ±0.02 mm are the same size as the margin); fine for notch width |
| HDMI capture | a UVC USB capture device that takes 640 × 480 at 60 Hz | GC-102 glitch counting | watching a monitor for an hour (not objective; only as a fallback with a recording reviewed at 4×) |

## Common methods

### M-K: four-terminal (Kelvin) resistance

1. Unpowered board. Force current with the bench supply in constant-current
   mode through the path, with a second DMM in series to read the current
   (the supply's own readout is ±1 % plus offset). 1.000 A for paths under
   1 Ω; 0.5 A for single connector contacts (slot contacts are rated about
   1 A each, `slot.md` line 40).
2. Sense with separate needle probes **exactly on the defined end points**
   (named in each measurement), inside the force points, so that the force
   leads' own contact resistance is outside the measurement.
3. Zero check: touch both sense probes to one point with the current on:
   the reading must be under 5 µV. Otherwise, clean the probes.
4. **Reverse the current** and read again: R = (V₊ − V₋) / (2 I). This
   cancels thermal EMFs and the DMM's offset, which at these levels
   (µV) are the same size as the signal.
5. Keep the current on for under 10 s per reading so that the copper does
   not warm, and record `board_temp_c` (thermocouple on the board next to
   the path). The tool scales copper to the model's hot corner.
6. Resolution: at 1 A, 10 µV is 10 µΩ. A dedicated 4-wire milliohm meter is
   fine instead if its resolution is ≤ 1 % of the limit (0.3 mΩ for
   MB-110's 30 mΩ).

### M-S: a rail on the scope

1. 10× probe, spring ground tip, tip and ground **on the two pads of the
   decoupling capacitor** nearest the load (named in each measurement).
   Never a clip lead.
2. AC coupling, 10–20 mV/div, 20 MHz bandwidth limit on (regulator loops
   are under 1 MHz; the bucks switch at 1.2–1.4 MHz, which it still shows).
3. Trigger on a test-firmware GPIO that marks the start of the load event
   (TX burst, SD write, refresh, DMA). Without one, trigger on the rail's
   own falling edge, normal mode.
4. Capture at least 1000 events in peak-detect/envelope or persistence mode
   and record the worst excursion; save one representative capture as CSV.
5. The rail's DC level comes from the DMM at the same pads. Minimum =
   DMM DC + most negative AC excursion; maximum likewise.

### M-T: temperature

1. Thermocouple on the target with a dot of thermal paste, held by Kapton
   tape; a second thermocouple measures air 5 cm away, out of any airflow.
2. Steady state: the reading changes by less than 0.5 °C over 5 minutes.
3. Record the **rise** over the ambient thermocouple (`*_rise_c`). The
   models are at 40 °C ambient (`hw/power/design.py` line 21, `AMBIENT_C`),
   so every thermal limit here is (limit − 40 °C) as a rise.
4. Rise at room ambient plus 40 °C is acceptable for pure heat checks
   (conduction and convection are close to linear over 20 °C). It is **not**
   acceptable where the silicon's own behaviour depends on temperature
   (GC-102 overclock, WC-105 ESP32 current, MB-111/CC-104 iCE40 leakage):
   those run in the 40 °C box.

### M-I: current measurement points

- **A card's +5V:** the main board's 50 mΩ sense resistor in each slot's
  feed, with pads either side (`debugging.md` lines 70–71;
  `hw/boards/main.py` line 492). I = V / 0.050. DMM for averages.
- **A card's +3V3:** there is no per-slot 3V3 sense. Use the main board's
  3V3 link R7 (`hw/boards/main.py` line 274) on the measurement board
  (unit 1), and take the difference with and without the card, the rest of
  the machine in the same state:
  - if the MB-051 proposal lands, R7 is a 1 mΩ alloy shunt
    (`hw/power/reset_supervisor.py`, `PARTS`): 40 mA is 40 µV, which needs a
    6½-digit DMM (1 µV). A 4½-digit DMM resolves only 10 mA there: not good
    enough for the 40–50 mA budgets;
  - otherwise, replace R7's 0 Ω jumper on unit 1 with a 20 mΩ 1 % 1206
    resistor: 0.8 mV at 40 mA, and at most 12 mV of drop at 0.6 A (a 100 mΩ
    part would drop 60 mV and bring 3V3 near the MAX811T's 3.17 V).
  Allow ±5 mA for the rest of the machine drifting between the two readings.
- **The chipset's 1V2:** the link R8 (`1V2_LDO` → `+1V2`, `hw/boards/main.py`
  line 279) is the RT9013's output. Same choice: the 1 mΩ shunt with a
  6½-digit DMM, or on unit 1 replace it with 100 mΩ 1 % (4 mV at 40 mA).
- **The CPU card's 1V2** has no link: see CC-104.

### M-Z: capacitor C and ESR under DC bias

The quantity is the capacitance and ESR **at the bias the part sees on the
board**, which no handheld meter applies.

- **Preferred:** an LCR meter or impedance analyser with DC bias: C at
  100 kHz and ESR at 1–2 MHz, bias as stated.
- **Hobbyist, NanoVNA shunt-through:** port 1 → DUT to ground → port 2, the
  DUT soldered on a small fixture. Each port joins the DUT node through a
  DC block (47 µF or more, film or electrolytic in parallel with a ceramic:
  a few tens of mΩ at 100 kHz, negligible against the 50 Ω ports); the bias
  comes in from the bench supply through 1 kΩ (far above the DUT's
  impedance at these frequencies, so it does not disturb the reading).
  Normalise with a solder short in the DUT position. Then
  Z = 25 Ω × S21 / (1 − S21); C from the reactance at 100 kHz, ESR from the
  real part at 1–2 MHz. Resolution around 1 mΩ with care; the limits here
  are 5 mΩ and 150 mΩ.
- Measure at 25 °C. The tool's limits already take out the maker's
  **guaranteed** TCC and life drift, as the model's stress corner does
  (`hw/power/wifi_parts.py` lines 150–160, `stress_capacitance`).

---

## Stage 0: loose parts, before the boards arrive

These need no board, so they run while JLC builds.

### WC-103: C45783 22 µF ESR and effective capacitance (POW-003 F5/F7, WC-005)

- **Closes:** POW-003 **F5** ("C1/C2/C3 guaranteed ESR maximum",
  `hw/power/buck.py` line 250) and **F7** ("minimum effective capacitance at
  bias, temperature and age", line 253), and with them WC-005. The same part
  is the IO card's boost output and the GPU card's buck-boost output
  (`hw/power/design.py` lines 240, 278), so this lot result covers those too.
- **Acceptance** (`doc/hardware/wifi-droop-fix-proposal.md` lines 140–141):
  ESR ≤ 150 mΩ each; C1 ≥ 5.8 µF and C2 ≥ 8.3 µF effective. Those effective
  values are after the guaranteed TCC (15 %) and life drift (12.5 %)
  (`hw/power/wifi_parts.py` lines 56–58), so at 25 °C:
  - `c_5v5_uf` (bias 5.5 V, C1's worst: `design.VBUS_MAX`) ≥ 5.8 / (0.85 × 0.875) = **7.80 µF**;
  - `c_3v6_uf` (bias 3.6 V, above C2's DC-high 3.411 V) ≥ 8.3 / 0.744 = **11.16 µF**;
  - `esr_max_mohm` (worst of both biases, 1–2 MHz) ≤ **150 mΩ**.
- **Setup:** M-Z.
- **Procedure:** for each sample: solder in the fixture; normalise; at 5.5 V
  bias, read C at 100 kHz and ESR at 1.0, 1.5 and 2.0 MHz; repeat at 3.6 V;
  record the lower-bias C for C2, the higher for C1, and the worst ESR.
- **Sample:** 10 capacitors from one LCSC lot (`units=10`).
- **Design change if:** any sample fails. ESR above 150 mΩ: fit the optional
  second 22 µF at U1 pin 3 (tolerates 200 mΩ,
  `wifi-droop-fix-proposal.md` lines 120–123) and rerun POW-003. Low C:
  qualify the replacement CL21A226MAYNNN# (C602037, line 44) or a 1206
  part and rerun POW-003, POW-007, POW-008. Typical data predict about
  4 mΩ and 9.8/14.0 µF (`wifi_parts.py` lines 64–67), so a failure means the
  lot is not what Samsung characterised.

### CC-105: the CPU card's 1V2 capacitors (CC-005)

- **Closes:** CC-005's "guaranteed C22/C1–C4 capacitance and ESR"
  (`hw/tools/boardcheck.py` line 31; `cpu-power-proof-gaps-20260928.md`
  lines 49–76).
- **Acceptance:**
  - `c22_1v2_uf`: C22 (C23733, 4.7 µF 0402 X5R) at 1.2 V, 25 °C
    ≥ 1.4 / (0.85 × 0.875) = **1.88 µF**. The POW-002/CC-005 deck uses
    1.4 µF on the rail (`hw/power/design.py` line 191, `RT9013_COUT`); this
    asks C22 alone to supply it, after TCC and the same life allowance as
    C45783 (Samsung gives none for this part: **proposed**), and leaves
    C1–C4 as margin.
  - `esr_c22_mohm` ≥ **5 mΩ**: RT9013 stability needs output ESR above 5 mΩ
    (`cpu-power-proof-gaps-20260928.md` line 65). In circuit the trace to the
    capacitor adds to it, so this is conservative.
  - `c21_3v3_uf`: C21 (C52923, 1 µF 0402 X5R 25 V) at 3.3 V ≥ **1.0 µF**
    (Richtek recommends an input capacitor above 1 µF, line 64). **Likely to
    fail:** nameplate tolerance alone allows 0.90 µF (line 67), before bias.
    Decide before ordering whether to change C21 to a 2.2 µF part.
- **Setup/procedure:** M-Z at the stated bias; C at 100 kHz, ESR at
  100 kHz–1 MHz (the LDO's loop region), lowest reading.
- **Sample:** 5 of each (`units=5`).
- **Design change if:** C22 fails: a larger 0603 capacitor and rerun
  CC-005. ESR below 5 mΩ: an RT9013 stability review (a small series
  resistance or a different LDO; `cpu-ldo-replacement.md` already notes the
  RT9013 is EOL). C21 fails: change C21.

### MB-114: 3V3_STBY part currents (MB-006 H1/H2)

- **Closes:** two assumptions in the main board's standby thermal row
  (`hw/power/board_thermal.py`): MAX16054 supply current ≤ 15 µA
  (`hw/power/design.py` line 111, `ONOFF_I_MAX`: the datasheet gives 7 µA
  typical) and HT7533-2 ground current ≤ 20 µA over load and temperature
  (`board_thermal.py` lines 71–72: ISS is 5 µA max only at 25 °C, no load).
  **Skip the MAX16054 half if its datasheet maximum is found**; keep the
  HT7533 half either way, since Holtek publishes no loaded or hot figure.
- **Acceptance:** `max16054_icc_ua` ≤ **15 µA**; `ht7533_ignd_ua` ≤ **20 µA**.
- **Setup:** each part on an SOT-23 breakout, DMM on its µA range in series
  with the supply pin (burden of a few mV is harmless here). MAX16054: VCC
  at 3.366 V (3V3_STBY maximum, `design.py` line 114), inputs in the idle
  state the board holds them in. HT7533: VIN 5.5 V and 24 V (its rating, as
  the model uses), output loaded with 50 µA; ground current = input − output
  current.
- **Procedure:** read at 25 °C, then on a hot plate at 60 °C (these parts
  barely self-heat; 60 °C covers 40 °C ambient with room). Record the
  larger.
- **Sample:** 5 of each.
- **Design change if:** either exceeds its assumption: rerun MB-006 with the
  measured value; only if H1/H2 then fail does the standby path change.

---

## Stage 1: unpowered inspection, every unit

### MECH-101 steps 1–2: notch and fingers (look and measure)

Do this the day the boards arrive, before anything else: a trimmed finger
(JLC "optimising" the notch fingers, `card-notch-decision-applied-20260928.md`
lines 45–50) is the one fault that would change the full order.

- **Closes:** MECH-101 (already in the catalogue), steps 1 and 2 of its
  procedure (`card-notch-decision-applied-20260928.md` lines 105–114).
- **Acceptance:** notch width 1.90 ± 0.06 mm (`notch_width_mm` 1.84–1.96,
  line 107); every notch-wall-to-finger gap ≥ **0.10 mm**
  (`notch_gap_min_mm`, David 2026-09-28, catalogue MECH-101); no finger
  trimmed, lifted or with gold/copper exposed at the wall
  (`fingers_trimmed` = 0).
- **Setup:** calipers for the notch width; microscope with the stage
  micrometer for the gaps (calipers are not good enough for 0.10 mm).
- **Procedure:** as the catalogue entry, both faces, A11/B11 and A12/B12;
  photograph each wall with the micrometer in view and attach the images.
- **Sample:** every card type, ≥ 2 each (`units=2` per board); in practice
  all assembled units, it takes minutes.
- **Design change if:** a trimmed finger or a gap under 0.10 mm: stop, and
  compare JLC's post-CAM Gerbers (the "Confirm Production File" step) with
  ours before the full run.

---

## Stage 2: shorts and first power, every unit

The pattern for every board: **resistance of each rail to GND before any
power**, then **first power current-limited**, then the DC rails.

Short screen (all boards): DMM resistance from each rail to GND, both probe
polarities, after the reading settles (capacitors charge); record the
lower. **Proposed limit ≥ 10 Ω:** a solder bridge or a reversed part reads
well under 1 Ω; every rail on these boards has only CMOS loads and should
read hundreds of Ω or more. Also compare the three units: a rail that
differs by more than 3× from the other two is worth a look even if it
passes.

### MB-107: main board, pre-power and first power

- **Closes:** power-up safety for the main board (no gate yet; it protects
  everything after it).
- **Acceptance:** `r_vbus_ohm`, `r_5vsys_ohm`, `r_3v3_ohm`, `r_1v2_ohm`,
  `r_3v3stby_ohm` ≥ 10 Ω (proposed); first-power input current
  `i_first_power_ma` ≤ **250 mA** at 5.0 V, no cards (proposed: the Typ
  column puts the main board's own 3V3 loads near 90 mA,
  `hw/power/design.py` lines 321–325, about 70 mA at 5 V).
- **Setup:** bench supply 5.0 V, current limit 150 mA, into J1 through the
  USB-C breakout (with the CC pins pulled as a 3.0 A source would, so the
  policy logic sees a full source); DMM in series.
- **Procedure:**
  1. Short screen as above.
  2. Power at 150 mA limit. If the supply goes into current limit, remove
     power, find the fault. Otherwise raise the limit to 500 mA.
  3. Press POWER. Check the 5V/3V3/1V2 LEDs. Record the input current
     after 10 s.
- **Sample:** every main board (3).
- **Design change if:** the same short on two boards is a design or
  footprint fault, not assembly.

### MB-101 (existing, amended): main board rails

- **Closes:** MB-101 with numbers instead of "within 5 %".
- **Acceptance:** `v_3v3_v` **3.246–3.390 V** (POW-001's DC range with the
  0.1 % divider, `power.md` line 309; inside `design.V3V3_MIN/MAX`
  3.135–3.465, `design.py` lines 173–174); `v_1v2_v` **1.176–1.224 V**
  (1.2 V ± `RT9013_TOL` 2 %, `design.py` line 189, as `ldo.py` computes it);
  `ripple_3v3_mvpp` ≤ **30 mV** (proposed: twice POW-001's 10–15 mV in
  power-save, `power.md` line 309).
- **Setup:** DMM for DC; M-S for ripple at the buck's output capacitor, no
  bandwidth limit for this one (20 MHz still fine).
- **Sample:** every main board.
- **Design change if:** DC outside the model's range means the tolerance
  stack in `design.py` is wrong: find the part, fix the model, rerun POW-001.

### Card first power: CC-102, GC-103, IC-102, WC-102, SC-101, EC-101, YC-101

- **Closes:** power-up safety for each card; DC rails; idle current against
  each card's budget.
- **Setup:** short screen at the card's fingers (the power fingers to a GND
  finger). Then the card goes into a slot of a main board that has passed
  MB-107/MB-101, **only after that card type has passed MECH-101 steps 3–4**
  (Stage 3: seats, reverse blocked). Supply current limit set to the main
  board's reading plus the card's budget. Card current by M-I.
- **Acceptance:**

| Gate | Short screen (≥ 10 Ω, proposed) | Idle current limit (the budget, source) | DC rail |
|---|---|---|---|
| CC-102 cpu | +3V3, 1V2 | 3V3 ≤ 40 mA (`design.py` line 306) | 1V2 at TP1 1.176–1.224 V (`design.py` line 189) |
| GC-103 gpu | +5V, +3V3, 1V1 | 3V3 ≤ 145 mA (lines 311–312); +5V ≤ 95 mA (`power.md` line 314) | HDMI +5V pin 4.8–5.3 V (`design.py` line 261) |
| IC-102 io | +5V, +3V3, 1V1 | 3V3 ≤ 50 mA (line 313); +5V ≤ 0.80 A (line 141) | keyboard VBUS 4.40–5.5 V (lines 250, 251) |
| WC-102 wifi | +5V, +3V3 | +5V ≤ 340 mA (`power.md` line 314) | 3V3 **3.227–3.411 V** (`wifi-droop-fix-proposal.md` lines 95–96; `wifi_parts.vout_range()`) |
| SC-101 storage | +3V3, 1V1 | 3V3 ≤ 150 mA (lines 314–315) | |
| EC-101 eink | +3V3, 1V1 | 3V3 ≤ 95 mA (line 333) | |
| YC-101 system | +3V3, 1V1 | 3V3 ≤ 50 mA (line 310) | |

  The idle limits are the budgets' maxima, so they only catch gross faults;
  the worst-workload currents are checked in Stage 5.
- **Sample:** every assembled card (3 each).
- **Design change if:** the Wi-Fi 3V3 outside 3.227–3.411 V means the
  0.1 % divider is not fitted (check the BOM) or the VFB model is wrong:
  POW-003 F2 depends on it.

---

## Stage 3: fit and four-terminal resistance (unpowered)

One session with the Kelvin setup covers all of this.

### MECH-101 steps 3–6: insertion, reversal, continuity

- **Closes:** the rest of MECH-101 (`card-notch-decision-applied-20260928.md`
  lines 115–130).
- **Acceptance:** seats by hand in its socket type (`inserts_by_hand` = 1);
  reversed insertion blocked before any finger touches a contact
  (`reverse_blocked` = 1); A11/A12/B11/B12 to the socket's solder tails
  < **1 Ω** (`continuity_max_ohm`, line 123), again after 10 insertion
  cycles (`continuity_10_cycles_max_ohm`); no short to the neighbouring
  finger (`adjacent_shorts` = 0).
- **Setup:** the real main board (unpowered): UMAX x1 C404113 for the I/O
  cards, UMAX x8 C404111 for the CPU card, SOFNG x4 C19188869 for the system
  card.
- **Sample:** every card type, 2 units each.
- **Design change if:** anything binds, and especially the SOFNG x4, whose
  drawing gives no key-rib tolerance (line 125): measure the rib and stop
  the run.

### MB-110: slot contact resistance (x1, x8, x4)

- **Closes:** the slot contact term in GC/SC/EC/YC-005 and CC-005
  (`m1-live-status.md`, B), and the assumption `R_SLOT_CONTACTS`: "3 contacts
  at ≤ 30 mΩ each, plus 10 mΩ card copper" (`hw/power/design.py` line 139).
- **Acceptance:** worst single mated contact ≤ **30 mΩ** in each socket type
  (`r_contact_x1_max_mohm`, `_x8_`, `_x4_`), including the card-side trace
  to the probe point (conservative).
- **Setup:** M-K at 0.5 A. A **bare** card PCB (from the batch's unassembled
  boards) of each outline, seated in the main board's socket: each finger's
  trace ends on a component pad you can probe. Force and sense on the main
  board at the contact's solder tail; force and sense on the bare card at
  that finger's first pad.
- **Procedure:** measure the power contacts (x1: +5V A2/B1/B2, +3V3 A4/B4,
  one GND, `slot.md` lines 20–24; x8: the CPU card's +3V3 B5/B6/B7; x4: the
  system card's +3V3 B1/B2/A2, `system-slot.md` line 104) and A11/A12/B11/B12
  next to the notch. Repeat after 10 insertion cycles, and after the Stage 6
  heat soak. Record the worst.
- **Sample:** 2 main boards × 2 bare cards per socket type.
- **Design change if:** > 30 mΩ: rerun POW-006 and the card power rows with
  the measured value (the slot +5V chain has PTC 40–210 mΩ ahead of it,
  `design.py` line 135, so a small excess is likely harmless); > 100 mΩ, or
  growing with cycles: a socket quality problem, raise it with the maker
  before the full run.

### MB-108: main board input loop (MB-005)

- **Closes:** MB-005's input-loop requirement (David 2026-09-28): the
  board-side loop "J1 terminations + VBUS/GND copper to F1/U2, solder,
  transitions; not the mated contacts" **≤ 60 mΩ at the hottest corner**
  (`hw/power/design.py` lines 64–66; `mb005-loop-requirement-derivation.md`
  lines 165–170). The hot corner is 115 °C (`hw/power/main_input_heat.py`
  line 37).
- **Acceptance:** `r_loop_mohm` ≤ 60 mΩ after the tool scales it to 115 °C,
  i.e. about **44 mΩ measured at 20–25 °C** (× 1.35).
- **Setup:** M-K at 1 A, board unpowered. Positive leg: sense on J1's VBUS
  solder tails and on U2's (TPS25947) IN pin; force into a USB-C plug
  breakout in J1 and out at U2's input capacitor pad. Return leg: sense on
  U2's GND pad and on J1's GND solder tails; force likewise. The mated
  plug contact lies outside the sense points, exactly as the requirement
  excludes it (§4.4.1 counts it in the cable).
- **Procedure:** measure both legs; `r_loop_mohm` = sum; attach both.
- **Sample:** 2 main boards (units 1 and 2).
- **Design change if:** over 60 mΩ hot: the input path widening (A.1) did not
  do enough; widen or pour again. The current route's positive copper alone
  was 73 mΩ hot (`mb005-loop-requirement-derivation.md` line 142), so this
  is the check that proves the reroute.

### CC-103: CPU card 3V3 feed and 1V2 route (CC-005)

- **Closes:** CC-005's "minimum finished copper/via resistance" and "socket
  contact resistance" for the two routed paths
  (`cpu-power-proof-gaps-20260928.md` lines 22–47).
- **Acceptance:**
  - `r_feed_3v3_mohm`: main-board x8 socket +3V3 solder tails (B5/B6/B7) to
    U3 pins 1/3, through the mated contacts ≤ **20 mΩ** (three contacts at
    ≤ 30 mΩ in parallel plus 10 mΩ card copper, the same form as
    `design.py` line 139).
  - `r_1v2_route_mohm`: U3 pin 5 to U1 pin 40 (the farthest VCC pin)
    ≤ **797 mΩ** at 100 °C: the modelled 196.8 mΩ plus the whole remaining
    0.60 Ω allowance (`cpu-power-proof-gaps-20260928.md` lines 24, 37–40).
    That is zero margin: **above 400 mΩ, review** before accepting. The tool
    scales from `board_temp_c` (about 618 mΩ at 25 °C).
- **Setup:** M-K, 1 A for the feed, 0.1 A for the 1V2 route (it carries
  40 mA in use; 0.1 A still gives 20 µV per 0.2 mΩ).
- **Sample:** 2 CPU cards, each in the x8 socket of main board unit 1.
- **Design change if:** the 1V2 route above 400 mΩ hot: add a 1V2 pour or a
  second track; above 797 mΩ it fails outright.

### WC-104: Wi-Fi card return through a mated slot (POW-003 F6, WC-010 T4r)

- **Closes:** **F6** ("routed GND pad/spoke/contact resistance validated",
  `hw/power/buck.py` line 252) and the resistance half of **T4r**
  (`hw/power/thermal.py` lines 152–153), as the proposal asks: a
  four-terminal measurement of U2.2 → J1 and U1.1 → J1 through a mated slot
  (`wifi-droop-fix-proposal.md` lines 142–145).
- **Acceptance:** `r_ret_buck_mohm` (U2 pin 2 to the main board's slot GND
  tails) and `r_ret_esp_mohm` (U1 pin 1 to the same) ≤ **1 Ω** each: the
  model tolerates ≥ 1 Ω of extra return without a rail violation
  (`wifi-droop-fix-proposal.md` lines 118–119, 144). The routed part alone is
  tens of mΩ (`buck.py wifi-card` prints it), so anything above about
  100 mΩ means a poor contact or via: investigate.
- **Setup:** M-K at 1 A. Card seated in main board unit 1, both unpowered.
  Force in at a card GND pad next to U2 (or U1), out at a main-board GND
  point beyond the slot; sense on U2.2 (U1.1) and on a slot GND solder
  tail.
- **Sample:** 2 Wi-Fi cards.
- **Design change if:** > 1 Ω: F1/F2 fail; add GND vias at U2/U1 and J1.
  The measured value also replaces the unbounded contact term in WC-010's
  thermal balance (`thermal.py` lines 129–133); WC-106 measures the heat
  directly anyway.

---

## Stage 4: functional bring-up (existing rows)

Unchanged: MB-102 → MB-103 → MB-104 → MB-105 → CC-101 → MB-106, then GC-101,
IC-101, WC-101 (`debugging.md` §4). They are pass/fail and need no new
limits; they now also write a record (see
[Recording results](#recording-results)) so a check can see they were
done. Stage 5 needs the firmware they load.

Two of them close what the co-simulation deliberately does not model (David,
2026-09-29; `hw/cosim/coverage.py` `BOUNDARY_DECISIONS`): **MB-106** proves
each slot's CARD_RST_n and PROG_n on real cards (`cupc8.py card reset SLOT
--hold` stops the card answering IDENT and `--release` brings it back; the
Wi-Fi card enters its ROM bootloader with PROG_n low), and **WC-101** the
Wi-Fi card's UART0 path (`cupc8.py card flash SLOT FILE --esp` through the
slot mux) and its LINK, TX and RX LEDs, which light at first power-up and
during the join. The emulator has no chip-level reset and QEMU no EN hook,
so neither is an emulator check.

### System-card USB acceptance check (YC-007, first articles)

David accepted the existing system-card USB routing for first articles on
2026-09-30. Keep YC-007's impedance and capacitance-balance failures visible;
functional tests do not establish electrical compliance. The recovered
model passes all 32 cable cases, but capacitance imbalance is 19–26 %
(limit 10 %) and routed impedance is outside the target. Possible symptoms
are failed enumeration, intermittent disconnects or unreliable transfers.

On each first-article system card, record the host, cable, USB-C plug
orientation and test duration. Check repeated attach/enumeration in both
orientations using multiple known-good data cables and more than one host.
Exercise both CDC ports, console input/output and programming/control
transfers, verifying transferred contents and recording errors, unexpected
disconnects and timeouts. Preserve host logs. If symptoms occur, reproduce
them and investigate the USB waveform/layout before a larger manufacturing
run. A working sample does not close the failed impedance/balance checks.

### GC-105: GPU card hot-plug detect and DDC/EDID with a real monitor

Closes the six GPU nets the firmware never touches and the emulator does not
model (`DDC_SCL`, `DDC_SDA`, `HDMI_SCL`, `HDMI_SDA`, `HDMI_HPD`, `HPD_5V`;
`gpu.py` lines 124-141): whether a real monitor's hot-plug line reaches the
RP2040 pin as a high level and its EDID reads through the level shifters.

- **Acceptance** (limits live in `tools/fa_results.py`):
  `hpd_off_v` ≤ **0.4 V** with no sink (R21, 33 kΩ to GND, holds the pin low);
  `hpd_on_v` **2.0-3.6 V** with the monitor on (the 22 kΩ/33 kΩ divider gives
  about 3.0 V from a 5 V sink line; 2.0 V is the RP2040's VIH minimum at
  3.3 V IOVDD, so a sink that only reaches HDMI's 2.4 V minimum would fail:
  that is the finding this row exists to make);
  `ddc_idle_5v_side_v` **4.5-5.3 V** (2.2 kΩ pull-up to HDMI +5V, cable side)
  and `ddc_idle_3v3_side_v` **3.0-3.6 V** (4.7 kΩ to 3V3, RP2040 side) with the
  monitor connected and idle; `edid_bytes_read` ≥ **128**, `edid_header_ok`
  = 1 (`00 FF FF FF FF FF FF 00`), `edid_checksum_ok` = 1 (the 128 bytes sum
  to 0 mod 256; VESA E-EDID).
- **Setup:** the GPU card in a slot of a powered board (or on the bench
  +5V), a real monitor on its HDMI port, the card held in reset so its
  RP2040 does not drive GPIO18-20 (`cupc8.py card reset SLOT --hold`); DMM
  for the voltages; a 3.3 V I2C master (a USB I2C adapter such as a CH341A
  or FT232H, or a Raspberry Pi Pico with an I2C scanner) clipped to the
  RP2040-side DDC nodes, R22 pad 2 (SCL) and R24 pad 2 (SDA), and GND.
- **Procedure:** unplug the monitor, read the HPD node (R21 pad 1) for
  `hpd_off_v`; plug it in and switch it on, read `hpd_on_v`, then the DDC
  nodes at R23 pad 2 / R25 pad 2 (cable side) and R22 pad 2 / R24 pad 2
  (RP2040 side) idle; read 128 bytes from I2C address 0x50, offset 0, and
  check the header and checksum. The read goes monitor, cable, connector,
  2N7002 level shifter, adapter: the whole DDC path except the RP2040 pins,
  which no firmware uses.
- **Sample:** 2 GPU cards on one monitor model; record the monitor's make
  and model in `notes`, and repeat with a second monitor if the first
  fails (a sink that does not raise HPD is a monitor fault, not a card fault).
- **Design change if:** `hpd_on_v` under 2.0 V with a spec-compliant sink
  (the divider passes 60 % of the line, so a sink line under 3.4 V fails):
  raise R21 or drive GPIO18 from a comparator; a failed EDID read with sound
  levels: check the 2N7002 (gate at 3V3, source on the RP2040 side).

---

## Stage 5: power integrity under load

The test firmware needs, per card, a **worst-case load mode** and a
**trigger GPIO** (to be written, see "Who does what"):

| Card | Worst realistic load |
|---|---|
| gpu | DVI running at 252 MHz, full-screen redraw every frame, SPI command stream at full rate |
| io | keyboard enumerated and typing (auto-repeat), SPI at full rate; plus a 500 mA dummy load on the port (IC-104) |
| storage | continuous SD writes of large files |
| eink | continuous full refreshes (7.5" panel if fitted) |
| system | FPGA flash programming + USB traffic + ADC sampling |
| cpu | a tight BASIC loop plus `selftest ram` equivalent traffic (every bus cycle busy) |
| main (chipset) | `selftest ram` (MB-104), SPI transfers to every card, trace capture on |
| wifi | continuous TX (WC-105) |

### WC-105: ESP32 TX current and 3V3 envelope at 40 °C (POW-003 F8, WC-010 T4p)

- **Closes:** **F8** ("ESP32 and other 3V3 load-current envelope validated
  over operating corners", `buck.py` line 255) and **T4p** ("ESP and other
  3V3 load power bounded at the 40 C full-TX corner", `thermal.py` lines
  156–157). Espressif gives only a 25 °C typical 350 mA
  (`wifi_parts.py` lines 90–95).
- **Acceptance:**
  - `ambient_c` ≥ 38 (the 40 °C box).
  - `i3_bound_a` ≤ **0.50 A**: an upper bound on the 3V3 load,
    V₅ × I₅ / V₃ (the buck's efficiency is ≤ 1, so this over-states it).
    The divider design passes at Espressif's 0.5 A supply requirement
    (`wifi-droop-fix-proposal.md` lines 146–149; `wifi_proposal.py` line 57).
  - `v_3v3_burst_min_v` ≥ **3.074 V** and `v_3v3_burst_max_v` ≤ **3.537 V**:
    the model's worst-case envelope for the fitted 0.1 % divider
    (`wifi-droop-fix-proposal.md` line 110). A real unit must land inside
    the worst case; outside means the model is optimistic.
- **Setup:** Wi-Fi card in main board unit 1, the whole machine in the
  40 °C box. Card +5V current at the slot's 50 mΩ sense (M-I), card +5V
  voltage at the card's fingers side of the sense, 3V3 by M-S on C2's pads.
- **Procedure:**
  1. Flash Espressif's RF test firmware over the card's UART bootloader
     (the WC-101 path) and set **continuous TX, 802.11b, maximum power**
     (the case Espressif's Table 6-4 rates). Restore the CUPC/8 firmware
     afterwards.
  2. After 15 minutes at 40 °C, read V₅, I₅ (DMM averages, 10 readings) and
     V₃ (DMM). Record `i3_bound_a`, and V₅ × I₅ as `p_in_w` (info).
  3. Back on CUPC/8 firmware with bursty TX (a large upload through the
     card, trigger GPIO at each TX start): M-S on C2 for the envelope, 1000
     bursts; plus power-up and the burst release for the maximum.
- **Optional WC-105b** (tighter F8): an ESP32-C3-MINI-1U on a breakout,
  3.6 V supply through a 0.1 Ω shunt, in the box, same RF firmware; scope
  across the shunt for the peak current (1 µs average). Acceptance the
  same 0.5 A. Only needed if `i3_bound_a` fails, since the bound includes
  buck losses and LEDs.
- **Sample:** 2 Wi-Fi cards.
- **T4p:** the measured V₅ × I₅ bounds all heat the card makes. Record it;
  WC-010's balance (`thermal.py` line 53) uses 3.6 V × 350 mA = 1.26 W for
  the ESP. If `p_in_w` exceeds 1.26 W, rerun WC-010 with it; WC-106's direct
  temperature is the final word.
- **Design change if:** `i3_bound_a` > 0.5 A (and WC-105b agrees), or the
  3V3 envelope is outside 3.074–3.537 V: the second 22 µF at U1 pin 3
  (`wifi-droop-fix-proposal.md` lines 120–123) and rerun POW-003.

### MB-111 and CC-104: iCE40 1V2 core current, hot (MB-006/CC-006 F2, CC-005)

- **Closes:** the iCE40 core-current envelope for both FPGAs: the main
  board's chipset (U7) and the CPU card (U1). Lattice publishes no maximum
  operating core current (`hw/power/board_thermal.py` lines 11–19), so
  MB-006/CC-006 **F2** stays red until `ICE40_CORE_MAX` (line 58) is set
  from a measurement; CC-005 needs the same number
  (`cpu-power-proof-gaps-20260928.md` lines 78–99).
- **Acceptance:** the shipped bitstreams running their worst realistic load
  in the 40 °C box (`ambient_c` ≥ 38: iCE40 leakage rises with temperature):
  - `i_1v2_core_ma` ≤ **40 mA** sustained: the core budget every rail model
    uses (`design.py` line 197, `I_1V2_MAX`: POW-002, CC-005's 0.60 Ω
    allowance, THM-001 T3). The thermal row alone allows more: the RT9013
    holds Tj ≤ 100 °C up to **108 mA** of 1V2 load, about 107 mA for the
    iCE40 after the resistor branches (`board_thermal.py`
    `rt9013_ceiling()`). Between 40 and ~107 mA F2 passes thermally but
    POW-002 and CC-005 must be rerun with the measured current (a design
    review, not an automatic fail of the board).
  - `v_1v2_min_v` (main, at U7's farthest VCC pin decoupler) and
    `v_1v2_far_min_v` (CPU card, at U1 pin 40's decoupler) ≥ **1.14 V**
    (`design.py` line 192, the iCE40 minimum), by M-S + DMM, including
    configuration (CDONE rising) and the workload.
  - CC-104 also: `t_rt9013_rise_c` ≤ **55 °C** (Tj ≤ 100 °C at 40 °C,
    `design.py` lines 21–22, less a **proposed** 5 °C top-to-junction
    allowance) (CC-006).
- **Setup and method:**
  - **Main (MB-111): the shunt method at the RT9013 output.** R8 is the
    link between `1V2_LDO` and `+1V2` (M-I). Read the shunt voltage with
    the DMM (averaged, 10 readings) during the worst load; also M-S across
    it for the peak (`i_1v2_core_peak_ma`, info).
  - **CPU card (CC-104): the supply-current method.** The card's only
    input is +3V3 through the socket, and an LDO's input current is its
    output current plus a few µA, so the card's 3V3 current (M-I, R7
    difference) is an **upper bound** on its 1V2 current (it also includes
    VCCIO). Record it as `i_1v2_core_ma` with `notes: "upper bound: card
    3V3"`. If the bound exceeds 40 mA, get the real 1V2 figure by
    temporarily lifting U3 pin 5 and bridging it to the 1V2 net through a
    100 mΩ resistor (rework on one card only).
- **Procedure:** 30 minutes in the box at the worst load; then 10 DMM
  readings of the current, the scope envelope over 1000 load events, the
  RT9013 temperature (M-T).
- **Setting the model:** David sets `ICE40_CORE_MAX` from the largest
  sustained measurement across the units, times a margin for the process
  spread that 2–3 parts cannot show (**proposed ×1.25**). The measurement at
  R8 includes the rail's resistor branches, so using it whole for the iCE40
  is conservative.
- **Sample:** 2 main boards, 2 CPU cards.
- **Design change if:** core current > 40 mA: rerun POW-002/CC-005 with it;
  if the CPU 1V2 then falls under 1.14 V, the CC-103 route needs copper.
  Above ~107 mA: the RT9013 is too small thermally (larger package or a
  buck).

### GC-104, IC-103, SC-102, EC-102, YC-102: RP2040 DVDD load step and card rails (GC/IC/SC/EC/YC-005, -006)

- **Closes:** the RP2040 internal regulator gaps: "RP2040 VREG 1.20 V
  transient/droop model at 252 MHz" (GPU), "SD-card load-step and RP2040
  internal regulator model" (storage), "panel load-step ..." (e-ink),
  "RP2040 internal regulator transient model" (system)
  (`hw/tools/boardcheck.py` lines 32–36), and the thermal gap "RP2040
  internal regulator dissipation at maximum board load" (lines 37–38). The
  datasheet gives no load-step response, output impedance or maximum DVDD
  current (`hw/power/rp2040_vreg.py` lines 25–28), so only a measurement
  bounds them.
- **Acceptance:**
  - `dvdd_dc_v` within VSEL ± 3 % (`rp2040_vreg.py` line 42, Table 192):
    GPU **1.164–1.236 V** (VSEL 1.20 V, the declared overclock, line 53;
    `fw/rp2040/gpu/main.c` line 191); the other cards **1.067–1.133 V**
    (the 1.10 V default, line 46).
  - `dvdd_dev_mv` ≤ **100 mV** peak deviation from DC during the workload:
    "short-term transients within ±100 mV" (`rp2040_vreg.py` line 14,
    Table 634).
  - `v_3v3_card_min_v` ≥ **3.135 V** at the card (`design.py` line 173); this
    is also the SD card's and the panel's supply.
  - `i_3v3_max_ma` ≤ the card budget (the table in Stage 2).
  - `tc_rp2040_rise_c` ≤ **45 °C**: case 85 °C maximum (`rp2040_thermal.py`
    line 60, Table 624) at 40 °C ambient.
  - EC-102 also `v_panel_min_v` ≥ **2.3 V** during a refresh (the panel's
    minimum, `eink-card.md` lines 58–59).
- **Setup:** M-S on 1V1: the RP2040 cards have no 1V1 test pad
  (`hw/boards/rp2040card.py` lines 286–289), so probe the 1V1 pad of the
  DVDD decoupler next to pin 50 (C13) or pin 23 (C12) with its own GND pad
  (`rp2040card.py` lines 97–104); the system card has TP7 1V1 and TP6 GND
  (`hw/boards/system.py` lines 97–98). 3V3 on the card's 3V3 decoupler.
  Card current by M-I. RP2040 case by M-T.
- **Procedure:** worst load (table above) for 30 minutes (rise at room
  ambient + 40 °C is acceptable here; GPU: do it inside GC-102's box run);
  DMM DC of 1V1 and 3V3; M-S envelopes over 1000 events, triggered on the
  load event (SD write start, refresh start, frame start, flash block
  write); current; temperature.
- **Sample:** 2 of each card.
- **Design change if:** DVDD deviation > 100 mV: more DVDD decoupling at
  pins 23/50 (the footprint has room for a second 1 µF next to C13/C14
  only with a placement change). 3V3 under 3.135 V at the card: the slot
  +3V3 path (MB-110) or the main buck. Case temperature over: reduce the
  load (GPU: this would retire the overclock).

### IC-104: keyboard port under load and short (IC-005, POW-007)

IC-005's switch is the TPS2553DBVR-1 (David approved the proposal,
2026-09-29). Run against the fitted part.

- **Closes:** IC-005's "current limit; fault flag on short" on the real part,
  and POW-007's port voltage.
- **Acceptance:** `v_vbus_500ma_min_v` ≥ **4.40 V** at 500 mA
  (`design.py` line 250, USB 2.0 low-power port; POW-007); slot +5V at that
  load `i_slot_5v_500ma_a` ≤ **0.80 A** (`design.py` line 141, slot.md);
  port limit `i_port_trip_a` ≥ **0.50 A** (`design.py` line 336,
  `I_KEYBOARD`); fault flag asserted on a hard short
  (`fault_flag_on_short` = 1); boost and switch top rises ≤ **55 °C**
  (Tj ≤ 100 °C less the proposed 5 °C) at 500 mA.
- **Setup:** electronic load on the keyboard port through a USB-A breakout;
  slot +5V by M-I; M-T on U7 (TPS61023) and the switch.
- **Procedure:** 0 → 500 mA steps, read VBUS; 30 min at 500 mA for heat;
  ramp in 10 mA steps to the trip; then a short (load at max) for 1 s,
  check the fault flag over SPI/UART and recovery.
- **Sample:** 2 IO cards.
- **Design change if:** trip under 0.5 A or no fault flag: the IC-005
  replacement.

### MB-113: reset thresholds (MB-051 confirmation)

For the fitted MB-051 dual-rail qualifier (`hw/power/reset_supervisor.py`).

- **Closes:** confirms MB-051 on hardware: reset asserts before a rail
  leaves its valid range and never inside the regulator's range.
- **Acceptance:** falling trips `v_3v3_fall_trip_v` **3.1698–3.2035 V** and
  `v_1v2_fall_trip_v` **1.1507–1.1604 V**, the outward-rounded modeled
  windows from `python3 hw/power/reset_supervisor.py` (2026-09-30); and all six
  SLOTn_RST_n held low while nPOR is low (`slot_rst_held` = 1). Update these
  numbers if the design changes before the order.
- **Setup:** on main board unit 1, remove R7 (then R8) and feed `+3V3`
  (`+1V2`) from the bench supply at the link's load-side pad; DMM at the
  rail-side sense pad R113.1 (`+3V3`) or R116.1 (`+1V2`); scope on nPOR.
  The 1V2 window is 9 mV wide: the supply
  needs 1 mV steps, or add a 1 Ω 10-turn rheostat in series and trim with it.
- **Procedure:** from nominal, lower in 1 mV steps (5 s each) until nPOR
  falls, then refine the crossing to 0.1 mV with the trim resistor; record
  the rail at that moment. Raise until release (hysteresis, info). Check
  the slot resets at the slot pins. Repeat after at least 30 minutes at
  38 C or warmer in the 40 C box, recording `minutes_hot` (at least 30),
  `ambient_hot_c` (at least 38 C),
  `v_3v3_fall_trip_hot_v` and `v_1v2_fall_trip_hot_v` against the same bands.
  Record room temperature as `ambient_room_c` (15–35 C).
  TI's OPA376 input-bias hot data is typical; the model's 1 nA allowance
  is an engineering assumption that this hot test must confirm. The
  30-minute soak is an engineering qualification minimum; keep soaking if
  the monitor temperatures have not stabilized (M-T).
- **Sample:** 2 main boards.
- **Design change if:** a trip outside its window: the tolerance stack in
  `reset_supervisor.py` is wrong; fix the model and the ladder.

---

## Stage 6: heat, stress and burn-in

### MB-109: input copper at the eFuse limit (MB-005 heating)

**Can damage the board.** Run on unit 1 only, after everything else on it.

- **Closes:** MB-005's thermal half: "≤ 20 C copper rise at 3.289 A"
  (`hw/power/design.py` lines 64–66;
  `mb005-loop-requirement-derivation.md` lines 99–134). A load just under
  the eFuse limit is a continuous condition, so the copper must survive it
  in steady state.
- **Acceptance:** `dt_input_copper_c` ≤ **20 °C** after the tool scales it by
  (`design.insw_ilim()[2]` / `i_load_a`)² (3.288102 A before outward rounding) (I²R heating). The unit's eFuse limits somewhere
  between 2.565 and 3.289 A (including RILM tolerance/TCR; `power.md`), so load it just under
  its own limit; `i_load_a` ≥ 2.5 A for the scaling to be meaningful.
- **Setup:** bench supply 5.0 V, limit 4 A, into J1 through the 5 A USB-C
  breakout (short, ≥ 20 AWG). Electronic load on 5V_SYS taken at the
  5V_SYS side of R4 (not through R4: a 1206 0 Ω jumper is typically rated
  about 2 A). Thermocouples on the J1–F1 track and on the F1–U2 track (outer
  layer), each ≥ 3 mm from J1, F1 and U2 so their own heat is not counted;
  ambient thermocouple. IR camera first to find the hottest point.
- **Procedure:** raise the load in 0.2 A steps to where 5V_SYS starts to
  sag (the eFuse limiting), back off 50 mA; hold 15 minutes to steady state;
  record the current and the hottest track rise.
- **Sample:** 1 main board.
- **Design change if:** over 20 °C scaled: widen or pour the input path
  further (≥ 1.75 mm outer at finished-minimum copper,
  `mb005-loop-requirement-derivation.md` lines 127–130).

### WC-106: Wi-Fi board temperature under sustained TX (WC-010 T4c)

- **Closes:** **T4c** ("measured or calibrated ESP-to-buck thermal transfer
  bound supplied", `hw/power/thermal.py` line 154). No published model
  bounds this board (`wifi-droop-fix-proposal.md` lines 150–153):
  Tj(U2) = T_board + ψJB (40.6 °C/W) × P_U2.
- **Acceptance:** `t_u2_board_rise_c` ≤ **50 °C** (i.e. T_board ≤ 90 °C at
  40 °C ambient). With Tj ≤ 100 °C (`design.py` line 22) that leaves 10 °C
  for ψJB × P_U2, which covers P_U2 up to 246 mW: over four times the
  modelled worst buck loss (58 mW at 5.5 V in, `thermal.py` `buck_loss`).
  No need to measure P_U2 unless the rise is close.
- **Setup:** M-T, thermocouple on U2's GND lead (pin 2) or the copper
  touching it; a second on the ESP module's shield (info:
  `t_esp_shield_rise_c`); the machine in the 40 °C box (or at room + 40 °C;
  but the ESP current is hotter-higher, so the box is better, and WC-105
  already needs it). If an enclosure exists, inside it.
- **Procedure:** continuous TX (WC-105 firmware) for 30 minutes, until
  steady; record the rise.
- **Sample:** 2 Wi-Fi cards.
- **Design change if:** over 50 °C: a copper pour under U2 tied to GND with
  vias, or move U2 away from the module.

### MB-112: main board thermal soak (MB-006)

- **Closes:** MB-006's "package-to-board/enclosure theta ... copper/pad/contact
  loss and neighbouring heat unbounded" (`hw/power/thermal_bind.py`
  line 250): the main regulators at the M1 worst load.
- **Acceptance:** 5V_SYS load `i_5vsys_a` ≥ **1.74 A** (the M1 worst case
  1.737 A, `power.md` line 314); top-of-package rises ≤ **55 °C** for the
  eFuse U2, the 3V3 buck, the HT7533 and the RT9013 (Tj ≤ 100 °C at 40 °C
  less the proposed 5 °C). The models predict 63.1, 52.2, (H2) and 62.2 °C
  junction (`power.md` line 317), so the expected rises are 12–25 °C.
- **Setup:** all four M1 cards running their worst loads; an electronic
  load on an empty slot's +5V makes up the rest of the 1.74 A (≤ 0.8 A per
  slot). M-T on each part.
- **Procedure:** 60 minutes; record rises; also redo MB-110 afterwards.
- **Sample:** 1 main board (unit 2, clean).
- **Design change if:** a rise over 55 °C: rerun the thermal row with the
  measured θ and add copper; if the buck is the part, `TLV62569PDDCR` is
  already the larger package.

### GC-102: GPU DVI burn-in at 40 °C (per unit)

- **Closes:** the per-unit qualification of the declared 252 MHz / 1.20 V
  overclock (`power.md` lines 275–296; `rp2040_vreg.py` line 53,
  `OVERCLOCK`; `verification.md` §5 "RP2040 at 252 MHz").
- **Acceptance:** `minutes` ≥ **60** of DVI output with `ambient_min_c` ≥ 38
  (~40 °C), `glitches` = `dropouts` = `lockups` = **0**, and the RP2040 case
  `tc_rp2040_c` ≤ **85 °C** (Table 624, `rp2040_thermal.py` line 60)
  measured at the end.
- **Setup:** GPU card in the machine in the 40 °C box; HDMI out through the
  box wall to the capture device on a PC; UART or `cupc8.py card ident`
  polled every second (a lockup is 3 missed IDENTs).
- **Procedure:** the GC-101 test pattern plus a moving element; a script
  compares every captured frame with the expected one (with a tolerance
  for the capture's compression) and counts frames that differ
  (`glitches`) and lost signal (`dropouts`). The script is a follow-up; until
  it exists, record the video and review it at 4×.
- **Sample:** **every** GPU card that will be used; the first articles are
  the first three. A card that fails is not used as a GPU card.
- **Design change if:** failures on more than one unit of three: the
  overclock is not safe as a requirement. Options: lower resolution / a
  pixel-doubled mode at a lower clk_sys, or a different GPU part.

---

## Recording results

### Layout

```
doc/hardware/fa-results/
  <TEST-ID>/                       one folder per gate, e.g. WC-103/
    <unit>-<YYYY-MM-DD>.json       one record per unit per session
    <unit>-<YYYY-MM-DD>-*.csv|png  attachments: scope captures, photos
```

`<unit>` is the board's serial (write it on the silk with a marker:
`MAIN-FA1`, `WIFI-FA2`, ...) or, for loose parts, `<LCSC>-<lot>-<n>`.

### Record

```json
{
  "schema": "cupc8-fa/1",
  "test": "WC-104",
  "board": "wifi",
  "unit": "WIFI-FA1",
  "date": "2026-10-20",
  "operator": "David Kaplan",
  "evidence": "sha256 of build/hw/wifi/evidence.json the batch was ordered from",
  "ambient_c": 22.5,
  "instruments": ["UNI-T UT61E+ (V)", "Bench DMM (I, series)", "RD6006 (1.000 A CC)"],
  "measurements": {
    "r_ret_buck_mohm": 38.2,
    "r_ret_esp_mohm": 41.0
  },
  "attachments": ["WIFI-FA1-2026-10-20-probe-points.png"],
  "notes": "sense on U2.2 pad and slot 3 GND tail B3; current reversed"
}
```

- `measurements` holds **numbers only**, named exactly as in each
  measurement above (`python3 tools/fa_results.py --list <TEST>` prints the
  required ids and limits). 1/0 for yes/no items. Extra ids (for example
  `p_in_w`, `i_1v2_core_peak_ma`) are kept and ignored by the gate.
- The **limits live in `tools/fa_results.py`**, not in the record, so a
  record cannot pass itself; the tool applies the copper scaling (`cu`, to
  the model's hot corner from `board_temp_c`) and the I²R scaling (`i2`,
  MB-109).
- A failed record is never deleted. If it was a measurement error, add
  `"void": "<reason>"` and measure again; the gate ignores void records.
- Human narrative (what was seen, photos) can go in a bring-up log
  (`doc/hardware/bringup.md`, which the existing hw rows name); the JSON is
  what the gates read.

### Turning gates green

- `python3 tools/fa_results.py [TEST ...]` prints each gate as green, red or
  pending and exits 0 only if all named gates are green. Tested by
  `test/test_fa_results.py`.
- The proposed catalogue entries below run it as their `cmd`.
- For the analysis rows that are red for want of these numbers (POW-003
  F5–F8, WC-010 T4c/T4p/T4r, MB-006/CC-006 F2, CC-005, the RP2040 -005/-006
  gaps in `boardcheck.py`), the follow-up is to make each check read its FA
  gate: for example `wifi_parts.guaranteed('esr_max')` true when WC-103 is
  green, `ICE40_CORE_MAX` set from the MB-111/CC-104 records, `boardcheck.py`
  GAPS entries cleared by the matching -104/-103/-102 gates. That is a
  source change in `hw/`, left for when the first records exist.

## Proposed catalogue entries

Not added to `test/catalogue.toml` (this task does not edit it). IDs checked
against the catalogue on 2026-09-28: existing hw rows are MB-101..106,
CC-101, GC-101, IC-101, WC-101 and MECH-101; none of the ids below exists.
GC-102 is the id `power.md`, `verification.md` and `rp2040_vreg.py` already
use for the burn-in. **Collision risk:** the GPU agent (live status A.2) was
asked to add "a per-card DVI burn-in hw test (GC-1xx)": it should use GC-102
as defined here, or this plan renumbers.

Every entry has `kind = "hw"`, `vrow = "5"` and
`method = "manual per doc/hardware/first-article-plan.md, recorded in doc/hardware/fa-results/<ID>/"`,
and `cmd = "python3 tools/fa_results.py <ID>"`. Only `id`, `title` and
`checks` differ:

| id | title | checks |
|---|---|---|
| MB-107 | First article: main board shorts and first power | each rail to GND >= 10 ohm unpowered; first power at 5.0 V, no cards, <= 250 mA |
| MB-108 | First article: main board input loop resistance | four-terminal J1 tails -> U2 IN plus U2 GND -> J1 GND tails, scaled to 115 C, <= 60 mOhm (MB-005) |
| MB-109 | First article: input copper heating at the eFuse limit | input track rise at just under the unit's eFuse limit, scaled to 3.289 A by I^2, <= 20 C (MB-005) |
| MB-110 | First article: slot contact resistance | four-terminal worst mated contact in the x1, x8 and x4 sockets <= 30 mOhm, also after 10 cycles and the heat soak (design.R_SLOT_CONTACTS) |
| MB-111 | First article: chipset iCE40 1V2 core current, hot | at 40 C ambient, worst load: RT9013 output current via R8 <= 40 mA sustained; 1V2 at U7 >= 1.14 V (MB-006 F2) |
| MB-112 | First article: main board thermal soak | 5V_SYS >= 1.74 A for 60 min: eFuse, 3V3 buck, HT7533 and RT9013 top rise <= 55 C (MB-006) |
| MB-113 | First article: reset thresholds | two main boards at room temperature and after >= 30 min at >= 38 C: 3V3 falling trip 3.1698-3.2035 V, 1V2 1.1507-1.1604 V, slot resets held while nPOR low; qualifies the modeled OPA376 bias allowance (MB-051) |
| MB-114 | First article: 3V3_STBY part currents | MAX16054 supply <= 15 uA and HT7533-2 ground current <= 20 uA at 60 C, 5 parts each (MB-006 H1/H2) |
| CC-102 | First article: CPU card shorts and first power | 3V3, 1V2 to GND >= 10 ohm; idle 3V3 <= 40 mA; 1V2 1.176-1.224 V |
| CC-103 | First article: CPU card 3V3 feed and 1V2 route resistance | four-terminal: x8 +3V3 tails -> U3 <= 20 mOhm; U3.5 -> U1.40 <= 797 mOhm at 100 C (CC-005) |
| CC-104 | First article: CPU card iCE40 1V2 current and far-pin voltage, hot | at 40 C ambient, worst load: 1V2 current <= 40 mA (card 3V3 bound), U1.40 >= 1.14 V, RT9013 rise <= 55 C (CC-005, CC-006 F2) |
| CC-105 | First article: CPU card 1V2 capacitors under bias | C22 >= 1.88 uF at 1.2 V/25 C, ESR >= 5 mOhm; C21 >= 1.0 uF at 3.3 V; 5 parts each (CC-005) |
| GC-102 | Per unit: GPU card DVI burn-in at 40 C | 60 min DVI at >= 38 C ambient: no glitches, dropouts or lockups; RP2040 case <= 85 C; every GPU card used |
| GC-103 | First article: GPU card shorts and first power | +5V, 3V3, 1V1 to GND >= 10 ohm; idle 3V3 <= 145 mA, +5V <= 95 mA; HDMI +5V 4.8-5.3 V |
| GC-104 | First article: GPU RP2040 DVDD and rails under load | DVDD 1.164-1.236 V DC, <= 100 mV deviation at 252 MHz; card 3V3 >= 3.135 V; 3V3 <= 145 mA; case rise <= 45 C (GC-005, GC-006) |
| GC-105 | First article: GPU card hot-plug detect and DDC/EDID | with a real monitor: HPD at the RP2040 pin <= 0.4 V unplugged and 2.0-3.6 V plugged; DDC idle 4.5-5.3 V (cable side) and 3.0-3.6 V (RP2040 side); a 128-byte EDID with a valid header and checksum reads through the level shifters (co-sim waivers for GPU DDC/HPD) |
| IC-102 | First article: IO card shorts and first power | +5V, 3V3, 1V1 to GND >= 10 ohm; idle 3V3 <= 50 mA, +5V <= 0.80 A; keyboard VBUS 4.40-5.5 V |
| IC-103 | First article: IO RP2040 DVDD and rails under load | DVDD 1.067-1.133 V DC, <= 100 mV deviation; card 3V3 >= 3.135 V; 3V3 <= 50 mA; case rise <= 45 C (IC-005, IC-006) |
| IC-104 | First article: keyboard port under load and short | VBUS >= 4.40 V at 500 mA; slot +5V <= 0.80 A; limit >= 0.50 A; fault flag on short; boost/switch rise <= 55 C (IC-005, POW-007) |
| WC-102 | First article: Wi-Fi card shorts and first power | +5V, 3V3 to GND >= 10 ohm; idle +5V <= 340 mA; 3V3 3.227-3.411 V |
| WC-103 | First article: C45783 22 uF under bias | at 25 C: >= 7.80 uF at 5.5 V, >= 11.16 uF at 3.6 V, ESR <= 150 mOhm at 1-2 MHz; 10 parts of the lot (POW-003 F5/F7) |
| WC-104 | First article: Wi-Fi return resistance through the slot | four-terminal U2.2 and U1.1 -> main-board slot GND tails <= 1 ohm each (POW-003 F6, WC-010 T4r) |
| WC-105 | First article: ESP32 TX current and 3V3 envelope at 40 C | continuous TX at >= 38 C: V5 x I5 / V3 <= 0.50 A; bursty TX 3V3 within 3.074-3.537 V (POW-003 F8, WC-010 T4p) |
| WC-106 | First article: Wi-Fi buck board temperature under TX | 30 min continuous TX: U2 GND-lead rise <= 50 C (WC-010 T4c) |
| SC-101 | First article: storage card shorts and first power | 3V3, 1V1 to GND >= 10 ohm; idle 3V3 <= 150 mA |
| SC-102 | First article: storage RP2040 DVDD and rails during SD writes | DVDD 1.067-1.133 V DC, <= 100 mV deviation; card 3V3 >= 3.135 V; 3V3 <= 150 mA; case rise <= 45 C (SC-005, SC-006) |
| EC-101 | First article: e-ink card shorts and first power | 3V3, 1V1 to GND >= 10 ohm; idle 3V3 <= 95 mA |
| EC-102 | First article: e-ink RP2040 DVDD and rails during refresh | DVDD 1.067-1.133 V DC, <= 100 mV deviation; card 3V3 >= 3.135 V; 3V3 <= 95 mA; panel >= 2.3 V; case rise <= 45 C (EC-005, EC-006) |
| YC-101 | First article: system card shorts and first power | 3V3, 1V1 to GND >= 10 ohm; idle 3V3 <= 50 mA |
| YC-102 | First article: system RP2040 DVDD and rails under load | DVDD 1.067-1.133 V DC, <= 100 mV deviation; card 3V3 >= 3.135 V; 3V3 <= 50 mA; case rise <= 45 C (YC-005, YC-006) |

Amendments to existing rows (text only):

- **MB-101** `checks`: "3V3 3.246-3.390 V, 1V2 1.176-1.224 V, 3V3 ripple
  <= 30 mVpp, rail LEDs on"; `cmd = "python3 tools/fa_results.py MB-101"`.
- **MECH-101** `method`: "... recorded in doc/hardware/fa-results/MECH-101/";
  `cmd = "python3 tools/fa_results.py MECH-101"`.

Example, for the TOML:

```toml
[[test]]
id = "WC-103"
title = "First article: C45783 22 uF under bias"
checks = "at 25 C: >= 7.80 uF at 5.5 V, >= 11.16 uF at 3.6 V, ESR <= 150 mOhm at 1-2 MHz; 10 parts of the lot (POW-003 F5/F7)"
method = "manual per doc/hardware/first-article-plan.md, recorded in doc/hardware/fa-results/WC-103/"
kind = "hw"
vrow = "5"
cmd = "python3 tools/fa_results.py WC-103"
```

Per board: main 8 new + MB-101 amended; cpu 4; gpu 4; io 3; wifi 5;
storage 2; eink 2; system 2; MECH-101 amended. 30 new entries.

## Gate coverage

| Open gate / check | Closed by |
|---|---|
| POW-003 F5 (ESR max), WC-005 | WC-103 |
| POW-003 F6 (return resistance) | WC-104 |
| POW-003 F7 (effective C), WC-005 | WC-103 |
| POW-003 F8 (load envelope) | WC-105 (WC-105b if needed) |
| POW-003 F1/F2 (confirmation on hardware) | WC-102 (DC), WC-105 (envelope) |
| WC-010 T4c | WC-106 |
| WC-010 T4p | WC-105 |
| WC-010 T4r | WC-104 (resistance) + WC-106 (heat, directly) |
| CC-005: socket contact resistance | MB-110 (x8), CC-103 (feed) |
| CC-005: finished copper/via resistance | CC-103 |
| CC-005: C22/C1–C4 capacitance and ESR | CC-105 |
| CC-005: iCE40 core-current envelope | CC-104 |
| CC-006 / MB-006 F2 (iCE40 core maximum) | CC-104, MB-111 |
| MB-006 H1/H2 (3V3_STBY currents) | MB-114 |
| MB-006 (board θ, neighbours) | MB-112 |
| MB-005 loop ≤ 60 mΩ | MB-108 |
| MB-005 rise ≤ 20 °C at 3.289 A | MB-109 |
| MB-051 | MB-113 (confirmation) |
| GC/IC/SC/EC/YC-005 RP2040 DVDD load step | GC-104, IC-103, SC-102, EC-102, YC-102 |
| SC-005 SD current; EC-005 panel current | SC-102, EC-102 (card 3V3 current and droop) |
| GC/IC/SC/EC/YC-005 slot contact resistance | MB-110 (x1, x4) |
| GC/IC/SC/EC/YC-006 RP2040 dissipation | the same -104/-103/-102 (case rise) |
| GC-005 overclock per unit | GC-102 |
| GPU DDC/EDID and hot-plug detect (co-sim waivers, David 2026-09-29) | GC-105 |
| Slot CARD_RST_n / PROG_n and the Wi-Fi ESP32 EN/BOOT, LEDs and UART0 (co-sim waivers, David 2026-09-29) | MB-106, WC-101 (amended) |
| IC-005 limit and fault flag | IC-104 |
| MECH-101 notch fit | MECH-101 |

## What first articles cannot close

- **Population, not proof.** Two or three units show that this lot works
  and that the models are not optimistic; they do not bound the process
  spread of a later lot. The part-lot gates (WC-103, CC-105, MB-114) use
  5–10 samples for that reason, and the iCE40 figure takes a proposed
  ×1.25 margin. A later production run from a different lot should repeat
  WC-103 and CC-105 on a few parts.
- **Board-maker copper minimum.** MB-108 and CC-103 measure this batch's
  copper, not JLC's guaranteed minimum finished thickness, which they do
  not publish. The hot-corner scaling covers temperature, not a thinner
  future lot.
- **TMDS signal quality.** A 100 MHz scope cannot see a 252 Mb/s eye;
  GC-102 tests the outcome (a stable picture) instead.
- **ESP32 maximum across process.** WC-105 measures these modules; only
  Espressif could give a maximum.
