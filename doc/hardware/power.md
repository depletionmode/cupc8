# Power (Milestone 1)

## Input and distribution

```
USB-C receptacle (main board)
  │  CC1/CC2: 5.1 kΩ Rd each (sink). Also to sysctl ADC pins to read the
  │           source's advertised current.
  ├─ TVS (SMF5.0A) + 3.5 A input PTC (SMD1812P350TF/16)
  └─ eFuse (TPS259470ARPWR): 2.63–3.21 A limit, OVLO 5.60–5.81 V, dVdt soft start
       │  ≤ 10 µF directly on VBUS; the rest charges behind the dVdt ramp
       └── 5V_SYS ──┬── 3V3 buck (TLV62569PDDCR, 2 A)
                    │     └── 3V3 ──┬── 1V2 LDO ── chipset iCE40 core (+ PLL filter)
                    │               ├── RP2040 sysctl, SRAM, ROM, W25Q32, LEDs
                    │               ├── CPU socket +3V3 → CPU card (own 1V2 LDO)
                    │               └── slots +3V3 (≤ 300 mA each)
                    ├── CPU socket +5V
                    └── slots +5V, each via a 1.1 A PTC + 0 Ω link + 50 mΩ sense
```

- **Rail LEDs:** each rail (5V_SYS, 3V3, 1V2, and the CPU card's 1V2) has an
  LED and a test pad.
- **Isolation:** each rail and each slot has a 0 Ω isolation link, so
  bring-up can power one section at a time.
- **USB data:** USB-C D+/D− go to the sysctl RP2040 only.

## Current budget

Maximum values are datasheet max or conservative estimates. Typical values
are what we expect at 12 MHz. The per-part datasheet numbers are checked
during schematic capture and entered in `hw/power/budget.py`, which recomputes
this table.

| Load | Rail | Typ mA | Max mA |
|---|---|---|---|
| Chipset iCE40HX4K core | 1V2 (from 3V3) | 15 | 40 |
| Chipset iCE40HX4K I/O (≈95 pins, 12 MHz) | 3V3 | 15 | 40 |
| CPU card iCE40HX4K core + I/O | 3V3 | 15 | 40 |
| SRAM IS62WV5128EBLL | 3V3 | 10 | 22 |
| ROM SST39VF040 (read, or program when stalled) | 3V3 | 10 | 30 |
| W25Q32 config flash | 3V3 | 2 | 15 |
| sysctl RP2040 + flash | 3V3 | 25 | 50 |
| GPU card RP2040 @ 252 MHz + flash | 3V3 | 60 | 100 |
| GPU card TMDS drive (4 pairs into the monitor's 50 Ω / 3.3 V termination) | 3V3 | 30 | 45 |
| IO card RP2040 (USB host) + flash | 3V3 | 25 | 50 |
| Storage card RP2040 + flash | 3V3 | 25 | 50 |
| Storage card microSD: ~1 mA idle, up to ~100 mA reading or writing | 3V3 | 5 | 100 |
| I²C expanders, SWD mux | 3V3 | 1 | 5 |
| LEDs (~16 at 1–2 mA) | 3V3 | 15 | 30 |
| **3V3 total** | | **272** | **617** |
| 3V3 buck input at 90% efficiency (5.0 V; 535 mA max at the worst-case 4.23 V) | 5V | 200 | 452 |
| USB keyboard VBUS, through the IO card's boost (500 mA at the port: 746 mA from +5V at the worst corner) | 5V | 110 | 746 |
| HDMI +5V pin (sink EDID power, 55 mA per spec), through the GPU card's PTC and buck-boost (95 mA from +5V at the worst corner) | 5V | 10 | 95 |
| Wi-Fi card (ESP32-C3 via its own TLV62569 buck from +5V; TX peaks, ~260 mA at 5 V) | 5V | 80 | 350 |
| Slots 5–6 (future cards; not in M1) | 5V | 0 | — |
| **Total from USB-C (M1 cards)** | 5V | **≈ 400** | **≈ 1740** (worst-case corner, POW-006) |

The worst case assumes a keyboard drawing the full 500 mA (e.g. an RGB
gaming keyboard), Wi-Fi transmitting at 100 % duty and the SD card writing,
with the HDMI card in the graphics slot. The e-ink card (`proposals/eink-gpu.md`:
~45 mA typical, ~95 mA max, all from +3V3, nothing from +5V) takes 105 mA
less than that. With an ordinary keyboard (< 100 mA) the maximum is about
**1.0 A**.

**The storage card** (`storage-card.md`, slot 4 in M1) adds up to 150 mA of
+3V3 (its RP2040 and a microSD card), well inside a card's 300 mA. With it
the machine no longer fits a 1.5 A source with margin, so **the full M1
machine needs a USB-C 3.0 A source** (David, 2026-09-24; below).

Future cards in slots 5–6 must declare their budget. sysctl sums the declared
budgets and compares them with the advertised source current.

## Source requirements

`PWR_HI` means **a Type-C 3.0 A source**. The main board's TLV7011 compares
the CC line with a threshold between the 1.5 A and 3.0 A ranges (~1.30 V on
CC; POW-005), so the policy holds with or without the system card. The
chipset shows it in `SYSCTL` bit 1 ($f203). sysctl still reports the exact
class from its ADC (`cupc8.py power`).

| Source advertises | PWR_HI | What runs |
|---|---|---|
| 3.0 A Type-C current | high | Everything, with ~1.0 A left for slots 5–6 to declare (POW-006) |
| 1.5 A Type-C current | low | The machine, keyboard, display and storage **reads** (LOAD, DIR). The kernel keeps the radio off ("USB power under 3A: net off") and refuses SD **writes**: SAVE and DEL say "USB power under 3A: SD writes off". Worst case in this mode: 1.11 A (26 % under 1.5 A, POW-006 B5). |
| Default USB power (500 mA USB 2 / 900 mA USB 3) | low | The same as 1.5 A, but **not guaranteed**: at the max budget, with the radio off and the SD idle, the machine draws 606 mA with a 100 mA keyboard (USB 2.0's 500 mA) and 1.02 A with a 500 mA one (USB 3's 900 mA) (POW-006 B6/B7, failing until decided). At typical loads it fits. |

Why reads stay allowed and writes don't: a microSD card can draw as much
reading as writing (up to ~100 mA, so B5 counts it either way), but a
brown-out in the middle of a read loses nothing. One in the middle of a write
can leave the file system damaged.

## Checks (part of `make verify`, section E)

- **ngspice and worst-case scripts** in `hw/power/`, run as POW-001…006 and
  THM-001 (verification rows 4.4 and 4.5). Results are below.
- **Sequencing:** the iCE40 HX power-up sequence is checked against the
  Lattice datasheet. The RP2040 boots from 3V3 alone.
- **Brown-out:**
  - sysctl holds /CPU_RST and CARD_RST_n until all rails are within 5%.
  - The 1V2 rail is monitored by sysctl through a divider into an ADC input.

## Verification results (rows 4.4 and 4.5)

Run with `test/run.py POW THM`, or each script on its own (for example
`python3 hw/power/budget.py`). Every check prints its value, its limit and
the margin. The values and their sources (datasheet, spec, board script, or
assumption) are in `hw/power/design.py`.

**Models.** The 3V3 bucks, the IO card's keyboard boost and the PWR_HI
comparator use TI's own PSpice models (TLV62569, TPS61023, TLV7011). The
GPU card's TPS63802 is behavioural: TI's model does not run in ngspice
(POW-008 below).
`hw/power/models/fetch.py` downloads them from pinned URLs, checks their
SHA-256, and ports them to ngspice. They aren't committed, because TI's
licence doesn't grant redistribution. There is no vendor model for the
RT9013, and the input eFuse's inrush check (POW-004) uses a behavioural
switch with its datasheet slew rate, limit and RON. These are
**behavioural** models (`hw/power/models/behavioural.lib`) built from
datasheet figures:
- the LDO's output impedance is fitted to its datasheet load-step figure.
  Each run re-simulates that figure first.
- the LDO model has no control loop, so it says nothing about stability.

The TI buck model's switches are 10 mΩ rather than 100/60 mΩ, so buck losses
come from the datasheet RDS(on) and not from the simulation.

As of 2026-09-25 every test passes. POW-006 B5 (the 1.5 A source case)
passes at 7.8 % against a 5 % margin, under a waiver
(`fab-waivers.md`, David 2026-09-25).

**The input path, re-sized for 3 A.** The SY6280 (limit at most 2.5 A,
±25 %) could not pass the 3 A case with margin. It is replaced on the main
board by a **TPS259470ARPWR eFuse** (C3662799). Its limit is 3340/RILM with
−11 %/+9 %; RILM 1.13 kΩ gives 2.63 / 2.96 / 3.21 A (min/nom/max). The OVLO
divider keeps a misbehaving source off 5V_SYS, and a 680 pF dVdt capacitor
slows the attach. The 2 A input PTC becomes a **3.5 A SMD1812P350TF/16**
(C46970911). The TVS stays SMF5.0A: its 9.2 V clamp is now far inside the
eFuse's 23 V rating. The main 3V3 buck is the **TLV62569PDDCR** (C398365):
the DBV package reaches 100 °C at 1.21 A, and slots 5–6 can bring the 3V3 to
1.22 A.

**Default USB (B6/B7)** now checks power.md's statement as written: a
default source runs the machine at typical loads (the Typ column, a 100 mA
keyboard, the radio off). That is 370 mA, 26 % under USB 2.0's 500 mA. The
max budget (637 mA) is not promised.

**The keyboard port (B16, POW-007)** has a boost on the IO card. Without it
the port sat at 3.97 V at the worst corner. With it, the port stays at 4.70 V
or more through a 500 mA step at every corner, against USB 2.0's 4.40 V. The
circuit is below, for the IO board agent.

### Decided (POW-008, POW-006 B5), David 2026-09-25

- **HDMI +5V: a TPS63802 buck-boost**, the safest of the options. With the
  TPS61023 boost the pin followed a source above 5.45 V through the boost's
  pass-through, reaching 5.40 V against HDMI's 5.3 V. A buck-boost
  regulates in both directions: the pin now stays within 4.862–5.239 V at
  every corner, 5.5 V sources included.
- **B5, a 1.5 A source:** accepted at 5 % margin, not 10 % (the waiver).
  It is 1.383 A (7.8 % under 1.5 A); the buck-boost costs 14 mA more than
  the boost did.

### Decided (POW-006 B10)

| Check | Result | What it needs |
|---|---|---|
| B10, the IO card's +5V against slot.md's 0.55 A (**decided 2026-09-24: raised to 0.80 A**) | A 500 mA keyboard through the boost draws **0.746 A** from a 3.89 V card input at the worst corner. No boost can do better on 0.55 A: even an ideal one needs 0.57 A. | Raise slot.md's per-card +5V budget from 0.55 A to **0.80 A**. The slot fuse goes up one size to **SMD1206P110TFT** (C143975), which holds 0.92 A at 40 °C. With that fuse the IO card passes against the fuse itself (B10b, +19 %), and 0.80 A is 13 % under its hold (B8 at 10 %). |

### IO card keyboard boost (for the IO board agent)

```
slot +5V ──┬── C 10 µF 25 V 0805 (C15850)
           └── TPS61023DRLR (C919459, SOT-563)
                 VIN, EN ── slot +5V (always on; it idles at ~1 µA)
                 SW ── L 1 µH FXL0420-1R0-M (C167203, 27 mΩ, Isat 7 A) ── slot +5V
                 VOUT ──┬── 2 × 22 µF 25 V 0805 (C45783)
                        ├── R1 750 kΩ 1 % (C23240) ── FB ── R2 100 kΩ 1 % (C25803) ── GND
                        └── SY6280AAC (C55136), as before: its RSET sets the 500 mA
                            limit, EN from the RP2040, FLT to GPIO8 ── USB-A VBUS
```

- The output is 5.06 V nominal, 4.84–5.28 V over VREF and the divider's
  tolerance. At a card input above ~5.1 V the TPS61023 passes its input
  straight through: at vSafe5V max the port reaches 5.43 V at most, under
  5.5 V.
- No feedforward capacitor is needed: 2 × 22 µF derates to about 26 µF at
  5 V, under the 40 µF above which TI recommends one.
- The SY6280 keeps the 500 mA limit and the fault flag the firmware reads. It
  only switches the boost's output.
- Layout follows TI's (SLVSF14B, section 10): the input and output capacitors
  go right at VIN/VOUT and GND, and the SW loop stays short.

Other observations (not failures):
- The SMF5.0A's 5.0 V standoff is below vSafe5V max (5.5 V). Leakage rises,
  but it stays under breakdown (B21 passes).
- The eFuse's OVLO needs a **0.1 %** divider: with 1 % the trip can reach
  6.00 V, the absolute maximum of the TLV62569, SY6280 and TPS61023 behind it.
- Porting TI's TPS61023 model to ngspice needed three fixes, all in
  `models/fetch.py`. A current source written "10A" read as atto amps; ideal
  diodes (emission coefficient 0.01 → 0.1); and 1 pF on its pre-charge FET.
  POW-007 G0 checks the ported model still regulates at the datasheet's set
  point (0.8 % off).

### GPU card HDMI +5V (for the GPU board agent)

```
slot +5V ── PTC SMD0805P020TF (C20976, 200 mA, 0.5–3.5 Ω)
         ── 10 µF 25 V 0805 (C15850) at VIN
         ── TPS63802DLAR (C2845237, VSON-10)
              VIN, EN ── the PTC's output (on whenever the card has power)
              MODE ── GND (power save: it never sinks current from the pin)
              AGND, GND ── ground; PG ── unconnected (or to a GPIO)
              L1–L2: 0.47 µH FXL0420-R47-M (C167200, 14 mΩ, Isat 9.5 A)
              VOUT: 2 × 22 µF 25 V 0805 (C45783)
              FB: 300 kΩ 1 % (C23024) to VOUT, 33 kΩ 1 % (C4216) to GND  → 5.045 V
         ── HDMI pin 18 (and the 2.2 kΩ DDC pull-ups, the HPD divider)
```

- **The PTC goes ahead of the converter.** After it, 55 mA × 3.5 Ω (R1max)
  takes the pin to 4.670 V at the worst corner, under 4.8 V. Ahead of it,
  the PTC's drop only lowers the converter's input.
- **The PTC is the 200 mA size.** Ahead of the converter it carries the
  converter's input current: 95 mA at the worst corner. The 100 mA part
  (C20975) holds only 0.08 A at 40 °C; the 200 mA part holds 0.17 A (+44 %).
  A shorted cable still trips it: the converter's current limit (4–5.75 A
  in boost) pulls far more than that through it.
- **No Schottky.** The B5819W's ~0.3 V would cost the margin, and the
  TPS63802 disconnects its output from its input when it is off.
- **The output**: 5.045 V nominal; 4.881–5.214 V with VFB ±1 %, the 1 %
  divider and a 50 mVpp power-save ripple band (datasheet figure 10-21).
  HDMI asks 4.8–5.3 V.
- **Its input OVP** stops the TPS63802 above 5.5–5.9 V. At vSafe5V max its
  input reaches 5.409 V (91 mV under). Only a non-compliant source above
  5.5 V (the eFuse lets up to 5.81 V through) can trip it; it then stops,
  which is safe.
- Layout per TI (SLVSEU9D section 12): VIN and VOUT capacitors right at the
  pins over GND, the L1–L2 loop short, FB divider next to FB.

### Results (margins)

| Test | Key numbers |
|---|---|
| POW-001 3V3 buck | DC range 3.246–3.390 V (0.1 % divider). Worst 0→500 mA step: 3.238 V (+103 mV over 3.135). Light-load max 3.421 V (+44 mV under 3.465). DC low sits 76 mV above the MAX811T's 3.17 V maximum threshold. Up in 0.71 ms. Ripple 1.6 mVpp in PWM (1.2–1.4 MHz), 10–15 mVpp in power-save (19–30 kHz). |
| POW-002 1V2 | Worst low 1.172 V, including the step droop and ripple (+32 mV). Start-up peak 1.224 V (+36 mV). PSRR −44 dB at 17 kHz, −14 dB at 1.5 MHz. |
| POW-003 Wi-Fi card buck (as built) | ESP32-C3 minimum in a 358 mA TX burst: 3.199 V at the worst corner (+199 mV over 3.0), 3.201 V typical. Maximum 3.495 V (+105 mV under 3.6). Slot +5V at the card 4.116 V in the burst (+587 mV of headroom). |
| POW-004 inrush | 1 µF ahead of the eFuse (≤ 10 µF). The eFuse ramps 5V_SYS in 1.1–4.4 ms, so the 84 µF behind it charges at 91–427 mA. The whole surge, loads starting included, peaks at 0.85–1.34 A, under the eFuse's 2.63 A minimum limit (+49 %). The receptacle stays ≥ 3.91 V. |
| POW-005 CC | Realised CC ranges: default 0.317–0.571 V, 1.5 A 0.829–1.090 V, 3.0 A 1.524–1.936 V. PWR_HI trips between 1.203 V (+112 mV clear of 1.5 A) and 1.386 V (+138 mV clear of 3.0 A). The ADC classes clear by 60–102 mV. TI's TLV7011 model agrees at both edges. |
| POW-006 budget | M1 worst case 1.737 A: +42 % under a 3.0 A source, +34 % under the eFuse's minimum limit, +45 % under the PTC's 40 °C hold. The eFuse's max limit, 3.21 A, is +2.6 % under 3.3 A. With a 1.5 A source (radio off, SD reading): 1.383 A (+7.8 %, against 5 % under the waiver). Default USB at typical loads: 374 mA (+25 % under 500 mA). Slots 5–6 have 0.65 A left. Keyboard VBUS 4.784 V worst (+384 mV over 4.40), 5.397 V highest (+103 mV under 5.5). Per card +5V: IO 0.750 A (+6.3 % under slot.md's 0.80 A, +19 % under the fuse's 0.92 A hold), GPU 0.095 A, Wi-Fi 0.34 A. OVLO 5.60–5.81 V. |
| POW-007 keyboard boost | Model check: 0.8 % off the set point. Port minimum in a 0→500 mA step at the DC low corner: 4.697 V worst (+297 mV over 4.40), 4.724 V typical, 5.129 V at vSafe5V max (pass-through). Port maximum 5.431 V (+69 mV under 5.5). Up in 0.32–0.36 ms. Inductor current 0.75 A against the 2.7 A valley limit. |
| POW-008 HDMI +5V (TPS63802, behavioural) | Model check: 147 mV dip against the datasheet figure's 130 mV. Pin in a 10→55 mA step, over every tolerance: 4.874 V minimum (+74 mV over 4.8) and 5.233–5.252 V maximum (+48 mV under 5.3; 300k/33k, both basic: the 825k (C25823) had 418 in stock), at the worst and typical corners and at vSafe5V max. Converter input at vSafe5V max 5.409 V (+91 mV under its 5.5 V OVP), at the worst corner 3.750 V (over 1.3 V). PTC current 0.096 A against its 0.17 A hold (+44 %). With the PTC after the converter the pin would be 4.670 V. |
| THM-001 | 3V3 buck (PDDC) 52.2 °C at the M1 load, 73.9 °C with slots 5–6 at 300 mA each. Wi-Fi card buck 50.9 °C. IO card boost 55.5 °C, GPU card buck-boost 45.8 °C. RT9013 62.2 °C. Input eFuse at 2.62 A 63.1 °C. IO card SY6280 46.0 °C. The AMS1117 rows are gone: no M1 card has one. |

### Assumptions the boards must meet

`python3 hw/power/design.py` prints the current list. As of this writing:

- **Main board, input:** USB-C receptacle and VBUS/GND copper ≤ 20 mΩ loop.
  Input PTC **SMD1812P350TF/16** (C46970911), then the SMF5.0A TVS. Input
  switch **TPS259470ARPWR** (C3662799) with EN/UVLO tied to IN, RILM
  **1.13 kΩ 1 %**, OVLO divider **37.4k / 10.0k at 0.1 %** from IN, and
  **680 pF** on dVdt. ≤ 10 µF on VBUS ahead of it (1 µF assumed). 5V_SYS
  copper ≤ 20 mΩ, 5V_SYS bulk 22 µF. Slot 0 Ω links ≤ 50 mΩ.
- **Main board, 3V3 and 1V2:** buck **TLV62569PDDCR** (C398365; leave its PG
  pin unconnected or route it to sysctl). 2.2 µH (Isat ≥ 2.5 A, DCR
  ≤ 50 mΩ), 22 µF out, 10 µF in, divider 453k/100k at **0.1 %** (1 % fails
  POW-001 by 6–9 mV). ≥ 20 µF of effective 3V3 decoupling at the loads,
  ≤ 100 µF on 3V3 in total. RT9013: 1 µF + 4 × 100 nF.
- **Main board, PWR_HI:** CC Rd 5.1 kΩ 1 %. CC1 and CC2 each through 1 MΩ
  1 % to the TLV7011's IN+ (averaged, since one comparator serves both
  lines). IN− at **0.648 V from 3V3 via 41.2k / 10.0k 1 %**, so PWR_HI means
  a 3.0 A source.
- **Main board, slots:** slot +5V fuses **SMD1206P110TFT** (C143975; was
  SMD1206P075TFT).
- **Cards:** slot +5V contacts ≤ 30 mΩ each. IO, GPU and system cards
  ≤ 10 µF on +5V. Per card (slot.md): ≤ 0.80 A of +5V (raised from
  0.55 A for the keyboard boost, B10), ≤ 300 mA of +3V3.
- **GPU card:** the HDMI +5V circuit above: PTC SMD0805P020TF ahead of
  a TPS63802DLAR, 0.47 µH, 300k/33k 1 %, MODE to GND, no Schottky.
- **IO card:** the keyboard boost above: TPS61023DRLR, 1 µH FXL0420-1R0-M,
  10 µF in, 2 × 22 µF out, 750k/100k 1 %, feeding the SY6280 port switch.
- **Wi-Fi card:** L1 is CJiang's FNR3015S2R2MT, not a Sunlord part. LCSC's
  listing gives 2.2 µH ±20 %, Isat 2 A and DCR 78 mΩ, which the checks use.
  CJiang's own datasheet hasn't been read yet. R10 (C25803) is UNI-ROYAL
  0603WAF1003T5E, ±1 %. R9 (C25818) is assumed to be from the same ±1 %
  series; that isn't confirmed yet. The LCSC, oneyac and vendor sites were
  all unreachable on 2026-09-24.
- **System card:** ADC reference = its 3.3 V rail ±3 %. ADC error ≤ 12 LSB.
- **Not re-fetched:** the MAX811T's threshold (2.98–3.17 V) and its ~10 µs
  glitch immunity. Both datasheet sources were unavailable on 2026-09-24.

## Future: more power needs USB PD (not in M1)

Decided 2026-09-24 (David): **M1 has no USB Power Delivery.** Plain USB-C
gives at most 3 A at 5 V (15 W). M1's worst case is 1.69 A, and slots 5–6
share about 0.67 A of +5V headroom on a 3 A source (not 0.67 A each; each
slot alone is still limited to 0.80 A by its fuse).

**If a future card needs more than that, the main board needs USB PD:**

- a PD sink/trigger chip (e.g. CH224K, in JLC's library) asks the charger for
  9, 12, 15 or 20 V, which gives 30–65 W and more;
- a buck converter turns that into the 5V_SYS rail at 4–5 A;
- the input protection is redesigned for up to 20 V (eFuse OVLO, TVS, fuse),
  and every POW/THM check is redone;
- **a 5 V fallback path** for chargers without PD (a buck cannot make 5 V
  from 5 V): a buck-boost, or a bypass with switching. This is the part that
  needs the most care.

The slot pinout and per-card rules don't change, so every existing card keeps
working on a main board revision with PD.
