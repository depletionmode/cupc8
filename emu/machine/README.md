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
options. `CUPC8_EMU_THREADS=0` runs serially. `runFor` runs on the calling
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

Harness hooks used in emu/rp2040: `FIFO::onPull` (TMDS capture), the SPI
`onTransmit`/`completeTransmit` callbacks, USBCDC and UsbKeyboard; nothing in
emu/rp2040 was changed for this directory.

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

The Wi-Fi card's firmware (its QEMU build: slot frames over UART1,
`fw/wifi/port/esp32c3/main/transport_uart.c`) runs in Espressif's QEMU,
built by `tools/qemu_build.sh` from the tag the SDK's binary comes from with
`tools/patches/qemu-esp-lockstep.patch` (the SDK's binary has no plugins and
no outside clock control). It runs **in step with the board**:

- `-icount shift=3,sleep=off`: the guest's clock is its instruction count
  (8 ns each, 125 MIPS: icount steps are powers of two, the real chip is 160
  MHz), and an idle guest's clock jumps straight to its next timer. `-seed 1`
  and the patch's fix to the SYSCON random register (it was `rand()` seeded
  from `time(NULL)`) make its random numbers repeat.
- `-chardev cupc8` (the patch's `system/cupc8-lockstep.c`) is UART1. The
  guest runs only as far as the emulator lets it: `EspCard::advance(t)`
  grants it the board's time in 100 us steps (so it trails the board and
  runs beside it, in its own process), and each `$A6`/`$A5` exchange is sent
  with the board's time of the select or deselect; QEMU runs to that guest
  time, the UART receives the bytes then, and the guest runs until it has
  answered, while the board waits. No answer in 10 s of guest time is an
  error, not a hang.
- An answer takes about 1.3 ms of guest time (the firmware's UART driver
  waits out an RX timeout before its frames task sees the bytes), so while
  the kernel polls the card back to back (every ~35 us during `net join`)
  the card's clock runs ahead of the board's, and grants below it do nothing
  (EMU-009: 0.3 s ahead after 3.2 s). On the card the SPI slave answers at
  once. Taking each byte as it comes (`uart_set_rx_full_threshold(1)`) was
  tried: the frames task (priority 10) then answered in ~0.1 ms but ran all
  the time under that polling, the main task never ran, and the join never
  finished (task watchdog). It is deterministic either way.
- So the same board run gives the same guest run, instruction for
  instruction: EMU-009 (`test/emu/test_wifi_lockstep.mjs`) runs a join and
  an HTTP GET serially and threaded twice and compares everything, the
  Wi-Fi card's frames with QEMU's clock and the guest's network traffic
  (pcap) included.

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

`CUPC8_ESP_TRACE=FILE` logs every exchange, with the board's time and QEMU's
(`@`), and `Machine.create({ pcap })` records the guest's traffic. Two
E2E-003 runs with `CUPC8_E2E003_PORT` set give identical traces (before the
lockstep they differed from the first exchange after the join).

Speed (2026-09-26, 24-core host at load ~15, boot and type a program, 2.4 s
emulated): a Wi-Fi card costs nothing measurable, before or after the
lockstep: threaded 8.6x slower than real time without it, 8.5x with it;
serial 11.3x and 11.2x. QEMU runs in its own process beside the board and
is far faster than it (1.5 s of guest time takes about 0.3 s alone). E2E-003
took 32 s of wall time (40 s before, on its real-time clock).
