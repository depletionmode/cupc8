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
                    └── slots +5V, each via a 750 mA PTC + 0 Ω link + 50 mΩ sense
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
| USB keyboard VBUS | 5V | 100 | 500 (switch limit) |
| HDMI +5V pin (sink EDID power, per spec) | 5V | 10 | 55 |
| Wi-Fi card (ESP32-C3 via its own TLV62569 buck from +5V; TX peaks, ~260 mA at 5 V) | 5V | 80 | 350 |
| Slots 5–6 (future cards; not in M1) | 5V | 0 | — |
| **Total from USB-C (M1 cards)** | 5V | **≈ 390** | **≈ 1420** (worst-case corner, POW-006) |

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

**Models.** The 3V3 buck and the PWR_HI comparator use TI's own PSpice models
(TLV62569, TLV7011). `hw/power/models/fetch.py` downloads them from pinned
URLs, checks their SHA-256, and ports PSpice's `VSWITCH` to ngspice. They
aren't committed, because TI's licence doesn't grant redistribution. There
are no vendor models for the RT9013 or the AMS1117, and the input eFuse's
inrush check (POW-004) uses a behavioural switch with its datasheet slew
rate, limit and RON. These are **behavioural** models
(`hw/power/models/behavioural.lib`) built from datasheet figures:
- the LDOs' output impedance is fitted to a datasheet load-step figure. Each
  run re-simulates that figure first.
- the AMS1117's datasheet has no load-step figure, so its model is fitted to
  the LM1117's, a part of the same 1117 family.
- the LDO models have no control loop, so they say nothing about stability.

The TI buck model's switches are 10 mΩ rather than 100/60 mΩ, so buck losses
come from the datasheet RDS(on) and not from the simulation.

As of 2026-09-24 (milestone-1 after the 3 A decision), every test passes
except three **decisions** in POW-006: B6/B7 (default USB at the max budget)
and B16 (keyboard VBUS at the worst corner). Each prints what it needs. No
board change fixes them.

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

### Decisions still open (POW-006)

| Check | Result | What it needs |
|---|---|---|
| B6/B7, default USB, radio off, SD idle, max budget | 606 mA with a 100 mA keyboard against 500 mA (USB 2.0); 1.022 A with a 500 mA keyboard against 900 mA (USB 3.x). Typical-corner figures are 573 mA and 980 mA, still over, because they use the max loads. | Say default USB runs the machine only at typical loads (the source table above does), or have the policy also switch the keyboard port off on default sources. |
| B16, keyboard VBUS at the worst corner | 3.965 V at the USB-A port against 4.40 V (USB 2.0 low-power port). Typical: 4.588 V (B17 passes). The Type-C cable alone takes 0.36 V at 4.75 V. | Accept: keyboards run their logic at 3.3 V. No board change reaches 4.40 V at vSafe5V min with a full-drop cable. |

Other observations (not failures):
- The SMF5.0A's 5.0 V standoff is below vSafe5V max (5.5 V). Leakage rises,
  but it stays under breakdown (B21 passes).
- The eFuse's OVLO needs a **0.1 %** divider: with 1 % the trip can reach
  6.00 V, the absolute maximum of the TLV62569 and SY6280 behind it.
- The AMS1117 rows in THM-001 (T5–T7) cover a card regulating from +5V. No M1
  card does, so they could be removed.

### Results (margins)

| Test | Key numbers |
|---|---|
| POW-001 3V3 buck | DC range 3.246–3.390 V (0.1 % divider). Worst 0→500 mA step: 3.238 V (+103 mV over 3.135). Light-load max 3.421 V (+44 mV under 3.465). DC low sits 76 mV above the MAX811T's 3.17 V maximum threshold. Up in 0.71 ms. Ripple 1.6 mVpp in PWM (1.2–1.4 MHz), 10–15 mVpp in power-save (19–30 kHz). |
| POW-002 1V2 | Worst low 1.172 V, including the step droop and ripple (+32 mV). Start-up peak 1.224 V (+36 mV). PSRR −44 dB at 17 kHz, −14 dB at 1.5 MHz. |
| POW-003 Wi-Fi card buck (as built) | ESP32-C3 minimum in a 358 mA TX burst: 3.199 V at the worst corner (+199 mV over 3.0), 3.201 V typical. Maximum 3.495 V (+105 mV under 3.6). Slot +5V at the card 4.116 V in the burst (+587 mV of headroom). |
| POW-004 inrush | 1 µF ahead of the eFuse (≤ 10 µF). The eFuse ramps 5V_SYS in 1.1–4.4 ms, so the 84 µF behind it charges at 91–427 mA. The whole surge, loads starting included, peaks at 0.85–1.34 A, under the eFuse's 2.63 A minimum limit (+49 %). The receptacle stays ≥ 3.91 V. |
| POW-005 CC | Realised CC ranges: default 0.317–0.571 V, 1.5 A 0.829–1.090 V, 3.0 A 1.524–1.936 V. PWR_HI trips between 1.203 V (+112 mV clear of 1.5 A) and 1.386 V (+138 mV clear of 3.0 A). The ADC classes clear by 60–102 mV. TI's TLV7011 model agrees at both edges. |
| POW-006 budget | M1 worst case 1.424 A: +52 % under a 3.0 A source, +46 % under the eFuse's minimum limit, +55 % under the PTC's 40 °C hold. The eFuse's max limit, 3.21 A, is +2.6 % under 3.3 A. With a 1.5 A source (radio off, SD reading): 1.109 A (+26 %). Slots 5–6 have 1.03 A left. Every card is within slot.md's 0.55 A of +5V and 300 mA of +3V3 (the keyboard's 500 mA: +9 %). OVLO 5.60–5.81 V (+1.8 % over 5.5 V, +3.2 % under 6 V). |
| THM-001 | 3V3 buck (PDDC) 52.2 °C at the M1 load, 73.9 °C with slots 5–6 at 300 mA each. Wi-Fi card buck 50.9 °C. RT9013 62.2 °C. Input eFuse at 2.62 A 63.1 °C. IO card SY6280 46.0 °C. |

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
- **Cards:** slot +5V contacts ≤ 30 mΩ each. IO, GPU and system cards
  ≤ 10 µF on +5V. Per card (slot.md): ≤ 0.55 A of +5V, ≤ 300 mA of +3V3.
- **Wi-Fi card:** L1 is CJiang's FNR3015S2R2MT, not a Sunlord part. LCSC's
  listing gives 2.2 µH ±20 %, Isat 2 A and DCR 78 mΩ, which the checks use.
  CJiang's own datasheet hasn't been read yet. R10 (C25803) is UNI-ROYAL
  0603WAF1003T5E, ±1 %. R9 (C25818) is assumed to be from the same ±1 %
  series; that isn't confirmed yet. The LCSC, oneyac and vendor sites were
  all unreachable on 2026-09-24.
- **System card:** ADC reference = its 3.3 V rail ±3 %. ADC error ≤ 12 LSB.
- **Not re-fetched:** the MAX811T's threshold (2.98–3.17 V) and its ~10 µs
  glitch immunity. Both datasheet sources were unavailable on 2026-09-24.
