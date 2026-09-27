# Wi-Fi WC-005/WC-010 proof-gap audit (2026-09-27)

This audit uses the committed `test/hw/fixtures/wifi-power-route-20260927.tar.xz`,
whose `wifi.kicad_pcb` SHA-256 begins `a03625fc088d` and `wifi.net` begins
`98648d1e9355`. It changes no board source. The archived order specifies two
layers, 1.6 mm, and nominal 1 oz finished outer copper. It gives no local
minimum thickness, via plating minimum, or mated contact resistance.

## Fitted capacitor evidence

`hw/boards/wifi.py` fits C1 and C2 as LCSC C45783, Samsung
`CL21A226MAQNNNE` (22 µF, 25 V, X5R, 0805), and C3 as LCSC C14663,
Yageo `CC0603KRX7R9BB104` (100 nF, 50 V, X7R, 0603). The
[Samsung product page](https://product.samsungsem.com/mlcc/CL21A226MAQNNN.do)
identifies the exact packaging suffix and labels the characteristic curves
as typical design reference data. It also marks this part NRND and names a
replacement; that replacement has **not** been substituted or qualified here.
The [Yageo part specsheet](https://yageogroup.com/download/specsheet/CC0603KRX7R9BB104)
lists capacitance, tolerance, voltage, and dissipation factor, while its ESR
plots are explicitly simulation, with unspecified ESR variation and no
maximum capability. No guaranteed ESR maximum over the transient frequency,
DC-bias, temperature, and age corners was found for any of C1–C3 in these
manufacturer sources. The `0.10 Ω` equal-capacitor ESR in the existing deck
is a sensitivity assumption. At `0.18 Ω` with zero extra contact the modeled
high corner reaches 3.595 V, only 5 mV below the 3.6 V limit; at `0.30 Ω`
it reaches 3.665 V. A guarantee or bounded assembled impedance is needed.

## Ground return in the saved receipt

The filled GND zones specify 0.25 mm minimum fill feature width, 0.5 mm thermal gap,
and 0.5 mm thermal bridge width. The following pads have a direct 0.3 mm
F.Cu segment from their pad center to a 0.6/0.3 mm GND stitching via; they
are not dependent solely on thermal relief through the fill:

| Pad | Center-to-via distance | Hot nominal 1 oz, 0.3 mm strip scenario |
| --- | ---: | ---: |
| U1.1 module GND | 0.326 mm | 0.75 mΩ |
| U2.2 buck GND | 1.000 mm | 2.30 mΩ |
| C1.2 input cap GND | 1.000 mm | 2.30 mΩ |
| C2.2 output cap GND | 1.000 mm | 2.30 mΩ |
| C3.2 decoupler GND | 1.000 mm | 2.30 mΩ |

The strip values apply `0.01724 Ω·mm²/m / 0.035 mm × 1.4` as in
`wifi_board.COPPER_OHM_MM`; they charge the full center-to-via segment and
therefore are geometry scenarios, not minimum or maximum assembled pad
resistance. They omit solder and pad spreading. The existing GND raster
connects idealized pad cells to filled copper with zero pad entry cost, uses
a fixed 0.25 mm corridor, and assigns 10 mΩ per through-via. Its reported
123.44/121.72 mΩ (0.25/0.125 mm pitch) covers U1 GND to the *local*
C2/C3/U2 GND pads. It does not cover return to J1 card-edge GND contacts.

Replaying the same `wifi_ground` graph from U1.1 to any J1 GND pad on each
face gives these additional diagnostic scenarios:

| Target GND fingers | 0.25 mm raster | 0.125 mm raster |
| --- | ---: | ---: |
| F.Cu B3/B5/B8/B11/B12/B14/B17 | 186.88 mΩ | 177.23 mΩ |
| B.Cu A3/A5/A8/A11/A12/A13/A15/A17 | 196.19 mΩ | 185.85 mΩ |

For these four values, the raster attaches to any filled cell overlapping
one of the listed pads. It still omits the mated socket contact, finger
surface, pad-to-fill entry, solder, local copper thickness minimum, and
uncertainty in via barrels. Parallel current spreading and the actual
external return also differ from a shortest fixed-width corridor. Thus
neither the 123 mΩ local figure nor the J1 figures can be inserted as a
certified maximum. The existing transient deck has no J1 ground return
term; its local rail result cannot certify the full input loop.

To reproduce after extracting the fixture into `build/hw/wifi`:

```sh
python3 hw/power/thermal.py wifi-card build/hw/wifi
python3 - <<'PY'
import sys
sys.path.insert(0, 'hw/power')
import wifi_board as w, wifi_ground as g
from pathlib import Path
t = w.parse(Path('build/hw/wifi/wifi.kicad_pcb').read_text())
pads = w.pad_nodes(t)
for pitch in (0.25, 0.125):
    xs, ys, mask = g.raster(g.polygons(t), pitch)
    links, vias = g.via_links(t, xs, ys, mask, pitch)
    src = g.pad_cells(pads, xs, ys, mask, [('U1', '1')], pitch)
    for face, pins in (('A', ('A3','A5','A8','A11','A12','A13','A15','A17')),
                       ('B', ('B3','B5','B8','B11','B12','B14','B17'))):
        dst = g.pad_cells(pads, xs, ys, mask, [('J1', pin) for pin in pins], pitch)
        print(pitch, face, 1000 * g.shortest(mask, links, src, dst, pitch))
PY
```

## Thermal transfer

`thermal.py wifi-card` computes 88.306 mW buck-plus-assigned-copper heat,
including 36.739 mW copper, and at most 1.26 W ESP TX electrical input as
heat. With its assumed JEDEC DBV `θJA = 188.2 °C/W`, the buck-only junction
is 56.62 °C at 40 °C ambient. The remaining 43.38 °C permits at most
`43.38/1.26 = 34.429 °C/W` ESP-to-buck transfer. This is a *required upper
bound*, not a computed property of the card. For reference, 40 °C/W transfer
would add 50.4 °C and bring that model to 107.0 °C. TI reports different
TLV62569 thermal resistances for its JEDEC board and EVM in the
[EVM guide, table 3](https://www.ti.com/lit/ug/slvuay6/slvuay6.pdf), showing
that the package `θJA` cannot establish this board's thermal path. A simple
FR-4 conduction calculation could only estimate one branch of the heat
network; without bounded plane geometry/material properties, assembly,
neighboring-card heat, enclosure, and airflow, it cannot upper-bound junction
coupling. The 34.429 °C/W allowance also must be recomputed after electrical
ESR, contact, and copper heat are bounded. WC-010 therefore remains red.

## Closure evidence required

1. Manufacturer production maximum or qualified assembled C1–C3 impedance
   over the relevant transient spectrum and voltage/temperature/age corners.
2. Minimum manufactured copper/via properties and a validated extraction or
   four-terminal measurement bounding each pad, finger/socket, and full GND
   return path; then rerun the complete input/rail transient at that bound.
3. A calibrated board-and-enclosure thermal model or sustained full-TX
   measurement that upper-bounds ESP-to-buck transfer and buck self-heating
   in the final stack at 40 °C ambient. The model must include neighboring
   cards and final airflow.

The current WC-005 and WC-010 failures are correct. The numbers above are
diagnostics and do not turn either gate green.
