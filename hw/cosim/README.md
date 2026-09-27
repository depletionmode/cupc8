# Schematic-derived wiring prerequisite

`gen_top.py` exports fresh KiCad netlists for the seven cards and reads the
main-board netlist. For routed slot execution it also reads the generated
GPU, IO, storage, Wi-Fi and e-ink card PCBs from `build/hw` (or
`--card-board-dir`), and the explicitly selected routed system PCB
(`--system-board`, default `build/hw/system/system-routed.kicad_pcb`). It joins contacts by physical pad number, including the
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
The main-board supervisor U6 reset output must connect to chipset U7's nPOR
input in the KiCad netlist **and** over measured routed copper. The manifest
passes `por_connected` to the native machine's reset input. On the routed
snapshot the shortest planar path is 88.152 mm; removing the supervisor
launch track makes `por_connected` false, and the native CPU stays at reset
PC `$E000` instead of reaching `$E2B9` in the 20 ms probe.
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
python3 test/hw/test_cosim_wiring.py --main-board build/hw/main/main.kicad_pcb --card-board-dir build/hw --system-board build/hw/system/system-routed.kicad_pcb
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
supervisor's routed nPOR launch, slot 1 chip-select launch, shared SCK
source launch, GPU card SCK launch and GPU QSPI clock launch, then executes the native SPI
counterexamples. The third proves
that ROM and CPU
address/data swaps, slot SCK/MOSI swaps, bridge SCK/MOSI swaps, an open
nPOR path, memory-write branches and ROM DQ0 read route change the running
machine. The manifest currently covers the CPU, main memory, slot data paths,
system bridge, Type-C source class and
supervisor nPOR release. Other power and reset circuits still use native
machine wiring. On the routed-board snapshot used for this audit, all required
top-level routes are present. Of 502 previously uncovered named nets, 45
reserved contacts have pin-bound waivers, eight slot-bus source nets, 30
card-local slot nets and 30 QSPI boot nets now affect execution; 389 remain
unmodeled. The remaining groups are boot/programming (68), slot/control bus (36), CPU/memory
(71), power/return (65), clock/reset (53), indicators (52), external IO (26),
and power policy (18). E2E-001 through E2E-004 remain
pending behind `--require-coverage` despite passing narrower runtime probes.
