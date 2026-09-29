# emu/machine: the whole machine, natively

The native whole-machine emulator of `doc/milestone-1.md` ("Whole-machine
emulator", "Emulator speed"): `test/emu/machine.mjs` in C++, cycle for cycle.
The main board is the Verilated CPU + chipset (`soc/emu/board.h`, shared with
`build/emu/core.node`) with the SRAM and the SST39 ROM model
(`fw/test/sysmodels.c`); the GPU, IO and system cards run their real firmware
on the native RP2040 (`emu/rp2040`, its card-test harness for the `Emu` step
loop and TMDS capture); the Wi-Fi card is Espressif's QEMU, in step with the
board (below, "The Wi-Fi card"), with machine.mjs's `$A6`/`$A5` protocol.

| file | what |
|---|---|
| `machine.h`, `machine.cpp` | the cards (`Rp2040Card`, `SysctlCard`, `EspCard`), TMDS frame decoding and font matching, `Machine` (the loop, the card threads, `screen()`, `type()`) |
| `addon.cpp` | `machine.node`, wrapped by `test/emu/machinenative.mjs` into machine.mjs's `Machine` API |
| `machinerun.cpp` | the machine from the command line: speed runs, serial vs threaded digests |
| `../../soc/emu/board.h` | the main board (also used by `soc/emu/core.cpp`) |

## Build and run

```sh
tools/emu_machine_build.sh          # tools/emu_build.sh, then cmake + ninja into build/emu-machine
tools/qemu_build.sh                 # the Wi-Fi card's lockstep QEMU (build/qemu-esp); tools/fw_esp32c3.sh qemu, its firmware
node test/emu/test_wifi_lockstep.mjs # EMU-009: the Wi-Fi card in step, serial vs threaded
CUPC8_EMU=native node test/emu/test_e2e.mjs E2E-002
test/emu/machine_diff.sh            # serial/threaded determinism (EMU-007; machine.mjs is legacy, not compared)
build/emu-machine/machinerun --root . --rom ROM --mode both \
    --until '>>' 6e9 --type '10 print 6*7\nrun\n' --until 42 3e9 --run 200e6
```

`machinenative.mjs` has the same API as machine.mjs (`create({slots, rom,
sysctl})`, `powerOn`, `runFor`, `runAsync`, `runUntil`, `ns`, `state`,
`frame`, `screen`, `type`, `keyboard.press`, `stop`, `sysctlPort`), plus
`setThreaded`, `stats`, `cards`, `spiLog` and the `spiLog`/`threaded` create
options. `create({pwrHi: false})` drives the chipset's PWR_HI input low to
exercise the kernel policy for a source below 3 A; it does not model CC
voltage or supply current. `CUPC8_EMU_THREADS=0` runs serially. `runFor` runs on the calling
thread's call and returns; `runAsync`/`runUntil` yield to Node's event loop
between slices exactly as machine.mjs does, so cupc8.py can talk to the
system card's TCP port. The system card's CDC output is collected during a
slice and written to the socket at its end; input from the socket is queued
between slices, as in machine.mjs (where both only move when the event loop
turns). `-DMACHINE_LTO=ON`: see Speed.

The system card is a composite USB device with two CDC ports (`sysctl.md`);
the host side is `rp2040js::CdcHost` (`emu/rp2040/src/usb/cdchost.cpp`, the
port of `test/emu/cdchost.mjs`). Port 0 is the TCP port above; port 1, the
USB console (`../../doc/proposals/usb-console.md`), is `m.console` in
machinenative.mjs: `open()`/`close()` set and clear DTR on it (between
runs), `write()` queues bytes, `read()` returns what arrived, `listen(port)`
serves it on TCP (a connection opens it). The addon's `cdcWrite`/`cdcRead`
take the port as their last argument, and `consoleOpen(h, on)` sets DTR.

## The loop

`Machine::iterate()` is machine.mjs's `runFor` loop body, statement for
statement: `bridgePins` (the system card's SPI byte clocked into BR_* at
1 MHz); *busy* if a slot or the bridge is selected; while busy, every card is
advanced to the next clock edge, the board runs one clock, the system card
and then each slot card (slot order) advance to the board's time and are
driven; otherwise the board runs up to 120 clocks (stopping early when a
watched output changes) with its inputs sampled once, and the cards are
advanced and driven afterwards.

## Threads, and why they change nothing

Each RP2040 card has a thread. In an idle iteration nothing is advanced before
the board runs, the board's inputs (the cards' IRQ pins, the bridge pins,
`sysReset`) are sampled once at the start, and each card is then advanced to
the board's end time `t` (`while (ns < t) step()`) and driven with the
board's end outputs. So:

- The cards' work in the window depends only on `t`, the end outputs and the
  card's own state; it touches only that card (no RP2040 state is shared:
  emu/rp2040 has no globals). The order of cards within a window cannot
  matter, so they may run concurrently.
- A card's step sequence does not depend on its target. A card that steps
  while `ns < c * 1000/12`, for a clock count `c` the board has already
  reached in this window, takes a prefix of the steps `advance(t)` takes,
  because `t >= c * 1000/12` (the same double expression). So each card
  *chases* the board's clock count while the board runs, and finishes at
  `t` once the board marks the window FINAL: exactly the serial state.
- Nothing flows back until the window ends: the next iteration starts only
  when every card has arrived at the barrier; only then are the pins read.
- Busy iterations run serially, in machine.mjs's order, on one thread (every
  card is sampled each clock there: IRQ pins of unselected cards reach the
  chipset clock by clock, and the shared SCK/MOSI lines re-set their GPIO
  edge bits, so no card may run ahead).

There is no board thread: whoever leads an iteration runs the serial part
(bridgePins, busy iterations, the board's run while the others chase), then
does its own card's share; `runFor` hands the run to the threads and waits.
The leader is normally a quick card (IO, system card) that has finished its
window and volunteers, spinning until the slow card (the GPU) arrives and
hands over, so the GPU only ever chases; if nobody volunteers in time, the
last card to arrive leads. Who leads cannot change the result: the leader
does exactly the serial loop's work, with every other card parked.
`CUPC8_EMU_VOLUNTEER_SPINS` (default 200000, 0 = never volunteer) bounds the
volunteer's spin. Waits spin briefly and then sleep on a futex. `machinerun --mode
both` and `test/emu/machine_diff.sh` check the result: identical board
clocks, CPU state, RAM, every card's time, cycle counts and UART, a hash over
(board clocks, outputs, every card's time) after every iteration, every SPI
frame, and the screen.

A `storage` slot runs `build/rp2040/storage.elf` with the SD card model's
socket on its SPI1 (`emu/rp2040/harness/sdcard.h`); `Machine::sd()`, and
`sdInsert`/`sdRemove`/`sdCard` in the addon (`m.sd` in machinenative.mjs), put
an image in and take it out between runs. The model runs on the storage
card's own clock, inside its thread.

The two iCE40s' configuration (`fpgaconfig.h`): each FPGA is configured
from its W25Q flash (a `SpiFlash`: JEDEC ID, read, status, write enable,
page program and 4 KB erase, completing at CS_n rising) when the flash holds
the iCE40 sync word and the FPGA-to-flash copper is whole. sysctl's GPIO6/16
(CRESET_B, open drain) hold an FPGA unconfigured; releasing it configures
it again 200 ms later (fpga.c's figure), and GPIO7/17 read CDONE. The
system card's SPI1 reaches the chipset's flash on GPIO10-13 and the CPU
card's on GPIO14/15/8/9, whichever pin set the firmware has on SPI; an open
bus reads 0. The chipset unconfigured holds the board's nPOR input low; the
CPU card unconfigured runs no clock and drives nothing (MainBoard
`setCpuConfigured`), and its CDONE low makes the chipset hold the CPU in
reset. `state()` adds `chipsetConfigured`, `cpuConfigured` and `cdoneLed`
(D5). At power-on both are configured at once, as before (the real ~0.2 s
start-up is not modelled); `Machine.create({chipsetFlash, cpuFlash})` sets
the flash contents (default: a stand-in image with the sync word), and the
netlist top's `fpga_links` gate each leg. This runs at the serial point of
each iteration (`configStep`), with every card parked.

Indicator LEDs: a GPIO listener on each firmware-driven LED pin (storage
GPIO24/25, IO 24/25, e-ink 24, system card 0/1) records its level and rising
edges; `leds()` in the addon, `m.leds()` in machinenative.mjs (which with the
netlist top lights only LEDs whose copper is whole). Listeners only observe:
the cards' step sequence is unchanged.

sysctl's I2C0 carries two TCA9555 models (`Tca9555`, registers with the
part's pointer toggling within a pair) when `Machine.create` is given
`expanders` (the netlist top does: U13 at $20, U14 at $21 with the CPU
card's presence and ID straps on its port 1); without them every address
NACKs as before. The expanders' outputs (CARD_RST_n, PROG_n) drive nothing
yet: holding or restarting a card needs an RP2040 reset in emu/rp2040.

Harness hooks used in emu/rp2040: `FIFO::onPull` (TMDS capture), the SPI
`onTransmit`/`completeTransmit` callbacks, the I2C `onConnect`/`onWriteByte`/
`onReadByte` callbacks, GPIO `addListener`, USBCDC and UsbKeyboard; nothing
in emu/rp2040 was changed for this directory.

## Speed

Boot to BASIC and type a program (1.6 s emulated, `test/emu/machine_diff.sh`,
quiet 4-core 2.1 GHz Xeon, emu/rp2040 with its PIO fast path, 2026-09-24):

| backend | slower than real time |
|---|---|
| machine.mjs (rp2040js) | 108x |
| native, serial (`CUPC8_EMU_THREADS=0`) | 23.5x |
| native, threaded (default) | 18.0x |

The threaded machine runs at the GPU card's speed: the GPU thread is busy
~95% of the wall time (252 MHz, three DVI serialisers every cycle), while the
IO card, the system card and the main board (each ~2-3x slower than real time
alone) run beside it. The spec's "a few times slower than real time" needs a
faster GPU card emulation in emu/rp2040. `-DMACHINE_LTO=ON` builds this
tree's copy of the RP2040 library with -O3 and LTO (about 10% faster before
the PIO fast path; not re-measured). On an oversubscribed host the threaded
mode can be slower than serial: the threads meet every 10 us of emulated time.

## The Wi-Fi card

The Wi-Fi card's firmware (its QEMU build, `tools/fw_esp32c3.sh qemu`) runs
in Espressif's QEMU, built by `tools/qemu_build.sh` from the tag the SDK's
binary comes from with `tools/patches/qemu-esp-lockstep.patch` (the SDK's
binary has no plugins and no outside clock control). It runs **in step with
the board**:

- `-icount shift=3,sleep=off`: the guest's clock is its instruction count
  (8 ns each), and an idle guest's clock jumps straight to its next timer.
  `-seed 1` and the patch's fix to the SYSCON random register (it was
  `rand()` seeded from `time(NULL)`) make its random numbers repeat.
- `-chardev cupc8` (the patch's `system/cupc8-lockstep.c`) is the emulator's
  line to QEMU. The guest runs only as far as the emulator lets it:
  `EspCard::advance(t)` grants it the board's time in 100 us steps, so it
  trails the board and runs beside it, in its own process.
- **The slot SPI slave is a device in QEMU**, a stand-in for the ESP32-C3's
  GPSPI2 slave at GPSPI2's address and interrupt source (registers in
  `cupc8-lockstep.c`). Like the real slave's queued DMA descriptor it holds
  the MISO preload the firmware armed, so the board never waits for the
  guest: at CS_n falling QEMU runs to the board's time and hands the preload
  over, and at CS_n rising the frame's MOSI bytes reach the device at the
  board's time and raise its interrupt. The firmware's ISR
  (`fw/wifi/port/esp32c3/main/transport_slotdev.c`) is `transport_spi.c`'s
  `done()`/`arm()`: it queues the frame and arms the next preload, swapped
  in whole by one register write. QEMU's clock is the board's at every
  select (to within one instruction), through `net join`'s back-to-back
  polling too (EMU-009 checks both). A stock QEMU has no such device (its ID
  register reads 0): the firmware then serves frames over UART1 (`$A6`/`$A5`,
  `transport_uart.c`), which `test_wifi_qemu.py` and the legacy machine.mjs
  use.
- **When a stale preload can be seen**, as on the card (`slot.md`: the card
  preloads before CS_n falls; `wifi-card.md`, "Status byte"): a frame shifts
  out the preload armed after the previous frame ended, so the status byte
  and any offered response are as of the previous frame's end, never
  updated mid-frame. The status byte is the task's last reading (the firmware
  takes it with `frames_status()` in its main loop, at most a tick old): the
  ISR may not ask the network stack for it. A response is offered only when
  no command is queued or running (`frames_preload()`), so a READ gets it
  only if it was ready when the frame before that READ ended, and RESP_LEN
  `$00` otherwise. After a READ the next preload may offer the same response
  again until the task has replayed that READ; the host reads a response
  once and sends a new command, which discards it. If the host selects
  before the ISR has re-armed (the host must leave 20 us), the device shifts
  out the previous preload again and still takes the frame (INT bit 1 if the
  ISR had not read the last one); the real slave has no descriptor queued
  then and would miss the frame. EMU-009 counts such selects and requires
  none.
- So the same board run gives the same guest run, instruction for
  instruction: EMU-009 (`test/emu/test_wifi_lockstep.mjs`) runs a join and
  an HTTP GET serially and threaded twice and compares everything, the
  Wi-Fi card's frames, QEMU's clock and the guest's network traffic (pcap)
  included.

**The one known timing approximation: the guest runs at 125 MIPS.** icount
steps are powers of two (`shift=3`: 8 ns an instruction), and the real
ESP32-C3 runs at 160 MHz, at best one instruction a cycle (less out of
flash: cache misses). So the firmware takes its instruction counts at 125
MIPS, e.g. its frame-end ISR is up to 1.28x slower than on the card. Timers
(FreeRTOS ticks, lwIP, the UART's) are in guest time and exact. Accepted by
David, 2026-09-27.

**The network outside the machine is not in step and never can be**: QEMU's
user networking (slirp) talks to real sockets on the host's clock. The patch
pins down the common case: when the guest sends a packet the vCPU stops
right after it, and QEMU waits (wall clock) until slirp has given the guest
nothing new for `CUPC8_LOCKSTEP_SETTLE_MS` (default 20, at most
`CUPC8_LOCKSTEP_SETTLE_MAX_MS`, 2000), so a host that answers within that
time is seen at a defined guest time. A host that answers later, or sends
unasked (a client through a port forward, E2E-014), is seen whenever QEMU's
main loop gets to it. A server inside the test's own Node process answers
only when the event loop turns between slices, usually too late for that,
so EMU-009's server runs in a child process. (Runs where cupc8.py talks to
the system card are not deterministic either: its bytes arrive at slice
boundaries that depend on wall time.)

`CUPC8_ESP_TRACE=FILE` logs every select (`S`, with QEMU's clock after `@`
and the preload) and frame (`F`, the MOSI bytes) at the board's time, and `Machine.create({ pcap })` records the guest's traffic. Two
E2E-003 runs with `CUPC8_E2E003_PORT` set give identical traces (before the
lockstep they differed from the first exchange after the join).

Found by the SPI slave stand-in: the firmware's frame-end ISR built the
preload with the card's `status()`, which asks lwIP (FIONREAD on each
socket); from an interrupt that corrupted FreeRTOS's lists once a socket was
open (the interrupt watchdog fired in `vListInsert`). The UART stand-in took
the preload in a task and hid it; on the card it was waiting to happen. The
ISR now takes the status byte the task last read.

Speed (2026-09-26, 24-core host at load ~15, boot and type a program, 2.4 s
emulated): a Wi-Fi card costs nothing measurable, before or after the
lockstep: threaded 8.6x slower than real time without it, 8.5x with it;
serial 11.3x and 11.2x. QEMU runs in its own process beside the board and
is far faster than it (1.5 s of guest time takes about 0.3 s alone). E2E-003
took 32 s of wall time (40 s before, on its real-time clock).
