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
| Wi-Fi card (ESP32-C3 via its own AMS1117 from +5V; TX peaks) | 5V | 80 | 350 |
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
| Default USB power (500 mA USB 2 / 900 mA USB 3) | **Not enough** once the Wi-Fi card is fitted. sysctl reports "low-power source" over USB and blinks the power LED. It holds the Wi-Fi card in reset (CARD_RST_n) until you override it with `cupc8.py power --force`. |

## Checks (part of `make verify`, section E)

- **ngspice:**
  - buck startup and a 0 → 500 mA load step on 3V3
  - 1V2 LDO dropout and PSRR at the buck ripple frequency
  - inrush at USB attach ≤ the USB-C limit
- **Thermal:** 1V2 LDO dissipation of (3.3 − 1.2) V × 40 mA = 84 mW. The
  buck's thermal rise at max load comes from the datasheet θJA.
- **Sequencing:** the iCE40 HX power-up sequence is checked against the
  Lattice datasheet. The RP2040 boots from 3V3 alone.
- **Brown-out:**
  - sysctl holds /CPU_RST and CARD_RST_n until all rails are within 5%.
  - The 1V2 rail is monitored by sysctl through a divider into an ADC input.
