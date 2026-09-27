# CPU CC-005 routed power and thermal gaps (2026-09-28)

**CC-005 remains open.** This is a diagnostic of the validated CPU receipt,
not a certified resistance, capacitor, FPGA-current, or temperature limit.
No board source or fitted part was changed.

## Receipt and route

The current `build/hw/cpu/evidence.json` has SHA-256
`d16f20229024300da43722413b17b82bad81f8ae05e48ba62325eb0c7c200527`.
Its `cpu.kicad_pcb` is `d591f88aaab270bc795e3f50070158c618707c32022f5923fb6c735b01eae081f8`,
`cpu.net` is `c36e9880c67180821f02bc84a80a31887679c93e9f2ab6cff94f79b42f9e5ce5`,
and `fab/order.json` is `3753e35143509f7831936d0e1c370afa02e0f794ef514b92a7f2b035a3f74487`.
`boardevidence.validate('cpu', build/hw/cpu)` succeeds against current source.
The order specifies six layers, nominal 1 oz finished outer copper, nominal
0.5 oz finished inner copper, and JLC06161H-3313. It does **not** give a
minimum local finished thickness, via barrel plating/resistance, or socket
contact resistance.

`cpu_board.check(build/hw/cpu)` now reports:

| Path | Routed geometry | Hot nominal copper scenario |
| --- | --- | ---: |
| U3.5 to farthest U1 VCC pin (U1.40) | 47 F.Cu segments, no 1V2 via or pour | 196.8 mΩ shortest centerline path |
| J1 B5/B6/B7 +3V3 fingers to U3.1/U3.3 | 53 F.Cu segments, 36 through vias, saved In4.Cu +3V3 fill | 14.78/14.78 mΩ shortest path **if the entire In4 plane and every via are ideal zero ohms** |

The input number charges only traversed F.Cu centerline tracks at the
extractor's hot nominal 1 oz resistivity. The plane, vias, finger/socket
contacts, pad entry, and parallel spreading are assigned zero. The path can
also carry other CPU-card +3V3 loads. It is an optimistic sensitivity point,
not an effective plane resistance and neither an upper nor a lower physical
bound. At an *assumed* 40 mA confined to that path it corresponds to
0.591 mV and 23.6 µW; neither is a worst-case board result. The 1V2 number
likewise uses nominal width/thickness and zero pad resistance, so it cannot
be called a finished maximum. At 40 mA its modeled drop is 7.87 mV.

The existing behavioral result is 1.164 V minimum at the far FPGA pin,
24 mV above Lattice's 1.14 V VCC minimum. Under the **same assumed 40 mA
waveform and unchanged LDO response**, the entire remaining series-resistance
allowance would be only `24 mV/40 mA = 0.60 Ω`; this cannot be spent without
bounding copper, contacts and the true core waveform. The +3V3 feed must
be measured or extracted with qualified minimum outer/inner copper, all
relevant pad/via resistance and the actual parallel socket contacts. The
socket maker's controlled contact-resistance maximum is also needed;
the selected UMAX family drawing in `hw/datasheets/C404113_UMAX-3183-10200P1T.pdf`
and [JLC's x8 listing](https://jlcpcb.com/parts/2nd/Connectors/PCI__PCIe_Connector_2052)
do not supply a lifetime/temperature maximum for the assembled mating pair.

## Fitted capacitors and regulator

The receipt BOM fits C21 as JLC C52923, Samsung
[CL05A105KA5NQNC](https://product.samsungsem.com/mlcc/CL05A105KA5NQN.do):
1 µF ±10%, 25 V, X5R, 0402. C22 is C23733, Samsung
[CL05A475MP5NRNC](https://product.samsungsem.com/mlcc/CL05A475MP5NRN.do):
4.7 µF ±20%, 10 V, X5R, 0402. C1–C4 are C1525, Samsung
[CL05B104KO5NNNC](https://product.samsungsem.com/mlcc/CL05B104KO5NNN.do):
100 nF ±10%, 16 V, X7R each. Nameplate tolerance alone gives 0.90 µF
minimum C21 and 4.12 µF total C22+C1–C4 at the specified no-bias
measurement condition. **Those are not operating capacitance minima** at
3.3 V/1.2 V, temperature, aging, and the step spectrum. Samsung labels
its characteristic curves as typical design data, not production limits.

[Richtek RT9013 DS9013-10](https://www.richtek.com/assets/product_file/RT9013/DS9013-10.pdf)
recommends an input capacitor above 1 µF/X7R and requires at least 1 µF
output capacitance with output ESR greater than 5 mΩ for stability. C21's
nominal 1 µF X5R designation does not itself demonstrate the recommended
input condition; its tolerance-only minimum is already 0.90 µF. C22's
nominal 4.7 µF does not demonstrate a **biased** ≥1 µF or a >5 mΩ assembled
ESR floor. The model deck uses 1.4 µF and does not establish these values.
The exact fitted parts need guaranteed capacitance and impedance limits over
operating bias, temperature, age, and relevant frequency, or controlled
assembled-board measurements. If C21 cannot meet the input recommendation,
qualify a different fitted capacitor and rerun CC-005; a nameplate swap alone
is insufficient. Richtek also lists the fitted RT9013 as
[EOL](https://richtek.com/Products/Linear%20Regulator/Single%20Output%20Linear%20Regulator/RT9013?sc_lang=en&specid=RT9013);
the [replacement review](cpu-ldo-replacement.md) does not qualify a new LDO.

## FPGA current and thermal transfer

The 40 mA, 0→40 mA core step in `hw/power/ldo.py` is an assumed workload,
not an iCE40HX4K-TQ144 maximum. The
[Lattice LP/HX data sheet](https://www.latticesemi.com/iCE40) gives the
1.14–1.26 V VCC operating range and device electrical limits, while
[Lattice's iCEcube2 tool](https://www.latticesemi.com/iCEcube2) provides a
design-specific power estimator. Neither a part rating nor the route receipt
specifies the programmed CUPC/8 core's peak and sustained current versus
clock, logic/BRAM/PLL activity, I/O loading, configuration, and temperature.
An activity-backed power estimate for the exact placed design, with a
conservative envelope, or measured current/waveform at all operating modes
is needed before the 40 mA deck can be treated as a limit.

At the current assumed 40 mA and 3V3 high corner, the existing LDO heat
scenario is about 88.7 mW; multiplying by Richtek's 250 °C/W SOT-23-5
JEDEC-board θJA gives about 62.2 °C junction at 40 °C ambient. This is a
package-board sensitivity result. It omits routed input/output/return heat,
neighboring parts, final airflow and enclosure, and the current maximum is
unverified. A board-specific thermal transfer or powered-board temperature
measurement at the qualified current and ambient is required. CC-005 and
the CPU thermal claim must remain red until those physical inputs are bounded.

To reproduce the route diagnostic without writing to the receipt:

```sh
python3 - <<'PY'
import sys
from pathlib import Path
sys.path[:0] = ['hw/tools', 'hw/power']
import boardevidence, cpu_board
out = Path('build/hw/cpu')
boardevidence.validate('cpu', out)
cpu_board.check(out)
PY
```
