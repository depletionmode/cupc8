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

For the routed Wi-Fi PCB with SHA-256 prefix `06a8db9bcace` and exported
netlist `9dd820f380cb` (the 2026-09-27 build), `wifi_board.routes` gives
38.0 mΩ on +5 V and 134.7 mΩ on 3V3. The saved GND fills give a 123.4 mΩ
fixed-corridor scenario with 152 represented GND vias; the 0.25/0.125 mm
meshes differ by 1.4%. `wifi_coupling_budget` then allows at most
34.4 °C/W of ESP32-to-buck transfer at the 40 °C, full-TX corner. A
calibrated thermal model or a powered-board temperature measurement still
has to establish a smaller transfer for this layout.

`python3 hw/power/wifi_limits.py build/hw/wifi` reruns the TI transient model
on that routed board while varying one unknown at a time. With no extra
module return contact resistance, equal ESR on C1/C2/C3 of 0.1, 0.3 and
0.5 Ω gives respective modeled TX minima of 3.113, 3.097 and 3.083 V after
the low DC set-point correction. At 0.1 Ω ESR, adding 0.2 Ω to the module
return gives 3.044 V; adding 0.33 Ω gives 3.000 V (2.9998 V before rounding),
and 0.4 Ω gives 2.976 V, below the 3.0 V limit.
These are sensitivity results, not component or contact specifications.

The fitted C1/C2 part is Samsung CL21A226MAQNNNE. Its
[manufacturer product page](https://product.samsungsem.com/mlcc/CL21A226MAQNNN.do)
identifies the part and labels the displayed characteristics as typical
design data. Samsung's [component library terms](https://weblib.samsungsem.com/mlcc/mlcc-ec.do?partNumber=CL21A226MAQNNN)
likewise say its SPICE model is for reference, not a product warranty.
No guaranteed transient ESR maximum was found for the fitted part. The
remaining electrical evidence is a manufacturer ESR limit or a controlled
qualification of the assembled parts, plus a bound for the pad and return
contacts from calibrated extraction or measurement. Until then WC-005 and
WC-010 remain red.
- SI and board co-simulation remain separate workstreams; newly added rows
  remain pending until their checks are implemented.

`BRD-002` exercises receipt invalidation and report failures without requiring
KiCad, routing or network access. Three counterexamples prove that stale
inputs, changed routed boards and ignored unconnected/parity findings are
rejected for the intended reason.
