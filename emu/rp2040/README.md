# rp2040emu: a native port of rp2040js

A C++17 port of [rp2040js](https://github.com/wokwi/rp2040js) v1.1.1 **with the
cupc8 dual-core patch** (`tools/patches/rp2040js-dualcore.patch`, applied at
`~/.local/share/cupc8-sdk/rp2040js`). It exists for the "Emulator speed" row of
`doc/milestone-1.md`: the whole-machine emulator must run natively with the
same cycle model as the TypeScript one. The port is **structure-preserving**:
one C++ class per TS class, the same member and method names, the same
algorithms and the same cycle accounting, so that running the same firmware in
both and diffing `--trace-every` output can prove it cycle-identical.

Do not improve behaviour. A TS bug is ported as a bug (and may get a comment).

## Build and run

```sh
cmake -G Ninja -S emu/rp2040 -B build/emu-native   # RP2040JS_DIR=... if the SDK is elsewhere
ninja -C build/emu-native
build/emu-native/rp2040run build/rp2040/emu_nested.elf \
    --until 'NEST (PASS|FAIL)[^\n]*\n' --max-ns 500e6 --toggle-gpio 2:997
```

Build options (plain `cmake` + `ninja` needs none of them). The library is
compiled twice: `rp2040emu` (plain `-O2`; what `emu/machine` links, and
`test_periph_diff`, whose `-Wl,--wrap` of `RP2040::setInterrupt` needs the
calls between object files) and `rp2040emu_fast`, which `rp2040run`,
`rp2040emu.node` (through `rp2040harness_fast`) and the other test drivers
link, with

- `-DRP2040EMU_LTO=ON` (the default where the compiler supports it):
  link-time optimisation;
- `-DRP2040EMU_NATIVE=ON`: `-march=native` (off by default: the binaries then
  need this kind of CPU);
- `-DRP2040EMU_PGO=generate|use` with `RP2040EMU_PGO_DIR`: profile-guided
  optimisation (GCC). `emu/rp2040/tools/pgo.sh [build dir] [-D...]` does it
  all: an instrumented build in `<dir>-pgogen`, trained by `rp2040run` on the
  gpu (also with the slot pins moving), io, sysctl and self-test images, then
  `<dir>` rebuilt with the profile.

Everything is compiled with `-ffp-contract=off`: the float arithmetic must
round as JS's does, so no fused multiply-adds (which `-march=native` offers).

`rp2040run <elf> --until <regex> --max-ns <ns> [--mhz N] [--core1-slow F]
[--toggle-gpio PIN:EVERY_N_CYCLES] [--trace-every N]` is
`test/emu/rp2040emu.mjs` in C++: B1 bootrom (extracted from
`rp2040js/demo/bootrom.ts` at build time), the ELF's `PT_LOAD` segments with a
flash `paddr`, `core0.PC = 0x10000000`, `nsPerCycle = 1000 / mhz`, the same
`step()` / `cycles()` / `runUntil()` loop (PIO stepped every cycle, the idle
path capped at 1000 ns), UART0 collected. It prints the UART0 text and exits 0
if `<regex>` (ECMAScript syntax, searched like `RegExp.test`) matched, else 1.
`--toggle-gpio` is `run_nested.mjs`'s `onCycle` hook;
`--core1-slow` is the `core1Slow` option. `--trace-every N` prints
`<ns> <pc0> <pc1>` to stderr after every Nth `step()`; the matching JS line is
`` `${emu.ns} ${hex8(mcu.core0.PC)} ${hex8(mcu.core1.PC)}` `` with
`hex8 = (v) => (v >>> 0).toString(16).padStart(8, '0')`.

Output of the library: `librp2040emu.a`, include directory `src/`, namespace
`rp2040js`.

## Card-test harness and Node addon

`harness/` (C++20, `librp2040harness.a`, namespace `rp2040js::harness`) is the
test bench side, reusable from C++: `emu.h` is `test/emu/rp2040emu.mjs`'s Emu
loop (bootrom, ELF loading, `step`/`cycles`/`runUntil`, an `onCycle` hook);
`slothost.h` is `test/emu/slothost.mjs` (the slot's SPI master; its
byte/select/deselect/frame/read generators are coroutines with the same waits
and pin changes, and a script is a callback run between operations);
`tmds.h` is `test/emu/tmds.mjs`'s capture. `node/rp2040emu_node.cpp` wraps
them as `build/emu-native/rp2040emu.node` (built when Node's headers are
found), which `test/emu/rp2040native.mjs` turns into drop-in Emu, SlotHost,
TmdsCapture, UsbKeyboard and USBCDC classes. The card tests pick it with
`CUPC8_EMU=native` (`test/emu/emu_backend.mjs`):

```sh
CUPC8_EMU=native node test/emu/test_gpu.mjs GPU-004     # also GPU-005, test_io.mjs, test_sysctl.mjs
CUPC8_EMU_TRACE=1 node test/emu/test_io.mjs 2> js.trace  # every runUntil's ns, host frame, TMDS digest
```

The two backends give byte-identical `CUPC8_EMU_TRACE` output on GPU-004,
GPU-005, IOC-004 (with `DEBUG=1`) and SYS-006.

## Verification

Every module has a seeded differential harness against the patched rp2040js
(`test/diffs.sh`, catalogue EMU-005), and the whole chip is cycle-identical to
it on real firmware: the same `(ns, pc0, pc1)` trace every 97 steps and the
same UART output on the EMU-001/002 self-tests and the GPU, IO and system card
images (`test/trace/tracediff.sh`, EMU-004). The self-tests run 20-40x faster
than in rp2040js.

## Speed without changing behaviour

The port stays line for line with TS, with a few places where it takes a
shortcut that is exact (same results, same calls, same order; EMU-004/005/006
prove it):

- **PIO fast path** (`RPPIO::sync`, pio.cpp's comments have the argument).
  While every enabled machine of a block is either stalled on a WAIT that
  only a syncing event can end, or a *runner* (divider 1, autopull, every
  reachable instruction an OUT to PINS/X/Y/NULL/PINDIRS/PC/ISR with one bit
  count and no delay: PicoDVI's `out pc, 1` serialiser), and the runners'
  pins are disjoint, listener-free and muxed to the block, `step()` only
  counts cycles. Its autopull cycle runs every machine's real `clockTick()`
  (the pull's FIFO, DREQ and interrupt effects happen as they would), and a
  TX FIFO write to a runner does not leave the fast path. What is owed —
  the runners' registers and pins, stalled machines' divider phases, and
  `checkForUpdates` for every pin that changed (with no listeners that only
  sets `lastValue`) — is replayed by `sync()`, which every way in calls
  first: the block's bus registers, `GPIOPin`'s PIO output functions,
  `setInputValue`, `addListener`, IO_BANK0 ctrl and PADS writes. **C++ code
  that reads PIO machine or pin fields directly must call
  `RP2040::syncPIO()` first** (test_pio_diff does). A pull whose
  `FIFO::onPull` is set only stays on the fast path if the hook sets
  `onPullRecordsOnly` (it must not read or change the chip; TmdsCapture's
  does). `RPPIO::fastPath = false` turns it off; `lazyCycles`/`lazyEvents`
  count it (`RP2040RUN_STATS=1 rp2040run ...` prints them). `stepPIOs()` is
  Emu.cycles' PIO loop with the lazy stretches done in bulk.
- The Cortex-M0 decode is a 64K-entry handler table (`decodeTable`, by first
  halfword). The TS if/else chain is split, by a script, into its branches'
  conditions (`decodeCond<k>`) and bodies (`exec<k>`), verbatim; entry
  `opcode` is the handler of the first branch whose opcode test can hold
  (`decodeEntry`, the chain's own conditions), which runs that branch and,
  if its opcode2 term fails, the rest of the chain (`chain(k + 1)`). So every
  opcode runs the branch the chain would. `test_decode` (EMU-005 `decode`)
  checks the table exhaustively (all opcodes; all second halfwords of the
  32-bit ones) and executes every opcode through the table and through the
  plain chain (`executeInstructionChain()`, the reference) from the same state.
- Instruction fetch (`CortexM0Core::fetch16`) reads SRAM, flash, its XIP
  mirrors (0x11-0x13) and the bootrom directly, as `readUint16`'s own fast
  paths and its aligned-word fallback do (no side effects there); anything
  else, including a halfword at the end of a memory, takes `readUint16`.
  Nothing is cached, so writes need no invalidation. core-diff runs blocks
  from SRAM, flash, the three mirrors and the bootrom, and now and then
  fetches at the end of a memory or outside every memory.
- The core's own bus accesses (`CortexM0Core::readUint32` etc.) take the
  chip's SRAM and flash branches directly: an aligned SRAM or flash (and
  mirror) word read, `readUint16`/`readUint8` from flash or SRAM, and
  stores to SRAM (which has no peripheral in `findPeripheral`); anything else
  goes through `RP2040::readUint32` etc. as before.
- `RP2040::runSteps(limit, stopNanos, clock, nsPerCycle)` is the Emu loop
  (rp2040emu.mjs's `step()` and `cycles(n)` without an `onCycle` hook: the
  idle path, `step()`, `stepPIOs`, `clock.tick`) as one function with the
  instruction inline; `Emu::runUntil` (`Emu::steps(64)`), `Emu::runTo(t)`
  (`while (ns() < t) step()`) and rp2040run (runs of steps between trace
  points) use it. `test_runsteps` (EMU-005 `steps`) runs every card image
  by `Emu::step()` and by runSteps in random runs and compares the chips.
  There is no decoded-instruction cache: decoding is one table load and the
  fetch one direct load, and an idealised cache (SRAM, never invalidated)
  measured 0.4% fewer instructions and ~1% less time on gpu.elf, not worth
  an invalidation scheme.
- `toUint32`/`jsMathRound` go through int64 where that is exact
  (`test/js/test_js_numbers.cpp`); Timer32 keeps `baseFreq / prescaler`.
- `RPSIO::selectCore` defers the divider/interpolator bank swap to the next
  SIO access (code reading those fields directly calls `flushSelect()`).
- Inline common cases: `CortexM0Core::setInterrupt`, alarm unlinking, FIFO
  wrap-around, `checkInterrupts`' single `intRaw()`.
- The step loop is inline: `RP2040::step()` (reading the cores' `waiting`
  flags directly), the Emu's `step()`/`cycles()` (the idle path and the
  `onCycle` loop out of line), and `SimulationClock::tick`, which only walks
  the alarm list when the next alarm is due (`fireAlarms`).

## Status

| TS module | C++ | state |
|---|---|---|
| rp2040.ts, sio.ts, interpolator.ts, gpio-pin.ts, irq.ts, simulator.ts | `src/` | ported |
| peripherals/{peripheral,clocks,reset,psm,io,pads,ssi,busctrl,syscfg,sysinfo,tbman}.ts | `src/peripherals/` | ported |
| clock/{clock,simulation-clock}.ts, utils/{fifo,logging,time,bit}.ts | `src/clock/`, `src/utils/` | ported |
| cortex-m0-core.ts, peripherals/ppb.ts | `src/`, `src/peripherals/` | ported; `test/core` |
| peripherals/pio.ts | `src/peripherals/` | ported; `test/pio` |
| peripherals/{dma,uart,spi,i2c,timer,watchdog,rtc,adc,pwm}.ts, utils/timer32.ts | `src/peripherals/`, `src/utils/` | ported; `test/periph` |
| peripherals/{usb,usb-host}.ts, usb/{cdc,setup,interfaces}.ts, test/emu/usbkbd.mjs | `src/peripherals/`, `src/usb/` | ported; `test/usb` |

Not ported: gdb/*, utils/assembler.ts, utils/pio-assembler.ts, clock/mock-clock.ts,
index.ts, the specs.

A stub `.cpp` has every method, each with its TS source pasted in as a
`// TODO(port)` comment. Methods that firmware reaches through the bus
(`readUint32`/`writeUint32`, `DPRAMUpdated`, `executeInstruction`, PIO
`step`/`clockTick`) call `TODO_PORT_ABORT`, so nothing runs silently on a
half-ported chip; constructors and `reset()` are no-ops so the chip can be
built. Porting a file means replacing those bodies; keep the header's public
surface unless you own every user of it.

## Porting rules

**Files.** One `.h`/`.cpp` pair per TS module, at the same path and with the
same name as the TS file (`src/cortex-m0-core.ts` → `src/cortex-m0-core.{h,cpp}`,
`src/peripherals/usb-host.ts` → `src/peripherals/usb-host.{h,cpp}`). Everything
is in `namespace rp2040js`. Exception: `enum DREQChannel` lives in
`peripherals/dreq.h` (it is in dma.ts) so that uart/spi/pio/adc need not
include the DMA header. `utils/js.h` (not a TS module) holds the JS-semantics
helpers.

**Structure.** Names, structure and control flow follow the TS line for line
where practical; keep the TS comments. A class's fields keep their TS order
where C++ construction order can observe it. Module-level `const`s become
`static constexpr` in the `.cpp` (inside the namespace); only what another
module imports goes in the header. If a file-local name clashes with a
header's, the header wins (the TS imports it from there anyway); rename
locals that are C++ keywords with a trailing underscore (`register_`,
`signed_`).

**Numbers.**
- A `number` used as a 32-bit register/value → `uint32_t`; `int32_t` where the
  TS does signed arithmetic via `| 0` / `s32()` and the sign is observable.
- Nanosecond times, frequencies, and counters that TS computes with floats
  (Timer32, clock, `cycles`, the chip's `coreTime`) → `double`, exactly as the
  JS number. Never "simplify" a float expression to integers unless you can
  show it is exact.
- `x >>> 0` → `toUint32(x)` for a double, nothing for a `uint32_t`;
  `x | 0` → `toInt32(x)`; `Math.round` → `jsMathRound` (half rounds up, unlike
  `std::round`); `Math.floor` → `std::floor`. JS takes shift counts `& 31`
  (`jsShl`, `jsSar`, `jsShr`); a C++ shift by ≥ 32 is undefined.
- A JS value that can leave the 32-bit range (`reg + carry`, `accum += value`,
  a float quotient) must be computed in `double` (or `int64_t` where provably
  identical) and converted where the TS converts it (a `Uint32Array` store is a
  ToUint32). Comment each such spot.
- Values on the bus (`readUint32` results, `writeUint32` values) are
  `uint32_t`. A few TS producers pass a negative int32 (`writeUint8`/`16`
  byte replication with bit 7 set, DMA byte swap); consumers only see the
  same 32-bit pattern. That differs from TS only if a consumer does
  non-bitwise math on `value` (compare, add a float); flag any such place with
  `// JS-SIGN:`.
- Byte arrays → `std::vector<uint8_t>`/`std::array`; `DataView` and typed-array
  views → `loadLE32`/`storeLE32`/`loadLE16`/`storeLE16`. `Uint32Array(n)` →
  `std::array<uint32_t, n>{}`.

**Getters and setters.** `get foo()` → `T foo() const` (non-const if it has
side effects); `set foo(v)` → `void setFoo(T v)` (first letter upper-cased:
`set xPSR` → `setXPSR`, `set en` → `setEn`). Call sites change from `x.foo`
to `x.foo()` and from `x.foo = v` to `x.setFoo(v)`. Plain fields stay fields.

**Callbacks.** TS callbacks and arrow-function hooks (`onByte`, `onBreak`,
alarm callbacks, pin listeners, `onTransmit`, ...) → `std::function` members
(empty = `undefined`, so `this.onByte?.(v)` → `if (onByte) onByte(v)`). An
arrow-function *field* that is really a method (`transfer = () => {...}`,
`handleAlarm`, `update`) → a method; where it is passed as a callback, pass
`[this] { method(); }`. Objects that hand out `this` (alarms, listeners) are
non-copyable and non-movable; hold them by value in their owner (arrays via
brace initialisers) or in a `unique_ptr`.

**Clock and alarms.** `IClock::createAlarm` returns `std::unique_ptr<IAlarm>`;
the peripheral owns it, the clock only links it. `SimulationClock` keeps the
TS linked list exactly (equal-time alarms: a later `schedule()` goes first; a
fired alarm keeps `scheduled == true`). The clock must outlive the chip.

**No exceptions for control flow, no globals.** Everything is owned by the
`RP2040` object, so chips can run on separate threads. The only throws
mirror a JS throw that ends the run: `ConsoleLogger::error` with
`throwOnError` (as the TS logger throws `Error`) and DataView/TypedArray
`RangeError`s. `console.warn`/`console.error` calls in the TS (not via the
logger) → `consoleWarn`/`consoleError` (stderr). The logger prints every level
to stderr (node sends debug/info to stdout; here stdout is the UART).

**Harness hooks.** Where the JS harness monkey-patches an instance, the C++
has an explicit hook: `RPPIO::run` is a `std::function` (the host sets it to a
no-op and steps PIO itself; there is no `setTimeout`), and
`CortexM0Core::executeInstructionOverride`, when set, is called by
`RP2040::step()` instead of `executeInstruction()` (`--core1-slow`).
Two more, empty by default and not in rp2040js: `FIFO::onPull` is called with
every value `pull()` returns (test/emu/tmds.mjs wraps the PIO TX FIFOs'
`pull`), and `RPPPB::onWrite(offset, value)` at the start of every PPB
`writeUint32` (rp2040emu.mjs's `ppbWriteTrap` wraps `ppb.writeUint32`).

## Differences from TS that cannot be avoided

- `GPIOPin`'s `lastValue = this.value` runs before `ctrl`/`padValue` exist in
  TS, giving `GPIOPinState.Input`; the port initialises it to that.
- Listener sets (`Set<GPIOPinListener>`) cannot deduplicate `std::function`s;
  adding the same listener twice calls it twice.
- `RPPIO.run` and `Simulator.execute` do one batch instead of re-arming with
  `setTimeout`.
- `RP2040.flash16` is not ported (nothing in the chip uses it).
- `RP2040.logger` is declared before the peripherals (TS initialises it after
  them; TS would crash if a constructor logged).
