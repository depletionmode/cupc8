# Wi-Fi card 3V3: model fix, sourced part data and divider proposal (2026-09-28)

Scope: POW-003 / WC-005 (Wi-Fi 3V3 transient) and WC-010 (Wi-Fi thermal),
on the pinned routed board `build/hw/wifi` (evidence SHA-256 `d697e1ff…`).
**No board, schematic or build was changed.** Everything below is the
simulated state of the board as built and a proposed BOM change for David
to accept or reject.

## 1. The 2.979 V droop was a deck error

TI's `TLV62569_TRANS` subcircuit ties its internals to global node 0, not to
its `GND` pin (e.g. `V_U3_V70 U3_N16775689 0 3`, the soft-start and
reference ABM sources, the gate-drive muxes). The POW-003 deck from earlier
today put U2's `GND` pin on `buck_gnd`, 70.7 mΩ above node 0 (the J1 return
path), so the model regulated FB against the far ground: any return drop
was multiplied by `1 + R9/R10 = 5.53`.

Demonstration (standalone, 5 V in, 358 mA, only the reference node moved;
physically a no-op):

| U2 GND vs node 0 | V(out, GND) | V(FB, GND) |
| ---: | ---: | ---: |
| 0 mV | 3.3307 V | 0.6023 V |
| +30 mV | 3.1648 V | 0.5723 V |
| −30 mV | 3.4965 V | 0.6323 V |

The fix (`hw/power/buck.py` `wifi_deck`) makes node 0 U2's GND pin (C1, C2
and R10 return there, as on the board). The source, main-board bulk and
other loads sit on `slot_gnd`, and `Rboardreturn` joins the two, so the J1
return resistance stays in the input loop. Same threshold, same load and
same routed resistances: F1w goes from 2.979 V to 3.112 V at the old DC
corners. With the same model, the standalone load regulation matches TI
Fig. 10 (+0.38 % FB at 358 mA vs about +0.3 % in the figure).
`test/hw/test_wifi_parts.py` pins both the node-0 dependence of the vendor
model and the deck's grounding.

## 2. Sourced data (retrieved 2026-09-28), now `hw/power/wifi_parts.py`

The data is bound by LCSC number to the netlist: new check `F0p` fails if
any of U1, U2, L1, C1–C3, R9 or R10 changes part.

| Part (ref, LCSC) | Guaranteed by the maker | Typical only | Source |
| --- | --- | --- | --- |
| CL21A226MAQNNNE 22 µF X5R 25 V (C1, C2; C45783) | ±20 %; TCC ±15 % (−55…85 °C, no bias); DF ≤ 0.1 at 120 Hz/0.5 Vrms; life test ΔC ±12.5 %, DF ≤ 0.2. NRND, replacement CL21A226MAYNNN# (C602037) | DC bias −32.3 % @3.3 V, −36.3 % @3.6 V, −51.3 % @5.0 V, −55.5 % @5.5 V; ESR 3.9 mΩ @1.5 MHz (2.7–22 mΩ, 10 kHz–10 MHz); −23 % at 10 mVrms AC | Samsung SpecSheet issued MAY.09.2024, and the characteristic data on the [product page](https://product.samsungsem.com/mlcc/CL21A226MAQNNN.do) |
| CC0603KRX7R9BB104 100 nF X7R 50 V (C3; C14663) | ±10 %; X7R ±15 %; DF 3.5 % | ESR plots are simulations with "unspecified variations of ESR" | [YAGEO specsheet](https://yageogroup.com/download/specsheet/CC0603KRX7R9BB104) |
| TLV62569DBVR (U2; C141836) | VFB 0.588–0.612 V **at TJ = 25 °C, VIN = 5 V only**; COUT 10–47 µF; Table 4 anticipates −50/+20 % effective C; θJA 188.2, θJB 41.2, ψJB 40.6 °C/W (DBV) | Fig. 3: FB within ±0.3 % over −40…125 °C; Fig. 10: load regulation | [SLVSDG1C, Oct 2017](https://www.ti.com/lit/ds/symlink/tlv62569.pdf) |
| ESP32-C3-MINI-1U-N4 (U1; C2911374) | VDD 3.0–3.6 V recommended **and 3.6 V absolute max**; supply must deliver ≥ 0.5 A | TX 350 mA peak (802.11b 20.5 dBm, 100 % duty, 3.3 V, 25 °C). No maximum published | [Module datasheet v2.2](https://documentation.espressif.com/esp32-c3-mini-1_datasheet_en.pdf) Tables 6-1/6-2/6-4 |
| ESP32-C3 chip | eFuse writes: VDD3P3_CPU ≤ 3.3 V | | [Chip datasheet v2.4](https://www.espressif.com/sites/default/files/documentation/esp32-c3_datasheet_en.pdf) Table 5-2 note 2 |
| R9 453 kΩ (C25818), R10 100 kΩ (C25803) | UNI-ROYAL 0603WAF4533T5E / 0603WAF1003T5E: ±1 %, **±100 ppm/°C** (this confirms the R9 series, which design.py had assumed) | | JLCPCB/LCSC parts listing |

**What these sources cannot close:**

- No maker publishes a maximum ESR or a minimum capacitance under bias (F5, F7).
- Espressif gives no maximum current (F8, T4p).
- TI does not guarantee VFB over temperature.

POW-003 now uses the sourced numbers and is **stricter** than before:

- **DC corners:** VFB limits plus TI's typical ±0.3 % temperature span, and
  each divider resistor at its tolerance plus TCR × 75 °C (25 → 100 °C). For
  the fitted parts that gives 3.151–3.494 V (was 3.199–3.440 V).
- **New stress-capacitance run (F1s/F2s/F3s):** minimum tolerance, Samsung's
  typical bias loss at 5.5 V (C1) or the DC-high output (C2), full TCC and
  life drift. That is 5.83/8.34/0.076 µF, versus 13.2/13.2/0.1 µF.
- **F3 input:** now measured between U2's VIN and GND pins.

## 3. POW-003 on the board as built (current output)

```
F0p  pass  0 unbound parts
F1t  pass  3.067 V (+0.067)   F2t pass 3.584 V (+0.016)
F1w  pass  3.065 V (+0.065)   F2w FAIL 3.624 V (-0.024)
F1s  pass  3.062 V (+0.062)   F2s FAIL 3.628 V (-0.028)
F3*  pass  F4/F4e pass        F5 F6 F7 F8 FAIL
```

The droop now passes. What fails is the burst-release overshoot at the
**DC high corner** (+2 % VFB, 1 %/100 ppm divider). It exceeds the ESP32's
3.6 V absolute maximum.

## 4. Proposed change: BOM only, same values and footprints

`hw/boards/wifi.py` lines 50–51. Only the LCSC field changes:

```python
r9 = passive("R", "R9", "453k", R0603, "C861412", (60 * G, 38 * G))    # RT0603BRD07453KL 0.1 % 25 ppm
r10 = passive("R", "R10", "100k", R0603, "C122538", (60 * G, 46 * G))  # RT0603BRD07100KL 0.1 % 25 ppm
```

| Ref | Part | LCSC | Stock (JLC/LCSC, 2026-09-28) | Price |
| --- | --- | --- | --- | --- |
| R9 | YAGEO RT0603BRD07453KL, 453 kΩ ±0.1 % ±25 ppm/°C thin film | C861412 | 7,451 (JLC extended) | ≈ $0.05 |
| R10 | YAGEO RT0603BRD07100KL, 100 kΩ ±0.1 % ±25 ppm/°C | C122538 | 1,228,110 JLC / 1,041,240 LCSC | ≈ $0.02 |

The nominal set point is unchanged at 3.318 V. The DC window tightens to
3.227–3.411 V, so the rail's maximum falls: no other 3V3 load, and no
main-board input driven by MISO or UART, sees more than it does today.
Raising the set point was also evaluated. Its best option, 459 kΩ 0.1 %
(C6288321), overshoots to 3.608 V at 0.5 A with stress capacitors. Raising
does not help, because the binding limit is the 3.6 V absolute maximum, not
the droop.

Simulated with `python3 hw/power/wifi_proposal.py build/hw/wifi`. The runs
are both slot corners × the 60 % and stress capacitance × 3 and 100 mΩ ESR ×
358 mA TX and Espressif's 0.5 A supply requirement (508 mA with LEDs):

| Divider | DC window | Worst burst minimum | Worst maximum |
| --- | --- | ---: | ---: |
| fitted (1 %, 100 ppm) | 3.151–3.494 V | 3.003 V (+3 mV) | 3.654 V (**−54 mV**) |
| proposed (0.1 %, 25 ppm) | 3.227–3.411 V | **3.074 V (+74 mV)** | **3.537 V (+63 mV)** |

Proposal sensitivities (stress caps, 358 mA, worst slot corner):

- **ESR per capacitor:**
  - 150 mΩ: maximum 3.583 V, passes.
  - 200 mΩ: 3.638 V, fails.
  - 300 mΩ: 3.723 V, fails.
- **Extra J1 contact resistance:** 0.2 Ω, 0.4 Ω and 1 Ω stay at or below
  3.543 V.
- **Optional robustness step (not required):** a second 22 µF (C45783) at
  U1 pin 3 gives 3.456 V maximum at 508 mA, and 3.483 V even at 200 mΩ ESR.
  It needs a placement and route change, which would re-run the
  nondeterministic autorouter.

Follow-ups if David accepts:

- `hw/power/wifi_parts.py` `FITTED`: R9 becomes C861412 and R10 becomes
  C122538. Until then, F0p fails on purpose.
- `design.WIFI_BUCK_RES_TOL` becomes 0.001, and its R9 "assumed" comment goes.
- `test/catalogue.toml` POW-003 text changes "at 1 %" to "at 0.1 %, 25 ppm/°C".
- A board rebuild is needed to carry the field into the BOM. The copper
  should not change, but see the board-determinism issue first.

## 5. What stays red, and exactly what closes it

- **F5 (ESR maximum) and F7 (minimum effective C):** no maker guarantees
  them. Close by measuring an incoming-lot sample from the reel in use: an
  impedance analyser at 1–2 MHz on the fitted C45783, at 3.4 V and 5.5 V DC
  bias, 85 °C. The acceptance limits the model supports are:
  - ESR ≤ 150 mΩ each (or ≤ 200 mΩ with the optional second 22 µF);
  - C1 ≥ 5.8 µF and C2 ≥ 8.3 µF effective.
- **F6 and T4r (pad, spoke and mated-contact resistance):** needs a
  four-terminal measurement of U2.2→J1 and U1.1→J1 through a mated slot,
  on a built card. The model tolerates ≥ 1 Ω of extra return without a
  rail violation. The thermal heat term uses it directly.
- **F8 and T4p (load envelope):** Espressif gives only a 25 °C typical
  peak. Close with the ESP32 current measured at 40 °C, full-duty TX, on
  sample modules, or with an Espressif-provided maximum. The divider
  proposal already passes at Espressif's 0.5 A supply requirement.
- **T4c (ESP-to-buck thermal transfer):** needs a measurement. Run
  sustained full TX in the final enclosure at 40 °C ambient, with a
  thermocouple on U2's GND lead or the board next to it. Then
  Tj = T_board + ψJB (40.6 °C/W) × P_U2. No published model bounds this board.
- **F2w/F2s** stay red until the divider change is built.

## Reproduce

```sh
python3 hw/power/buck.py wifi-card build/hw/wifi
python3 hw/power/thermal.py wifi-card build/hw/wifi
python3 hw/power/wifi_proposal.py build/hw/wifi
python3 test/hw/test_wifi_parts.py
python3 test/hw/test_wifi_limits.py
```
