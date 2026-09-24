# Verification contract (Milestone 1)

**Rule:** no hardware is ordered until **every row below is green in
`make verify`** and `doc/hardware/fab-readiness.md`, which is generated from
the results, is signed off by David.

There is no hardware prototype, so simulation and test must cover everything
that can be covered. The last section lists what physically cannot be
simulated, and how each item is mitigated.

Rules for the matrix:
- Every row names the **artifact under test**, **how** it is tested, and
  **what "green" means**.
- A row counts only if it runs in `make verify` and fails the build on
  regression.
- Hand checks count only where noted, and are recorded with a date in
  `fab-readiness.md`.

## 1. Logic (HDL)

| # | Artifact | Method | Green when |
|---|---|---|---|
| 1.1 | ALU, SPI master (incl. `SPI_CS`), IRQ controller, MMU decode, ROM windows/banking, bus bridge, stop/step/trace | GHDL unit testbenches | all pass; line and branch coverage ≥ 95% |
| 1.2 | CPU card (`cpu.vhd`) | Lockstep against `sim.nim`, instruction by instruction: every `test/` and `tools/testdata/` program plus ≥ 10⁶ fuzzed instructions | zero divergence; 100% opcode × format coverage |
| 1.3 | CPU bus, CPU side | Conformance testbench (`cpu-bus.md`): random wait states, stalls, mid-cycle reset, IRQ at every phase | zero protocol-monitor violations, lockstep still exact |
| 1.4 | Chipset and CPU bus | SymbiYosys proofs: one data-bus driver, /RDY rules, no RAM+ROM select together, no bridge+CPU grant together, one-hot SPI CS | all properties proven, not just bounded, where the solver allows. Bounded depth ≥ 40 otherwise. |
| 1.5 | Both FPGA designs, post-synthesis | Rows 1.2 and 1.3 re-run on the yosys netlist in Verilator | identical results to RTL |
| 1.6 | Both FPGA designs, post-place-and-route | nextpnr timing at 12 MHz | ≥ 30% slack on every path |
| 1.7 | External bus timing (SRAM, ROM, CPU socket) | `hw/timing/*_budget.py` using FPGA I/O timing, datasheet parameters and extracted trace lengths | every parameter ≥ 20% margin |

## 2. Firmware and software

| # | Artifact | Method | Green when |
|---|---|---|---|
| 2.1 | `sim.nim`, the reference model | `tools/run_tests.sh`. Every divergence found in 1.2 is resolved by the manual, not by the model. | all pass |
| 2.2 | Boot ROM `rom/boot.s` | Run in the simulator and the co-sim on every path: normal boot, each POST failure (RAM fault injection, bad magic, bad version, oversize, bad checksum), 0–6 cards, SST39VF040 vs VF010 chip ID | each path gives its specified LED code and console text |
| 2.3 | Kernel (new `gpu.s`, `keyb.s` framing, slot IRQ, network driver + commands) | Simulator scenario tests: boot to BASIC, typed programs, the Wi-Fi fetch test | scripted transcripts and golden frames match |
| 2.4 | GPU card firmware | Core: host unit tests on every opcode, malformed frames and flow control, plus golden images for TEXT and GFX. **Real binary** in rp2040js: PIO SPI slave driven with CUPC/8 timing, and the TMDS output captured and decoded back to pixels. | tests pass; decoded frame == golden |
| 2.5 | IO card firmware | Core: host tests on the keymap, repeat and overflow, fed by **HID reports recorded from ≥ 5 real keyboards** (committed as test data). Real binary in rp2040js for the SPI side. | pass |
| 2.6 | Wi-Fi card firmware | Core: host tests with lwIP's Unix port on TAP: DHCP, DNS, TCP, UDP, and TLS against a local server with a test CA. **Real binary** in Espressif's QEMU (esp32c3), with Wi-Fi replaced by QEMU's OpenCores Ethernet, running the same network tests. | pass |
| 2.7 | sysctl firmware | Core: host tests of the USB command protocol, FPGA configuration (flash and CRAM), SST39 JEDEC program and erase via the bridge model, the SWD engine against an SWD target model, the ESP UART flasher against the esptool reference protocol, I²C expander and mux sequencing, and USB-C CC → current policy | pass |
| 2.8 | Host tools (`cupc8.py`, `mkrom.py`, `jlcparts.py`) | pytest, including `cupc8.py` end-to-end against the co-sim's modelled USB | pass |

## 3. Whole system

| # | Artifact | Method | Green when |
|---|---|---|---|
| 3.1 | **The schematics themselves** | The co-sim's top level is **generated from the KiCad netlists** of all five boards. Every connection between FPGA netlists, SRAM/ROM timing models, connectors and card models comes from the schematic. Pull-ups become weak pulls, and series resistors become delays. A swapped or missing wire fails the simulation. | the end-to-end tests below pass on the netlist-generated top level |
| 3.2 | End-to-end | Blank ROM → program over modelled USB → boot → BASIC → type a program → run it → Wi-Fi join → TCP fetch from a local test server → golden HDMI frame | all pass |
| 3.3 | Negative end-to-end | Empty slots, a card removed between power cycles, corrupt kernel (bad header, bad body checksum), interrupted ROM programming, low-power USB source. Out of scope: a missing CPU card (broken hardware) and cards plugged or pulled while powered (cards change only with the power off, `slot.md`) | each behaves as specified |
| 3.4 | Pin consistency | `pins.yaml` ↔ `.pcf` ↔ firmware `pins.h` ↔ KiCad netlists, and iCE40 pin roles ↔ the Lattice pinout CSV | zero differences |

## 4. Electrical and board

| # | Artifact | Method | Green when |
|---|---|---|---|
| 4.1 | Schematics | KiCad ERC | 0 errors, and every waiver justified in writing |
| 4.2 | Layouts | KiCad DRC with JLC's rule set | 0 errors, 0 unconnected |
| 4.3 | Footprints and symbols | Every footprint matches, pad for pad, the EasyEDA footprint JLC places for its LCSC part (KiCad's own footprints are allowed when they do; an imported one when they don't). `hw/tools/bomcheck.py` (BRD-001) checks the package, the symbol pinout against the datasheet table in `hw/parts/<LCSC>.yaml`, and each line's CPL rotation against JLC's footprint. | all lines pass |
| 4.4 | Power | ngspice for each regulator (startup, load step, dropout, PSRR), USB-C inrush, and the 6-slot worst-case budget. A script checks the USB-C CC divider and ADC thresholds against the Type-C spec. | within spec with margin |
| 4.5 | Thermal | Per-regulator dissipation vs θJA at 40 °C ambient | Tj ≤ 100 °C |
| 4.6 | Signal integrity | openEMS: HDMI TMDS route, connector breakout and vias (loss and return loss up to 1.26 GHz), and the USB D+/D− routes. ngspice with IBIS models: the 6-slot shared SPI bus (SCK fan-out, MISO sharing), the CPU bus across the x8 socket, and the SRAM/ROM bus. | TMDS/USB impedance within ±10% and loss within budget; no ringing past VIH/VIL thresholds |
| 4.7 | Mechanical | STEP of all boards plus connector models, FreeCAD script: each card in each slot, card-to-card clearance, CPU card clearance, Wi-Fi antenna cable route, connector overhang, finger depth and bevel against PCIe CEM | no collisions; all dimensions in tolerance |
| 4.8 | BOM and stock | `jlcparts.py check` on every BOM line, and BOM ↔ schematic consistency | all in stock at ≥ 2× build quantity; no mismatches |
| 4.9 | Fab package | Gerbers re-imported and re-checked with DRC. The CPL is rendered over the board for a rotation and polarity review (hand check, recorded). The drill file is checked against the footprint holes. | pass, plus the recorded hand check |

## 5. Cannot be simulated: mitigations

| Risk | Why not simulable | Mitigation |
|---|---|---|
| TMDS analog eye at 252 Mb/s per lane | Needs the monitor's receiver behaviour | Pico DVI Sock pin mapping and resistors copied exactly; openEMS on our route; 4-layer board with controlled impedance |
| RP2040 at 252 MHz (per part) | Silicon margin varies | PicoDVI's standard 252 MHz with its core voltage bump (VREG 1.20 V), used widely on RP2040. Bring-up checks each unit for an hour with a soak test pattern. The spare boards cover a marginal part. |
| USB-host enumeration with real keyboards | rp2040js has no USB host | TinyUSB host HID is widely used; the HID parsing is tested on recorded reports from real keyboards; boot protocol forced |
| ESP32-C3 SPI slave on silicon | QEMU doesn't model the GPSPI slave | Espressif's documented `spi_slave` driver; the core is tested through an SPI shim that follows the datasheet timing; the framing rules (READ frames, 20 µs re-arm gap) were chosen for this driver |
| Wi-Fi RF | Radio isn't simulable | **Pre-certified module with an external antenna** (ESP32-C3-MINI-1U + MHF III lead to an SMA antenna), so our layout doesn't affect the radio |
| Assembly defects | Manufacturing | JLC AOI and X-ray on request for the TQFP; the debug features in `debugging.md` (LEDs, POST codes, test pads, isolation links, current sense, and the RP2040's stop/step/trace with `trace --diff` against the simulator); bring-up in stages; the spare main board |
