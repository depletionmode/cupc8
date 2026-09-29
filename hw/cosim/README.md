# Schematic-derived wiring prerequisite

`gen_top.py` exports fresh KiCad netlists for the seven cards and reads the
main-board netlist. For routed slot execution it also reads the generated
GPU, IO, storage, Wi-Fi and e-ink card PCBs from `build/hw` (or
`--card-board-dir`), and the explicitly selected routed system PCB
(`--system-board`, default `build/hw/system/system-routed.kicad_pcb`) and CPU
card PCB (`--cpu-board`). It joins contacts by physical pad number, including the
system socket's x4 pad translation. It checks the shared slot buses, their
chipset series resistors, the weak MISO pull, CPU socket and resistor packs,
and SRAM/ROM attachment. Its JSON manifest lists contact joins and the
verified model attachment paths. A broken connection exits nonzero.

The native RTL machine consumes the manifest when `CUPC8_COSIM_TOP` points to
it. CPU address/data wires and SRAM/ROM address/data pins use physical bit
maps read from KiCad pads. Slot SPI/IRQ and system bridge lines use their
connector maps. The shared MISO idle level comes from the verified 47 kΩ
pull-up. Cards receive edges after the 33 Ω source RC delay (1.089 ns for a
15 pF input). SRAM and ROM reads wait their 45 ns and 70 ns maximum access
times plus routed copper delay (7 ps/mm). A memory bus with no routed copper
gets provisional access times and `routed_timing: false`. The manifest lists
unrouted CPU, memory, slot, bridge, clock, reset and power-policy signal nets
under `missing_routes`; `--require-route` rejects them.
The generator separates `runtime_nets`, whose netlist values affect the
machine, from `structural_only_nets`, which have only a connectivity check.
All named nets without an executed model or a reviewed waiver appear in
`unmodeled_nets`; `structural_only_nets` still lists every structural-only net,
including waived ones. `coverage_families` groups the remaining gaps by their
required model domain. This classification is a work queue and grants no
coverage. E2E-001 through E2E-004 use `--require-coverage` and fail while any
gap remains. This keeps local card and power circuits from being silently
counted as covered.

`reviewed_waivers` currently permits only reserved connector contacts with
exactly one passive test point and no active electrical load. CPU and system
reserved contacts require the corresponding card pad to be KiCad NC; a slot
reserved contact requires all five possible card pads to be NC. The system's
two B-side reserved contacts instead require a passive test point at each end.
The waiver is recalculated from both netlists on every generation. Attaching
an IC pin or changing a mating card pad to an active net restores the coverage
gap; the wiring mutation probe checks both cases. The record includes the
actual pin list, mating contact, and reason for review. No power, clock,
programming, bus, LED, or data signal receives this waiver.

The Type-C source input in E2E-004 passes through the extracted Rd/averaging/
reference network before it reaches the chipset's `PWR_HI` pin. The nominal
trip is 1.289 V on the active CC line; the test drives the 3 A minimum or
1.5 A maximum CC voltage, so a bad resistor network changes the class.
The eight main-board GPO indicators have a separate executed digital model.
For each bit, the generator binds the chipset pad, exact 1 kΩ series part,
LED anode and grounded cathode to the schematic, then measures both routed
signal legs. On the current main receipt these measure 34.803–43.741 mm
from chipset to resistor and 4.401 mm from resistor to LED.
`Machine.state().gpoLeds[bit]` is high only when that bit of the
native GPO register is high and both signal legs are connected. Opening a
GPO1 launch on a private board copy restores two strict coverage gaps and
turns off only LED 1 in the native 20 ms probe. A changed resistor value
fails source binding. This models digital indication, not LED current,
brightness, supply integrity, or the still-unmodeled GND return.
The focused `test/hw/test_cosim_gpo_led.py` probe checks the source, copper
and native state mutations against the same routed board and generated top.
The main-board supervisor U6 reset output must connect to chipset U7's nPOR
input in the KiCad netlist **and** over measured routed copper. The manifest
passes `por_connected` to the native machine's reset input. On the routed
snapshot the shortest planar path is 88.152 mm; removing the supervisor
launch track makes `por_connected` false, and the native CPU stays at reset
PC `$E000` instead of reaching `$E2B9` in the 20 ms probe.
The system card's manual-reset GPIO23 has its own path from U1.35 to J2.B4,
then main J3.36 to supervisor U6.3 (`nMR`). The pinned routed receipts measure
44.378 mm and 56.853 mm for those legs. The local SW1.1 to U6.3 branch
measures 82.120 mm. The model also checks the mating contact translation,
reset switch ground and supervisor MR pin.
With both legs connected, a real sysctl `reset` command produces a low native
`nRST` interval and clears GPO. Removing either launch track on a private PCB
copy lets the command complete while `nRST` stays high and GPO stays `$02`;
each removal restores two strict gaps. A changed RP2040 GPIO pad fails source
binding. Holding the physical reset button keeps native `nRST` low and GPO
at `$00`; removing SW1.1's launch leaves the chipset running and restores
the main `nMR` gap. Both command and button paths are digital; switch bounce, supervisor threshold,
reset pulse analog timing and the unresolved rail return are outside it.
`test/hw/test_cosim_sysctl_reset.py` repeats both copper mutations and the
native command probe.

The IO card's USB keyboard host pair runs from RP2040 U1.46/47 through the
27 Ω R14/R15 resistors to receptacle J2.2/3. The model checks both USBLC6
ESD branches on each connector net. All eight copper legs are routed on the
current IO receipt: 10.396–10.957 mm from PHY to resistor, 9.407–20.101 mm
from resistor to receptacle, and 3.768–26.709 mm to ESD pads. The native
keyboard is attached only when both data paths reach the receptacle. Opening
either PHY or contact launch on a private PCB copy removes keyboard input,
so the keyboard IRQ fixture remains at GPO `$11` instead of reaching its
handler at `$A0`. An open ESD branch preserves keyboard operation but fails
the complete route requirement. Any open restores all four IO USB signal
nets as strict coverage gaps. This is a digital continuity model; it does not
establish USB eye quality, ESD performance, connector resistance or VBUS
power behavior. `test/hw/test_cosim_io_usb_host.py` checks source values,
copper mutations and the native keyboard IRQ.

The system card's USB CDC PHY reaches both Type-C orientations through two
27 Ω series resistors. U1.46/R3 carries D− to J1.A7/B7; U1.47/R2 carries
D+ to J1.A6/B6. U3's four ESD pads are checked as separate routed branches.
All ten copper legs are present on the pinned board (6.302–15.012 mm).
A native sysctl `ping` succeeds through either orientation. Removing either
PHY launch or a contact launch disables the affected orientation's host
port while leaving the sysctl firmware and CPU running. The opposite
orientation still works after a single contact open. A missing ESD branch
restores strict coverage gaps because protection routing is incomplete;
it does not itself disable the host port. This model covers USB continuity,
not eye quality, surge behavior or connector contact resistance.

The chipset's MEM_nWE pad U7.114 must also connect by KiCad net and routed
copper to SRAM U9.5 and ROM U10.31. The two independent branch flags gate
native memory writes. On the routed snapshot the shortest planar branches
measure 11.292 mm to SRAM and 54.867 mm to ROM. Removing the chipset's /WE
launch disables both. In a 20 ms CPU probe, an open SRAM /WE changes PC from
`$E2B9` to `$E1FF`; an open ROM /WE makes a 4 KiB sysctl flash write fail
read-back verification. This models the write-enable path only; other memory
controls and analog timing remain separate work.
ROM DQ0 has an additional route-bound read dependency from U10.13 to chipset
U7.119. The measured planar route is 23.517 mm. Opening its ROM launch track
keeps the other memory data traces in place but changes the native CPU's 20 ms
state from PC `$E2B9`/GPO `$02` to PC `$E35B`/GPO `$00`. The open net has no
pull resistor, so its voltage is physically undefined; the digital model
uses a deterministic high DQ0 value solely to expose the missing connection.
This counterexample does not establish analog open-pin behavior.
The CPU card's 16 address and 8 bidirectional data driver channels are now
traced in two copper legs each: FPGA pad to the 33 Ω pack input, and pack
output to the CPU socket finger. The generated per-bit links gate the native
CPU–chipset RTL bus in both data directions. Opening the routed FPGA A0
launch changes the native program counter; an open D0 link also changes
execution. An open bit is held high only as a deterministic digital
counterexample because its real voltage is undefined. This does not establish
CPU-card propagation delay or analog margin, and the remaining control lines
still need executed models.
Two CPU control outputs now follow the same physical card-to-chipset route:
FPGA `/STB` and `RW` pass through the 33 Ω RN5 channels, CPU socket contacts,
and separate main-board copper to U7. `/STB` has a checked 10 kΩ chipset-side
pull-up. The native RTL consumes their independent continuity flags. Opening
the CPU-card `/STB` FPGA launch on a private PCB copy changes the 20 ms PC
from `$E2B9` to `$E000` and GPO from `$02` to `$00`; opening the main-board
`RW` chipset launch changes PC to `$E1FF` and GPO to `$00`. Each open restores
three strict coverage gaps. The model uses logic high at an opened receiver
as a deterministic digital counterexample; the physical open-pad voltage,
edge timing and resistor/trace analog margin remain unmodeled. The focused
`test/hw/test_cosim_cpu_controls.py` probe checks source value, copper and
native execution mutations.
The CPU `/RDY` return is a separate three-leg input path: chipset U7.28 to
R33.1, R33.2 to main J2.B19, then CPU J1.B19 to FPGA U1.24. On the pinned
main and CPU boards those legs measure 8.306, 76.769 and 24.103 mm.
The generator checks the exact 33 Ω series part and both connector contacts;
the native RTL consumes the complete-route flag at the FPGA input. Removing
each leg in turn on a private board copy restores all three strict gaps and
stalls the native CPU at `$E000`/GPO `$00` instead of `$E2B9`/`$02`.
Changing R33's source value also fails binding. The open-input logic high is
a deterministic counterexample: open-pad voltage, `/RDY` propagation delay and
signal edge quality remain outside this digital model. The focused probe is
`test/hw/test_cosim_cpu_ready.py`.
The CPU `SYNC` instruction-boundary output has a separate FPGA U1.26 →
RN5.3, RN5.6 → CPU J1.B22, main J2.B22 → chipset U7.26 route, measuring
3.824, 19.265 and 74.037 mm. The generator checks the exact 33 Ω RN5
channel and every netlist pad. The routed flag drives the chipset's `SYNC`
input, which feeds its real instruction-step and trace logic. In the focused
native trace probe the intact board reports instruction-boundary flags;
removing each of the three launch tracks on a private board copy yields
zero such flags while CPU execution continues. Each open restores three
strict coverage gaps; changing RN5's value fails source binding. The
opened receiver is held low solely as a deterministic digital
counterexample. Its physical voltage and edge integrity remain unmodeled.
`test/hw/test_cosim_cpu_sync.py` exercises the source, copper and trace paths.
The CPU's `HALTED` and `WAITING` status outputs each pass through a 33 Ω
RN8 channel, a CPU socket contact and a main-board leg to the chipset.
The routed three-leg lengths are 10.873/35.321/49.898 mm for `HALTED` and
10.873/36.650/51.677 mm for `WAITING`. A tiny `HALT` ROM makes native
bridge status bit `$02` observable; a `STI; WAI` ROM makes bit `$04`
observable. Opening any one of the six real launch tracks on a private PCB
copy removes its status bit while the CPU itself remains in the same state.
Each open restores three strict gaps. A changed RN8 value fails source
binding. The open receiver is held low for a deterministic digital
counterexample; voltage, propagation and metastability are unmodeled.
`test/hw/test_cosim_cpu_status.py` checks both source and runtime mutations.

The main-board CPU data source is now checked independently of the CPU-card
data link. Each U7 data output must reach its exact R21–R28 33 Ω input pad;
each resistor output must reach its matching J2 socket pad, and its R90–R97
47 kΩ keeper must reach the same socket net with the other keeper pad on
`+3V3`. All 24 routed legs are present on the pinned main board. Their
length ranges are 7.775–19.017 mm from U7 to resistor, 59.128–74.437 mm
from resistor to socket, and 18.375–52.216 mm from keeper to socket.
The native RTL data input is enabled only when both main and CPU-card links
are intact. Copper-opening mutations at all 24 branch pads disable exactly
their own bit; each of eight U7 source opens changes the 20 ms native PC and
GPO. The 47 kΩ keeper is a source and route constraint here, not a model of
analog voltage, rail availability, contact resistance, or signal timing.

The chipset's four CPU IRQ outputs have an independent three-leg route each:
U7 through main-board R29–R32 (33 Ω), across J2/J1, and into CPU FPGA U1.
The four main source legs are 4.537–17.238 mm, main socket legs
38.088–57.659 mm, and CPU card legs 30.770–43.442 mm on the pinned
boards. The manifest drives a per-bit RTL receiver gate. An IRQ fixture
stimulates line 0 with an IO-card keyboard report, lines 1 and 2 with CPU
timers, and line 3 with the chipset's 50 ms tick. Each reaches its own
handler and writes GPO `$A0`–`$A3`; opening any of the three copper legs
disables that IRQ bit, and source-open probes leave the CPU parked at GPO
`$11`. Low on an open receiver is a digital counterexample; the actual
open-pad voltage, edge timing and contact behavior are not inferred.

The CPU timer-expiry pulses are also checked separately from their IRQ
returns. FPGA U1.55/56 reaches RN8's two 33 Ω channels, CPU J1.B41/B43,
main J2.B41/B43, and chipset U7.136/129. The routed legs measure
10.644/32.844/55.100 mm for timer 0 and 14.394/32.920/56.502 mm for timer 1.
An open on any of the six legs prevents that timer's pulse from reaching
the chipset's `IRQ_PEND` latch in the digital counterexample. Timer 0/1
handler probes then stay at GPO `$11` instead of `$A1`/`$A2`.
The CPU clock follows Y1.3 to R18.1 (5.937 mm), the routed 33 Ω output
to socket J2.B13 (60.564 mm), then the CPU card's J1.B13 to FPGA U1.21
(31.218 mm). Opening the FPGA clock launch holds the native CPU
at its reset vector PC `$E000` instead of `$E2B9` after 20 ms, while the
chipset continues to run. The chipset branch has its own R17 route check below.
The active-low CPU reset starts at chipset U7.32, reaches R34.1 over
12.342 mm on `CPU_nRST_SRC`, crosses the 33 Ω resistor, then follows main
R34.2 to socket J2.B16 (103.930 mm) and card J1.B16 to FPGA U1.22
(27.014 mm). Opening either the chipset source or FPGA reset launch holds
the native CPU at PC `$E000` with `/RST` low instead of booting to `$E2B9`.
The digital open-pad value is forced low for these counterexamples; the
physical voltage and reset edge quality remain unmodeled.
The 12 MHz oscillator's chipset branch runs from Y1.3 to R17.1 (14.622 mm)
and from R17.2 to chipset U7.21 (20.377 mm). The 33 Ω resistor and both
copper legs gate the chipset clock input in the native RTL. Opening either
leg removes chipset clock edges in the digital model. An open clock pad has
an undefined physical voltage, so a forced low input is used only to expose
the missing route; oscillator startup, jitter, amplitude and timing margin
remain outside this model.
The IO card's USB host data pair must pass from the RP2040 pins through the
27 Ω series resistors to the receptacle. That netlist path controls keyboard
attachment in the native machine; an open path leaves it disconnected.
Each of the six main-board slot chip selects is now connected to the native
card-select input through its netlist-identified 33 Ω resistor. Copper is
traced separately from the chipset package pad to the resistor input and
from the resistor output to the slot contact. A missing leg deasserts the
corresponding card's select in the native machine and fails `--require-route`.
The slot 1 source launch mutation leaves the other five selects intact and
reduces recorded SPI frames from 15 to 0. This accounts for the six
`SPI_nCS*_SRC` nets. Shared SPI SCK and MOSI use the same two-leg check from
the chipset through their 33 Ω source resistors to each of six slot pads;
MISO is traced from each slot pad back to the chipset input. The corresponding
per-slot link flags control the native card clock, outbound data, and return
bit. Opening the routed SCK source launch stops all slot 1 frames (15 to 0).
With the MOSI link disabled, the first GPU command changes from `$F0` to `$00`;
with MISO disabled, the native GPU workload records only 2 frames instead of
15. For digital counterexamples, open SCK/MOSI are held low and open MISO
reads the modeled idle high value; these choices do not predict analog
floating-pin voltage. The two source-side SCK/MOSI nets now count as executed.
The five slot cards now supply card-local route flags as well. SCK, MOSI,
CS_n and IRQ_n run from J1 to the MCU pad. MISO crosses the 74LVC1G125
buffer: MCU output to buffer input, buffer output to J1, and CS_n to its
output-enable pad. The generated top includes all five card kinds, while the
native machine combines only the installed kind's links with the physical
slot's main-board links. A missing generated card PCB leaves those links
disconnected and fails `--require-route`. Opening the GPU card's U1 SCK
launch changes 15 SPI frames to 0; opening IO-card IRQ_n prevents five
keyboard-service SPI frames within the first 25 ms after a key is queued.
This models digital connectivity and IRQ delivery, not analog edge quality
or open-pin voltage.
The system card's three RP2040 bridge outputs now require copper on both
sides of their 33 Ω series resistors: SCK through R11, MOSI through R12,
and chip select through R13. Their MCU-side paths measure 22.999, 18.676,
and 19.684 mm; their socket-side paths measure 25.853, 24.440, and
23.668 mm. Each route flag gates the corresponding native bridge input.
An open SCK route holds that digital input low as a deterministic
counterexample. The actual voltage on an open pad is undefined, and the
main-board bridge copper remains outside this system-card route check.
Five RP2040 boards (system, GPU, IO, storage, e-ink) also require all six
QSPI MCU-to-flash nets to have pad-to-pad copper before their native firmware
starts. An open clock launch on the GPU card changes 15 SPI frames to none;
the same board-level prerequisite removes only that card's firmware endpoint.
Mutating the IO prerequisite removes its keyboard, and mutating the system
prerequisite removes its bridge USB endpoint. The native firmware still comes
from an ELF image, so this checks a digital boot wiring prerequisite only;
flash contents, protocol timing, signal integrity, power rails, crystals,
reset and RP2040 boot-ROM fallback remain outside this model.
The storage card's seven SD signal contacts similarly control whether the
microSD socket is attached to its RP2040 model.
All four HDMI differential pairs, including the clock pair, must pass through
their 270 Ω series pack channels to the receptacle before the TMDS capture
endpoint attaches. Seven e-paper data/control lines through 33 Ω resistors
likewise control whether the panel attaches.
E2E-002 and E2E-003 capture the native HDMI frame after the BASIC program or
network page, replay the
observed GPU-slot SPI traffic through the independent host GPU core, and
compares all 640×480 decoded TMDS pixels at RGB222 precision. A fast mutation
test changes one SPI PUTC byte and requires the pixel comparison to fail.

From the repo root, after building the main board and five slot cards:

```
python3 hw/cosim/gen_top.py --output build/hw/cosim/top.json
python3 test/hw/test_cosim_wiring.py --main-board build/hw/main/main.kicad_pcb --card-board-dir build/hw --system-board build/hw/system/system-routed.kicad_pcb --cpu-board build/hw/cpu/cpu.kicad_pcb
python3 test/hw/test_cosim_runtime.py --top build/hw/cosim/top.json
# after the main route is complete:
python3 hw/cosim/gen_top.py --require-route --output build/hw/cosim/top.json
CUPC8_COSIM_TOP=build/hw/cosim/top.json CUPC8_EMU=native node test/emu/test_e2e.mjs E2E-002
# The catalogue can use this strict entry point for each row:
python3 hw/cosim/run.py E2E-001
python3 hw/cosim/run.py E2E-002
python3 hw/cosim/run.py E2E-003
python3 hw/cosim/run.py E2E-004
```

The second command proves swapped SCK/MOSI contacts, a missing chip select,
and a missing MISO pull are rejected. With `--main-board` it also opens the
supervisor's routed nPOR launch, chipset CPU-reset launch, slot 1 chip-select launch, shared SCK
source launch, GPU card SCK launch, GPU QSPI clock launch and CPU-card A0
launch, then executes the native
counterexamples. The third proves
that ROM and CPU
address/data swaps, slot SCK/MOSI swaps, bridge SCK/MOSI swaps, an open
nPOR and CPU-reset paths, memory-write branches and ROM DQ0 read route change the running
machine. The manifest currently covers the CPU, main memory, slot data paths,
system bridge, Type-C source class and
supervisor nPOR release. Other power and reset circuits still use native
machine wiring. On the archived routed-board snapshot used for this audit,
all required top-level routes are present; the current main-board route receipt
must be checked separately. The bridge MISO runtime input is gated by copper
continuity on both sides of R20 on main and from the system socket to the
RP2040 input; an open leg forces the native machine input high. Copper length
is recorded as provenance only, not an analog MISO timing model. Of 502
previously uncovered named nets, 45
reserved contacts have pin-bound waivers, eight slot-bus source nets, 30
card-local slot nets, 30 QSPI boot nets, 24 CPU-card bus nets, two CPU clock
nets, three CPU reset nets, two chipset oscillator-branch nets and three
system bridge source nets, the bridge MISO source, 16 main GPO indicator nets,
six CPU `/STB`/`RW` nets, three CPU `/RDY` nets, three CPU `SYNC` nets,
six CPU `HALTED`/`WAITING` nets and the two system manual-reset nets now affect
execution; eight main-board CPU data source nets and twelve CPU IRQ nets also
affect execution; six CPU timer-expiry nets and four system USB nets also affect execution; 288 remain
unmodeled.
The remaining groups are boot/programming (68),
slot/control bus (32), CPU/memory (3),
power/return (65), clock/reset (44), indicators (36), external IO (22),
and power policy (18). E2E-001 through E2E-004 remain
pending behind `--require-coverage` despite passing narrower runtime probes.

## Second pass (2026-09-28): 284 to 129 gaps

- **Non-digital waivers** (`coverage.py`, `analog_waivers`): 76 supply,
  return and regulator-internal nets (rails, GND, feedback and switch
  nodes, the eFuse's DVDT/ILM/OVLO, the slot +5V feeds, the iCE40 PLL
  supplies). A net is waived only while every attached pin is passive, a
  connector contact, a listed power/analog pin of its part, or a listed
  static strap (TCA9555 A0-A2, the 4051s' ~E/VEE, W25Q WP/HOLD, RP2040
  TESTEN, ...), and only while every analog check it names (the board's
  -005/-006 rows, POW-001..008, the pinout row for straps) has a command
  in the catalogue. The waiver names those checks; it does not claim they
  pass. A logic pin on a rail, or an unimplemented check, restores the gap
  (`test/hw/test_cosim_coverage.py`).
- **RP2040 crystals** (`crystal_routes`): XIN, XOUT, the 1k and both 33p load
  capacitors on every RP2040 card, each leg on routed copper; an open leg
  leaves that card's firmware stopped (like the QSPI prerequisite).
  Oscillator start-up margin is analog and not modelled.
- **FPGA configuration** (`fpga_config_routes`, `emu/machine/fpgaconfig.h`):
  both iCE40s boot from their W25Q flashes; sysctl's CRESET_B/CDONE lines,
  its SPI1 to both flashes (FL0 on the main board, FL1 through the CPU
  socket), the CPU card's CDONE into the chipset and the D5 CDONE LED, 56
  legs on 40 nets. Real `cupc8.py fpga hold/boot`, `flash id` and
  `fpga flash` run on the native machine; an image without the iCE40 sync
  word leaves the CPU card unconfigured and the CPU in reset
  (`test/hw/test_cosim_fpga_config.py`, nine copper opens).
- **Card indicator LEDs** (`card_led_routes`): the seven firmware-driven
  LEDs (storage ACT/CARD, IO KEY/KBD, e-ink REFRESH, system USB TX/RX) light
  in `m.leds()` only while both copper legs are whole
  (`test/hw/test_cosim_card_leds.py`).
- **sysctl's I2C expanders** (`i2c_expander_routes`): U13/U14 at their
  strapped addresses on the routed I2C bus; U14 P10 carries the CPU card's
  presence loop, so `cupc8.py status` reports the CPU card present. The
  expanders' CARD_RST_n and PROG_n outputs drive nothing yet.
- **sysctl's ADC** (`adc_sense_routes`): the Type-C CC1/CC2 contacts to
  GPIO26/27 and +1V2 through R100 (1k) to GPIO28; `status` reads the source
  class and the 1V2 rail (`Machine.create({pwrHi, ccLine})`). Both are
  checked with `test/hw/test_cosim_sysctl_inputs.py`.

`hw/cosim/run.py` now also runs the board rows (MB-052, CC-051, SC-051,
EC-051, YC-051) and validates all eight board receipts first.

What is left (129): the card programming port (the 4051 mux, SWD to every
slot, the ESP UART, card RUN/EN, PROG_n/BOOT and the expanders' outputs
that drive them; this needs an RP2040 reset and an SWD target in
emu/rp2040), BOOTSEL and debug UART test points, slot and system presence
and the CPU card ID (read by nothing), the power switch and eFuse enable, HDMI DDC/HPD, the IO card's
VBUS switch control, the Wi-Fi card's straps, LEDs and USB test points,
rail indicator LEDs (no analog check names them), the AUX header chip
select, and the system card's Type-C CC resistors.
