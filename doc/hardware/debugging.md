# Debugging the hardware

There is no prototype before the boards are made, so the boards themselves
have to be debuggable. This lists what goes on them, what each feature is
for, and what to reach for when something does not work.

Every feature here is a requirement on the schematics, and is checked by the
board tests in `test/catalogue.toml`.

## 1. LEDs: what the machine tells you without any tools

| LED | Where | Meaning |
|---|---|---|
| 5V, 3V3, 1V2 | main board, one per rail | the rail is up. The first thing to look at. |
| 1V2 (card) | CPU card | the card's own core rail |
| CDONE ×2 | main board (chipset), CPU card | the FPGA is configured. Off = configuration failed. |
| GPO D1–D8 | main board | the CPU's `$f000` port: the boot ROM's POST code, then whatever the kernel writes |
| ACT | graphics card | video output is running |
| KBD | IO card | a keyboard is enumerated |
| LINK | Wi-Fi card | associated to a network |
| PWR | each card | the card has 3V3 |

**POST codes** on the GPO LEDs, from the boot ROM (`doc/hardware/memory-map.md`):

| Code | Stage | If it stops here |
|---|---|---|
| $01 | boot ROM entered | the CPU runs and reads the ROM |
| $02 | RAM test | RAM, its address/data lines, or the chip select |
| $04 | slot probe | an SPI transfer to a card hangs |
| $08 | console banner | the graphics card answered IDENT but not the text commands |
| $10 | kernel header | the ROM contents are wrong: reprogram it |
| $20 | copying the kernel | ROM banking or RAM writes |
| $40 | checksum | the copy is corrupt: suspect the bus or marginal timing |
| $80 | jumping to the kernel | after this the kernel owns the LEDs |
| $82 | RAM test failed | stuck or shorted RAM lines |
| $90 | no valid kernel in ROM | reprogram the ROM |
| $91 | kernel too large | rebuild it |
| $A0 | kernel checksum bad | reprogram the ROM; if it repeats, suspect the bus |

A failure that reaches the console also prints a message.

## 2. The RP2040 as a debug probe

The system controller is on the CPU bus's doorstep and is reachable over the
single USB-C port, so most debugging needs no other equipment.

| `cupc8.py` command | What it does | Use it when |
|---|---|---|
| `status` | rails, CDONE, card presence, CPU state (halted/waiting/stopped), card IDs | first contact with a new board |
| `ram poke/peek/dump` | read and write SRAM with the CPU stopped | the CPU never runs |
| `selftest ram` | a March C- pattern over all of RAM | POST $02 fails |
| `rom read/write/verify` | program the ROM chip in place | ROM contents, or POST $10/$90 |
| `fpga flash` / `fpga load` | program or directly load a bitstream | CDONE stays off |
| `stop` / `step` / `step-cycle` | halt the CPU, then advance one instruction or one bus cycle | the CPU runs but does the wrong thing |
| `trace` | the last 512 completed bus cycles: address, data, read/write, opcode-fetch | anything that goes wrong "somewhere" |
| `trace --diff` | run the same program in `sim.nim` and compare traces instruction by instruction | the machine diverges from the simulator |
| `card flash/ident` | reprogram or identify a card | a card is silent |
| `power` | what the USB-C source advertises, and per-slot current | brown-outs, a card that trips the supply |

`trace --diff` is the strongest tool: the simulator is the reference model, so
a mismatch points at the exact cycle where the real machine differs.

## 3. Test points and links

- **Test pads** on every rail, every CPU-bus and memory-bus signal, both SPI
  buses, the clock and the resets, so a scope or logic analyser can attach
  without soldering to a pin.
- **0 Ω links** in each rail and each slot's 5 V feed: bring the board up one
  section at a time, and isolate a card that pulls a rail down.
- **Current-sense resistors** (50 mΩ) in each slot's 5 V feed with pads either
  side, so a meter reads the card's current.
- **UART headers** from the sysctl RP2040 and from each card MCU.
- **SWD pads and a BOOTSEL button** on every card: the normal path is through
  the slot, and these are the fallback if that path is the thing that's broken.
- **A spare main board** in the build, so a board-level fault doesn't stop
  everything.

## 4. Bring-up order

Each step is a test in the catalogue (`test/run.py --kind hw`), and each one
only depends on the steps before it.

1. **MB-101** rails, with nothing else fitted.
2. **MB-102** sysctl enumerates over USB.
3. **MB-103** chipset bitstream, CDONE on.
4. **MB-104** RAM march test through the bridge, CPU still in reset.
5. **MB-105** program and verify the ROM.
6. **CC-101** fit the CPU card, load it, single-step the boot ROM and diff the
   trace against the simulator.
7. **MB-106** slot signals and card presence.
8. **GC-101 / IC-101 / WC-101** one card at a time: flash it, IDENT it, then
   its own function (test pattern, typing, network).

## 5. Symptom → first checks

| Symptom | Look at |
|---|---|
| No LEDs | USB-C source, input fuse, 5 V rail, the rail links |
| sysctl does not enumerate | 3V3, the 12 MHz crystal, USB D+/D− (test pads), BOOTSEL |
| CDONE stays off | config flash contents (`fpga flash`), CRESET, the 1V2 rail |
| POST stops at $02 | `selftest ram`, then the address and data lines on the pads |
| POST stops at $04 | SPI pads: does SCK/MOSI move? Is one card holding MISO low? |
| Nothing on screen | graphics card ACT LED, `card ident`, HDMI cable, then the TMDS pads |
| No keyboard | IO card KBD LED, slot current, VBUS fault flag in `status` |
| Random crashes | `power` for brown-outs, then `trace` after the fault |
| Works stopped, fails running | timing: check the clock, then re-run the timing budget against the built board |
