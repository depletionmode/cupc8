# Wi-Fi return and heat sensitivity on the current route (2026-09-28)

The validated Wi-Fi board receipt is `build/hw/wifi/evidence.json`, SHA-256
`d697e1ff24eccb5f1c6df469de263078f18118503f8ff6fcfb431d25f20f11c3`.
`hw/power/wifi_ground.py` now extracts both the local regulator/load return
and paths to the actual J1 GND fingers through saved F.Cu/B.Cu fills and
stitching vias. The latter use the same hot, nominal 1 oz copper and fixed
0.25 mm corridor as the existing local model. Results are the worse of
0.25/0.125 mm meshes; the largest mesh difference is 5.3%.

| Ground path | J1 face A | J1 face B |
| --- | ---: | ---: |
| ESP32 U1.1 to J1 | 196.2 mΩ | 186.9 mΩ |
| Buck U2.2 to J1 | 70.7 mΩ | 61.4 mΩ |

The former 123.4 mΩ local return scenario joins U1.1 to C2/C3/U2 GND and
omitted the buck-to-J1 leg. `hw/power/buck.py wifi-card` now uses a separate
70.7 mΩ buck-input GND branch in its TI TLV62569 transient deck. A proposed
J1 contact term enters that branch, where buck input current flows, rather
than the ESP output-current branch. Under the existing 100 mΩ capacitor ESR,
60% effective C and 358.3 mA TX load assumptions, the routed-return deck
reports **2.992 V typical** and **2.979 V worst** burst minima, versus the
ESP32 3.000 V floor. A zero J1 return run of the same revised deck gave
**3.113 V** at the worst corner. This is a sensitivity failure, not proof
that manufactured units violate the limit: the raster path is neither an
effective parallel-plane resistance nor a certified upper bound, and the
capacitor/load/contact assumptions remain unqualified. WC-005 stays red.

`hw/power/thermal.py wifi-card` now charges the modeled 320.8 mA buck input
through that J1 return path. Its conditional heat balance is **51.6 mW**
buck internal loss plus **44.3 mW** assigned copper, with a separate
**1.26 W** ESP TX scenario. If all external copper heat transfers to the
buck at its JEDEC self-heating coefficient, the remaining ESP-to-buck
allowance is **33.30 °C/W** at 40 °C ambient. This is an allowable transfer
under assumptions, not a measured board property. The ESP-to-J1 and
buck-to-J1 corridors share copper; their individual I²R examples cannot
be added without extracting the joint current field. WC-010 stays red.

The needed closure evidence is unchanged: guaranteed effective C and ESR
for the fitted C1–C3 over bias, age, temperature and transient frequency;
qualified maximum ESP/other-load waveform; finished copper, via, pad and
mated-contact resistance including parallel return sharing; and a calibrated
board/enclosure thermal transfer at sustained full TX. See
`wifi-proof-gaps-20260927.md` for the manufacturer-source audit.

Reproduce the numerical checks with:

```sh
python3 hw/power/buck.py wifi-card build/hw/wifi
python3 hw/power/thermal.py wifi-card build/hw/wifi
python3 test/hw/test_wifi_ground.py
python3 test/hw/test_wifi_limits.py
python3 test/hw/test_wifi_thermal_board.py
```
