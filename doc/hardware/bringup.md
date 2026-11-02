# First-article bring-up log

The narrative the first-article plan asks for ([first-article-plan.md](first-article-plan.md),
"Recording results"). Measurements that close gates go to `doc/hardware/fa-results/` as JSON.

## 2026-11-02 (David at the bench)

**Units.** Main board "unit 1" (the board in use from 11:11). System card A: RP2040
`E665B448873D2132`; system card B: `E665B44887675335`. CPU card fitted from 11:24.
Host logs and readbacks: `build/bringup-20261102/` (not in git).

**Skipped.** The Stage 1–3 inspections, short screens and current-limited first power
(MB-107, MB-101 currents, MECH-101) were not done before cards were fitted. 1V2 read
1.2 V at TP7 and 1207–1216 mV through sysctl. The J1 source advertises default USB
only (CC ≈ 440 mV), not the 3 A the plan requires for full loads.

| Step | Result |
|---|---|
| MB-102 sysctl enumerates | PASS on both system cards: BOOTSEL → `sysctl.elf` → `1209:c8c8`, `ping`/`status` |
| MB-103 chipset bitstream | PASS after fix 1: qualified `chipset.bin`, 135100 bytes written, verified, configured in 3.8 s |
| MB-104 SRAM | PASS: 512 KB × 4 patterns (address-unique, random, complement, 55/AA) through the bridge, 0 bad bytes |
| MB-105 ROM | PASS: SST39SF040 ($BF/$D7); `kernel-program.bin` written and verified; full 512 KiB readback = release `kernel.rom` |
| CC-101 CPU card | after fix 2: qualified `cpucard.bin` written, verified, configured; POST $20 → $80, the kernel runs. The 100-instruction single-step trace diff is not done yet |
| (beyond M1 order) | BASIC over the USB console: `CUPC/8 BASIC 2026.09`, a `for` loop printed 7 14 21, `poke 61440, 85` set GPO $55 |

### Fix 1: the iCE40 leaves a blank flash in deep power-down

Both W25Q32JV flashes (main U8, CPU card U2) read JEDEC `ffffff`. Traced with the
diagnostic firmware (`fw/rp2040/sysctl_diag`) and a DMM, no scope:

- wiring at U8 correct (static patterns: SCK→6, MOSI→5, MISO→2, CS→1; VCC/HOLD/WP 3.3 V);
- the flash never drove DO (the read followed the RP2040's own pull);
- after `0xAB` (release from deep power-down) both answered `ef4016`;
- releasing CRESET for 2 s with a blank flash (CDONE stays 0), then holding again: `ffffff` again.

An iCE40 that fails to configure from a blank flash leaves the flash in deep power-down,
where it hears only `0xAB`. sysctl now sends `0xAB` when it holds an FPGA
(`fw/sysctl/core/spiflash.c` `fl_wake`, from `fpga_hold`). The host flash model
(`fw/test/sysmodels.c`) and the emulator's (`emu/machine/fpgaconfig.h`) model the sleep;
without the fix `test_sysctl` fails 10 checks, and the native machine reproduces the bench
(`ffffff`, program timeout).

### Fix 2: CS_n must rise before SCK is released

With fix 1 the CPU card flash read correctly but every sysctl program left it erased
(verify failed at $000001), while the diagnostic's writes worked. Status registers
`00 02 60` (no protection), WEL sets. sysctl's `release_bus` let go of SCK before CS_n:
on FL1 the CPU card's 10k pull-up (R4) on FL1_SCK raises SCK while CS_n is still low, an
extra clock that makes a W25Q drop write enable, erase and program. FL0 has no SCK
pull-up, so the chipset flash programmed. `release_bus` now drives CS_n high first.
Not caught by the models: both exchange whole bytes, not pin edges. Confirmed on the
bench at 11:48: the CPU card flash programmed and the CPU booted the kernel.

### BOOTSEL without the wire

The control port at 1200 baud now reboots sysctl into the RP2040 boot ROM
(`tud_cdc_line_coding_cb`), and `cupc8.py bootsel [FILE]` does that and loads FILE with
picotool: `python3 tools/cupc8.py bootsel build/rp2040/sysctl.elf`. Confirmed at 11:49
with the machine running throughout (GPO stayed $80). Cards that still run firmware
from before this need the TP4 wire once.

### Fix 3: the RP2040s hang in clock set-up after a cold start

After every main-board power-on the system card never reached USB (no kernel USB events),
while BOOTSEL, `picotool reboot` and `cupc8.py bootsel` always worked. A boot-trace build
(`sysctl_boottrace`: the TX/RX LEDs show the start-up stage) stopped with TX on, RX off:
past the early resets, never past the SDK's clock set-up. A RUN tap (full chip reset,
power steady) hung the same way (it had worked once, at 11:13). What the working cases
share: the boot ROM had already started the crystal. With the SDK's 6 ms start-up wait
the 12 MHz X322512MSB4SI (CL 20 pF, 33 pF + 1 kΩ, the same circuit on every RP2040 card,
`hw/boards/rp2040card.py`) is not stable from cold, the PLL does not lock, and the chip
waits for ever. With `PICO_XOSC_STARTUP_DELAY_MULTIPLIER=64` (64 ms): 8 of 8 cold starts
(5 with the trace build, 3 with the real sysctl, 11:57–12:04); 0 of 4 before. Now set for
every RP2040 firmware in `fw/rp2040/CMakeLists.txt`. With it the whole machine cold-boots
by itself: both FPGAs from flash, the CPU to the kernel (GPO $80).

### Fixes 4 and 5: card programming over SWD

`card flash` found no RP2040 in any slot (ACK 7) with two different HDMI cards. Static
patterns through the mux (`sysctl_diag` A/B/C) showed the path whole: the slot 1 channel
carries the card's SWDIO pull-up, SWCLK and SWDIO reach the card's TP2/TP3, RUN high.
- **TARGETSEL clocks.** The core asked `swd_io` for 5 undriven clocks (turnaround, 3 ack,
  turnaround) while the HAL adds each turnaround on a change of direction (its contract
  in `sysctl.h`): 7 on the wire, the ID two clocks late, nothing selected. Now 3. The host
  HAL now adds the turnaround as the RP2040 one does and the SWD target model counts every
  clock: the old code fails 24 checks.
- **The boot ROM table.** On the RP2040 B2 the function table is at $7A, 16-bit aligned;
  `cupc8.py` read whole words at it, so every entry was shifted (`boot ROM has no IF
  routine`). It now reads halfwords; the model's table moved to $7A.

Then `card flash 1 gpu.elf`: 40 KB written and verified in 3.7 s; after `cupc8.py reset`
the kernel found the GPU card and the console shows on the HDMI monitor (12:20).

### Open

- Card B's unprovoked USB drop at 10:37:46 is unexplained (possibly a clock-set-up hang
  after a reset; not seen since fix 3).
- The emulator does not model the RP2040 crystal oscillator (`XOSC_BASE` is an
  `UnimplementedPeripheral`, `emu/rp2040/src/rp2040.cpp`), so it cannot see fix 3's cause.
- **Next revision:** the cards' X322512MSB4SI crystal (CL 20 pF, 33 pF caps, 1 kΩ in
  XOUT) starts slowly from cold. Check its start-up margin against Raspberry Pi's hardware
  design guide or fit the reference ABM8-272-T3 (CL 10 pF, 15 pF caps).
- `status` reports "CPU card FPGA configured" with no CPU card: CPU_CDONE has a pull-up
  on main; the report should depend on presence.
- `test/hw/test_cosim_fpga_config.py` does not run against the current boards (its
  default `build/hw` set fails slot binding; the F51mm source tree fails on the storage
  card's SD_nCS pad), so its new blank-flash case is unrun. The same scenario passes on
  the native machine through `test/hw/fpga_config_probe.mjs`.
- No `selftest ram`, `selftest slots`, `cpu load` or `trace --diff` in `cupc8.py`
  (`debugging.md` names them); MB-104 was scripted with `ram write`/`ram read`.
