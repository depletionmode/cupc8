# Power (Milestone 1)

## Input and distribution

```
USB-C receptacle (main board)
  │  CC1/CC2: 5.1 kΩ Rd each (sink). Also to sysctl ADC pins to read the
  │           source's advertised current.
  ├─ TVS (5 V, SMF5.0A class) + 2 A input fuse
  └─ soft-start current-limited switch (1.5 A limit, SY6280 class)
       │  limits inrush to USB spec (≤ 10 µF effective at attach)
       └── 5V_SYS ──┬── 3V3 buck (≥ 1.5 A, JLC basic part preferred)
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
| I²C expanders, SWD mux | 3V3 | 1 | 5 |
| LEDs (~16 at 1–2 mA) | 3V3 | 15 | 30 |
| **3V3 total** | | **242** | **462** |
| 3V3 buck input at 85% efficiency | 5V | 188 | 365 |
| USB keyboard VBUS | 5V | 100 | 500 (switch limit) |
| HDMI +5V pin (sink EDID power, per spec) | 5V | 10 | 55 |
| Wi-Fi card (ESP32-C3 via its own TLV62569 buck from +5V; TX peaks, ~260 mA at 5 V) | 5V | 80 | 350 |
| Slots 4–6 (future cards; not in M1) | 5V | 0 | — |
| **Total from USB-C (M1 cards)** | 5V | **≈ 380** | **≈ 1270** |

The worst case assumes a keyboard drawing the full 500 mA (e.g. an RGB
gaming keyboard) and Wi-Fi transmitting. With an ordinary keyboard (< 100 mA)
the maximum is about **870 mA** during Wi-Fi TX bursts.

Future cards in slots 4–6 must declare their budget. sysctl sums the declared
budgets and compares them with the advertised source current.

## Source requirements

| Source advertises (CC voltage read by sysctl) | Result |
|---|---|
| 3.0 A Type-C current | Fully supported, with headroom for slots 4–6 |
| 1.5 A Type-C current | Supported with the M1 cards |
| Default USB power (500 mA USB 2 / 900 mA USB 3) | **Not enough** once the Wi-Fi card is fitted. The main board's comparator leaves `PWR_HI` low, and the kernel's `net` command refuses to start the radio ("USB power under 1.5A: net off"). This is the main board's policy, so it holds with or without the system card; sysctl only reports the class (`cupc8.py power`). |

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
are no vendor models for the RT9013, the AMS1117 or the SY6280. These are
**behavioural** models (`hw/power/models/behavioural.lib`) built from datasheet
figures:
- the LDOs' output impedance is fitted to a datasheet load-step figure. Each
  run re-simulates that figure first.
- the AMS1117's datasheet has no load-step figure, so its model is fitted to
  the LM1117's, a part of the same 1117 family.
- the LDO models have no control loop, so they say nothing about stability.

The TI buck model's switches are 10 mΩ rather than 100/60 mΩ, so buck losses
come from the datasheet RDS(on) and not from the simulation.

As of 2026-09-24 (branch milestone-1), three tests fail: **POW-003, POW-006
and THM-001.** Each failure below comes with a proposed fix. None of the
fixes is applied, because each one changes a board or a spec.

### Out of spec

| Check | Result | Proposed fix |
|---|---|---|
| POW-003 W1w/W2w, Wi-Fi card supply at the worst corner (4.75 V source, full Type-C cable drop, parts at max resistance, M1 worst-case load) | Slot +5V reaches the card at 3.91 V. The AMS1117 (1.20 V dropout at 358 mA) then leaves the ESP32-C3 at **2.71 V** against its 3.0 V minimum (−0.29 V). At the typical corner it passes, dipping to 3.18 V. | Replace U2 on the Wi-Fi card with a **TLV62569DBVR buck** (C141836, already in the BOM, 2.2 µH, 22 µF out). `hw/power/buck.py wifi-card` simulates it at the same worst corner with a more pessimistic feed: 3.22 V minimum through the burst. This also fixes THM-001 T4. |
| THM-001 T4, Wi-Fi card AMS1117 | 358 mA (TX at 100 % duty) from 5.5 V: 884 mW × 90 °C/W gives **Tj 119.6 °C**. From 5.0 V it is still 103 °C. | The buck above (58 mW, Tj 51 °C). Keeping the AMS1117 would need θJA ≤ 68 °C/W, meaning ≥ 225 mm² of tab copper over a plane per the AMS table, and would still fail POW-003. A pre-drop resistor would make POW-003 worse. |
| THM-001 T2, 3V3 buck with slots 4–6 each drawing their 300 mA of +3V3 (1.37 A total) | TLV62569**DBV** (188 °C/W): 386 mW, **Tj 112.7 °C**. The M1 load alone gives 54.9 °C. | Use **TLV62569PDDCR** (C398365, 16k in stock, 106 °C/W, good to 1.70 A), or cap slots 4–6 at 740 mA of +3V3 in total (the DBV is good to 1.21 A). |
| POW-006 B2, input switch current limit | The M1 worst case is 1.35 A. With "1.5 A" (RSET 4.53 kΩ) the SY6280's ±25 % tolerance puts the limit anywhere from **1.13 A** to 1.88 A. | RSET **3.40 kΩ**: 1.50 / 2.00 / 2.50 A (min/nom/max). The nominal 2.0 A is the SY6280's highest programmable limit (B3, zero margin). |
| POW-006 B14 (passes with 18 mA to spare) and the source table above | Even with a 3.0 A source, the SY6280 (1.50 A minimum) and the 2 A PTC leave **18 mA** for slots 4–6. "Headroom for slots 4–6" doesn't hold. | For real slot 4–6 budgets, fit a ≥ 3 A input eFuse/switch and a matching fuse. Until then sysctl must refuse slot 4–6 declarations. |
| POW-006 B5/B6, default USB with the radio off | Max budget, 100 mA keyboard: **589 mA** against 500 mA (USB 2.0). With a 500 mA keyboard: 1.01 A against 900 mA (USB 3.x). | The "Default USB" row above holds only for typical loads. Either say so, or have the policy also limit the keyboard port (IO card SY6280) on default sources. |
| POW-006 B9, slot.md's "≤ 1 A per card" | The slot PTC (SMD1206P075TFT) holds only **0.65 A** at 40 °C. | Say ≤ 0.55 A from +5V per card in slot.md, or fit a larger PTC. M1's cards fit: Wi-Fi 369 mA and keyboard 500 mA pass B7/B8. |
| POW-006 B12, keyboard VBUS at worst case | **3.80 V** at the USB-A port, against 4.40 V (USB 2.0 low-power port). The cable alone takes 0.34 V from 4.75 V. Typical is 4.51 V (pass). | Can't be met from a USB-powered board at the worst-case source and cable. Accept (keyboards run their logic at 3.3 V) and document it. Dropping the redundant 2 A PTC or a lower-RDS switch gains about 0.25 V. |

Other observations (not failures):
- AMS1117 stability: the datasheet specifies 22 µF tantalum, and the
  LM1117 needs 0.3–22 Ω of ESR. The Wi-Fi card has ceramic 22 µF + 100 nF.
  Nothing here can check this, and the buck fix removes it.
- The SMF5.0A's 5.0 V standoff is below vSafe5V max (5.5 V). Leakage rises,
  but it stays under breakdown (B15 passes). Its 9.2 V clamp is above the
  SY6280's 6 V absolute maximum.
- The 3V3 rows of the budget table sum to 467 mA, not 462. `budget.py` uses
  the rows.
- Resolved: the system, GPU and IO cards run from the slot's +3V3 (this
  budget and io-card.md); parts.md no longer lists an AMS1117 for them.
  The Wi-Fi card has the TLV62569 buck proposed above (POW-003, THM-001 T4).

### Results that pass (margins)

| Test | Key numbers |
|---|---|
| POW-001 3V3 buck | DC range 3.246–3.390 V (0.1 % divider). Worst 0→500 mA step: 3.238 V (+103 mV over 3.135). Light-load max: 3.423 V (+42 mV under 3.465). DC low sits 76 mV above the MAX811T's 3.17 V maximum threshold. Up in 0.72 ms. Ripple 1.6 mVpp in PWM (1.1–1.4 MHz), 10–17 mVpp in power-save (17–30 kHz). |
| POW-002 1V2 | Worst low 1.172 V, including the step droop and ripple (+32 mV). Start-up peak 1.224 V (+36 mV). PSRR −44 dB at 17 kHz, −14 dB at 1.5 MHz. |
| POW-004 inrush | 1 µF ahead of the switch (≤ 10 µF). The surge is held at the SY6280 limit (1.13–2.50 A). 5V_SYS is up in 0.24–0.48 ms, and the switch dissipates ≤ 1.5 mJ. The charge above the final load is 229–392 µC (46–78 µF at 5 V): the capacitance sits behind surge limiting, as USB 2.0 §7.2.4.1 allows, so the "≤ 10 µF effective" above means ahead of the switch. |
| POW-005 CC | Realised CC ranges: default 0.317–0.571 V, 1.5 A 0.829–1.090 V, 3.0 A 1.524–1.936 V. PWR_HI trips between 0.595 V (+24 mV clear of default) and 0.719 V (+109 mV clear of 1.5 A). The ADC classes clear by 60–102 mV. TI's TLV7011 model agrees at both edges. |
| THM-001 | Buck (M1 load) 54.9 °C, RT9013 62.2 °C, main SY6280 at 1.50 A 94.0 °C, IO card SY6280 46.0 °C. |

### Assumptions the boards must meet

`python3 hw/power/design.py` prints the current list. As of this writing:

- **Main board:** receptacle and VBUS/GND copper ≤ 20 mΩ loop. 5V_SYS copper
  ≤ 20 mΩ. ≤ 10 µF on VBUS ahead of the SY6280 (1 µF assumed). 5V_SYS bulk
  22 µF. SY6280 RSET per B2 (3.40 kΩ). Slot 0 Ω links ≤ 50 mΩ. Buck: 2.2 µH
  (Isat ≥ 2.5 A, DCR ≤ 50 mΩ), 22 µF out, 10 µF in, divider 453k/100k at
  **0.1 %** (1 % fails POW-001 by 6–9 mV). ≥ 20 µF of effective 3V3
  decoupling at the loads. ≤ 100 µF on 3V3 in total. RT9013: 1 µF + 4 ×
  100 nF. CC Rd 5.1 kΩ 1%. PWR_HI: CC1 and CC2 each through 1 MΩ 1 % to
  the TLV7011's IN+ (averaged, since one comparator serves both lines),
  and IN− at 0.330 V from 3V3 via 90.9k/10k 1 %.
- **Cards:** slot +5V contacts ≤ 30 mΩ each. IO, GPU and system cards
  ≤ 10 µF on +5V.
- **System card:** ADC reference = its 3.3 V rail ±3 %. ADC error ≤ 12 LSB.
- **Not re-fetched:** the MAX811T's threshold (2.98–3.17 V) and its ~10 µs
  glitch immunity. Both datasheet sources were unavailable on 2026-09-24.
