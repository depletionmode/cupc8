# Board catalogue gates

`python3 hw/tools/boardcheck.py <board> <check>` requires a completed build
in `build/hw/<board>` (or `--out`). The board pipeline writes `evidence.json`
after success, recording SHA-256 of the board script, shared card code,
pin table, hardware tools, local libraries, part records and fabrication
outputs. Rebuilding invalidates the previous receipt first. Inputs changing
during a build fail receipt creation. Copied artifacts require identical
source content; an old success log or file timestamp is insufficient. The
receipt covers both board renders and requires nonempty Gerber and drill
exports, as well as the schematic, routed PCB, netlist and order files.
Existing builds made before receipts were added must be rebuilt.

ERC and DRC are run again, including schematic parity and all severities;
report fields must be present and every finding fails. BOM and footprint
checks run BRD-001 on the completed build. BOM also queries current JLC stock
at twice the receipt's assembly quantity. Offline mode cannot certify these
rows. Mechanical rows run the full fit check, including the real mainboard
and system card (the stand-in socket row is insufficient).

SC, EC and YC identify the storage, e-ink and system card board rows. WC-006
remains the Wi-Fi strapping check; its thermal row is WC-010.

## Coverage still required

A wired command is not proof of completion. The following checks deliberately
fail until their contract coverage exists:

- Fab: Gerber re-import with DRC, drills compared to footprint holes and
  recorded CPL review. Existing clean PCB DRC and exported files do not
  prove these requirements.

  `fabcheck.py` independently parses plotted copper, mask, paste, silk,
  outline, and Excellon data for its implemented checks. Passing those checks
  still leaves the fab row red. The remaining plotted-geometry rules are
  minimum neck width in filled copper and silk regions, silkscreen text height,
  and drill-to-drill clearance. The card boards also configure no positive
  solder-mask web minimum. Gerber regions use `G36` polygons and a zero-width
  aperture; checking only draw aperture widths cannot establish their minimum
  neck width. Gerber strokes have no text-object or character grouping, so
  the saved PCB's text-size property alone would not be an independent
  re-import check. `require_complete_plotted_drc` names these gaps and fails
  after all implemented checks and the CPL review. Any future closure must
  establish the missing rules from the plotted outputs, or explicitly narrow
  the fab contract with documented approval; removing the final failure does
  not certify a package.

  The 2026-09-27 seven-card diagnostic skipped only copper-to-edge and CPL
  review to reach that final coverage gate. Its success on implemented checks
  is not a fab pass. All seven card outlines have a real 0.20 mm notch
  copper-to-edge separation against the 0.30 mm board rule. This violation
  must be fixed in the plotted design, with an appropriate reroute and fresh
  exports; it is independent of the missing coverage and CPL review.
- Connectors: pincheck validates the source tables; connectorcheck compares
  every contact, including intended no-connects, of the board's external
  connectors with its KiCad netlist and the published pinout.
- Power: the main board models need binding to the actual board netlist;
  the CPU output rail has partial routed binding described below;
  GPU needs the RP2040 internal regulator at its overclocked operating point;
  IO needs SY6280 current-limit, short and fault-flag transients; storage,
  e-ink and system need load-step/internal-regulator coverage. Existing
  buck, LDO, HDMI, USB boost and budget models still execute before these
  missing portions fail.

  CC-005 now binds the CPU card's RT9013 U3, input C21, output C22,
  C1-C4 decouplers and the four FPGA VCC pins to the exported netlist and
  PCB. The 2026-09-27 routed CPU PCB (SHA-256 prefix `cd72e96e79e9`,
  netlist `8f77c6df0154`) has 47 top-layer 1V2 segments, no 1V2 vias or
  pours, and a longest centerline resistance scenario of 196.8 mΩ from
  U3.5 to U1.40. At the modeled 40 mA this adds 7.9 mV; the behavioral
  model's low-corner minimum then becomes 1.164 V, 24 mV above the FPGA's
  1.14 V limit. The scenario uses 1 oz nominal finished copper with hot
  resistivity and ideal pad contacts, so it is not a guaranteed maximum
  resistance. The 3V3 socket feed is not extracted. The board fits a nominal
  4.7 µF Samsung C22 plus four 100 nF capacitors, while the existing deck
  uses 1.4 µF; effective capacitance and ESR at bias and temperature are
  unbounded. [Richtek's RT9013 datasheet](https://www.richtek.com/assets/product_file/RT9013/DS9013-10.pdf)
  requires at least 1 µF and ESR above 5 mΩ for stability. Samsung's
  [C22 product page](https://product.samsungsem.com/mlcc/CL05A475MP5NRN.do)
  lists nominal properties and typical characteristics, not a guaranteed
  biased capacitance/ESR bound. Richtek's [product page](https://richtek.com/Products/Linear%20Regulator/Single%20Output%20Linear%20Regulator/RT9013?sc_lang=en&specid=RT9013)
  currently marks RT9013 EOL; JLC stock needs a separate live check.
  CC-005 remains red until the physical bounds and 40 mA FPGA core-load
  assumption are supported.
- Thermal: main/CPU regulator models need netlist binding, and RP2040 cards
  need internal-regulator dissipation at their maximum operating loads.
- Wi-Fi strapping: WC-006 checks the actual KiCad netlist's ESP32-C3 GPIO2/8/9,
  EN, slot reset and programming connections, and runs ngspice for both normal
  and download reset releases. The model holds the 3.3 V rail at nominal; the
  separate Wi-Fi power gate owns rail start-up and load transients.
- Wi-Fi power: WC-005 checks U2/L1/R9/R10/C1-C3 values and pins in the exported
  netlist, matches those pads to the routed PCB, and adds the board's +5V and
  3V3 track/via resistance to the TI TLV62569 transient deck. A fixed 0.25 mm
  copper corridor through the saved GND fills and vias supplies a conservative
  path scenario. Runs at 0.25 and 0.125 mm pitch expose mesh sensitivity. The
  ordered card is 1.6 mm, two layers with 1 oz finished outer copper. JLCPCB's
  [copper guide](https://jlcpcb.com/help/article/jlcpcb-copper-weight) equates
  1 oz to a nominal 35 µm. The
  deck uses 100 mΩ ESR per capacitor as a sensitivity scenario. The path
  scenario is distinct from a solved effective plane resistance. WC-005 keeps
  separate failing checks for a guaranteed ESR maximum and validated pad,
  spoke and contact resistance. WC-010 owns the thermal transfer gap.
- Wi-Fi thermal: WC-010 binds the same routed copper and adds its I²R heat to
  the buck's loss. It computes the maximum permitted ESP32-to-buck thermal
  transfer at 40 C ambient, and remains red until a calibrated board thermal
  model or measurement bounds that transfer. The JEDEC theta_JA alone does not
  describe local heating from the nearby ESP32 module. TI measured 151 °C/W
  for its TLV62569EVM-789 versus 188.2 °C/W on the JEDEC test board
  ([TI EVM guide, table 3](https://www.ti.com/lit/ug/slvuay6/slvuay6.pdf));
  neither value bounds transfer from the ESP32 on this card. TI's
  [thermal application note](https://www.ti.com/lit/pdf/slvaeb1) recommends
  estimating junction temperature from measured case temperature and the
  package's characterization parameter for the actual board.

### Wi-Fi card electrical and thermal limits still needed

For the routed Wi-Fi PCB with SHA-256 prefix `a03625fc088d` and exported
netlist `98648d1e9355` (the 2026-09-27 build), `wifi_board.routes` gives
38.0 mΩ on +5 V and 134.7 mΩ on 3V3. The saved GND fills give a 123.4 mΩ
fixed-corridor scenario with 152 represented GND vias; the 0.25/0.125 mm
meshes differ by 1.4%. `wifi_coupling_budget` then allows at most
34.4 °C/W of ESP32-to-buck transfer at the 40 °C, full-TX corner. A
calibrated thermal model or a powered-board temperature measurement still
has to establish a smaller transfer for this layout.

`python3 hw/power/wifi_limits.py build/hw/wifi` reruns the TI transient model
on that routed board while varying one unknown at a time. The minimum is
measured during the TX burst at the low DC set-point corner. The maximum
covers start-up, burst and release at the high DC set-point corner. The
ESP32-C3 module limits are 3.0–3.6 V; both must pass.

| Equal C1/C2/C3 ESR | Extra module return contact | TX minimum | Whole-wave maximum | Modeled result |
| ---: | ---: | ---: | ---: | :--- |
| 0.10 Ω | 0 Ω | 3.113 V | 3.560 V | Within limits |
| 0.15 Ω | 0 Ω | 3.109 V | 3.575 V | Within limits |
| 0.18 Ω | 0 Ω | 3.106 V | 3.595 V | Within limits |
| 0.30 Ω | 0 Ω | 3.097 V | 3.665 V | **Overvoltage** |
| 0.50 Ω | 0 Ω | 3.083 V | 3.824 V | **Overvoltage** |
| 0.10 Ω | 0.20 Ω | 3.044 V | 3.554 V | Within limits |
| 0.10 Ω | 0.33 Ω | 3.000 V | 3.551 V | **Undervoltage** (2.9998 V unrounded) |
| 0.10 Ω | 0.40 Ω | 2.976 V | 3.552 V | **Undervoltage** |

These are sensitivity results, not component or contact specifications. The
minimum-only version of this sweep missed the overvoltage at 0.30 and
0.50 Ω ESR.

The exact routed inputs are committed as
`test/hw/fixtures/wifi-power-route-20260927.tar.xz` (SHA-256
`c2fd1c4731c4b22769c1d6dbb44add85ccf6e8be4bb9bcdbbe72e1986bc440e9`).
It contains `wifi.kicad_pcb`, `wifi.net`, and `fab/order.json`; their SHA-256
values are checked by `test/hw/test_wifi_limits.py`. Extract into an isolated
checkout's `build/hw/wifi` and run the sweep:

```sh
mkdir -p build/hw/wifi
tar -xJf test/hw/fixtures/wifi-power-route-20260927.tar.xz -C build/hw/wifi
python3 hw/power/wifi_limits.py build/hw/wifi
```

The deck uses `budget.chain('worst')`, the extracted 38.008/134.665/123.440
mΩ +5 V/3V3/GND route scenarios, 22 µF C1 and C2 at 0.6 DC-bias factor,
100 nF C3, a 120 µs input rise, and an 18.3→358.3 mA load step at 1.3 ms
released at 1.6 ms with 1 µs edges. Transient stop is 1.9 ms and maximum
step is 20 ns. The TI TLV62569 transient model is fetched by
`hw/power/models/fetch.py` from the pinned [TI model ZIP](https://www.ti.com/lit/mo/slvmbw3a/slvmbw3a.zip)
(SHA-256 `af0d920f2659195de7ba1437b4b435a33f01e128abf99a4c8a39abbcf515bd5d`);
the ported library in this run had SHA-256
`0f14829d253b36a6dd788c68385ff3536caba6db6b5f09725b3ab91d6686b08f`.
The results above used ngspice 47. Generated `.cir`, `.dat` and `.log` files
are saved under the isolated checkout's `build/power/`.

The fitted C1/C2 part is Samsung CL21A226MAQNNNE. Its
[manufacturer product page](https://product.samsungsem.com/mlcc/CL21A226MAQNNN.do)
identifies the part and labels the displayed characteristics as typical
design data. Samsung's [component library terms](https://weblib.samsungsem.com/mlcc/mlcc-ec.do?partNumber=CL21A226MAQNNN)
likewise say its SPICE model is for reference, not a product warranty.
No guaranteed transient ESR maximum was found for the fitted part. The
remaining electrical evidence is a manufacturer ESR limit or a controlled
qualification of the assembled parts, plus a bound for the pad and return
contacts from calibrated extraction or measurement. Until then WC-005 and
WC-010 remain red. For WC-010, the bound is at most 34.429 °C/W of
ESP32-to-buck transfer, with 88.3 mW assigned to the buck and adjacent
copper and 1.26 W upper-bounded ESP32 TX heat. The missing input is a
calibrated board-and-enclosure thermal solution or a powered-board
measurement at 40 °C ambient and sustained 350 mA TX, including neighboring
cards and the final airflow. TI's [TLV62569 datasheet](https://www.ti.com/lit/ds/symlink/tlv62569.pdf)
provides DBV θJA 188.2 °C/W and ψJT 31.4 °C/W; these package parameters
alone do not bound heat transfer from the ESP32 on this board.
- SI and board co-simulation remain separate workstreams; newly added rows
  remain pending until their checks are implemented.

`BRD-002` exercises receipt invalidation and report failures without requiring
KiCad, routing or network access. Three counterexamples prove that stale
inputs, changed routed boards and ignored unconnected/parity findings are
rejected for the intended reason.
