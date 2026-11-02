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

### USB-C PD chargers do not switch on (design; rework deferred)

A USB-C charger with a C-to-C cable leaves VBUS off (TP1 VBUS_F 0.1 V) while CC1 (TP8)
reads 0.7 V and CC2 (TP9) 0.2 V. U1, the USBLC6-2SC6 on CC1/CC2, has its rail pin 5 on
VBUS_F: before VBUS is up its rail diode clamps CC to VBUS_F + one diode (0.1 + 0.6 V)
and back-feeds VBUS_F. Below 0.8 V a source offering 3 A takes the CC load for Ra (a
powered cable), not Rd, and never turns VBUS on. A USB-A-to-C cable has no such check,
so it works, but the board then sees default USB only: the kernel refuses Wi-Fi
(`NET_E_POWER`) and SD writes (`ST_E_POWER`). **Rework (later):** lift U1 pin 5 (ST
allows the USBLC6's VBUS pin unconnected; the lines keep the clamp to ground) or remove
U1. **Next revision:** ESD on CC that clamps to ground only, rated for CC's 5.5 V.

Reworked on main unit 1 (pin 5 lifted): the USB-C charger then powered the board
(`Type-C 3.0 A`, CC 1651 mV), but after one unplug it never powered it again. Not
yet diagnosed: plug orientation (CC2 side: R2, J1 B5), U1 pin 5 touching its pad
again, or the charger.

### Fix 3b: a watchdog around the clock set-up

On the USB-C charger the 64 ms wait still hung now and then.
`fw/rp2040/common/boot_guard.c` (every card's firmware) arms the watchdog on
the ring oscillator before the SDK's clock set-up and disarms it after.
First version, the watchdog reset keeping the crystal oscillator running
(meant for a merely slow crystal): 6 of 7 cold starts, one hung until power
was removed, so a stuck oscillator was inherited by every retry. Second
version, the reset also restarting the crystal oscillator: 8 of 8, back on
USB 1.1-5.4 s after power-off (13:03-13:04). Encouraging, not proven: at
the old 1-in-7 rate 8 in a row is still 29% likely; keep counting. If it
comes back, the hardware margin is next (R1, the 1 kΩ in XOUT, or the load
capacitors).

### Wi-Fi programming: slot 6 (F700)

Resumed at 13:09. David identified the connector by its nearby fuse **F700**,
which is **slot 6**, not slot 3 as targeted earlier. On slot 6 the ESP32-C3
immediately answers over the programming UART: download mode works; normal boot
reports `invalid header: 0xffffffff` (no valid boot image). The earlier silent
slot-3 probes do not establish a Wi-Fi hardware fault.

Programmed the F51mm release's ESP32 **card** bootloader, partition table and
application, merged at their `flasher_args.json` offsets, through
`cupc8.py card flash 6`. esptool identifies chip revision v0.4, 4 MB XMC flash,
MAC `30:ed:a0:56:5f:04`; write hash verified. Merged image SHA256:
`bbd3e87298c01573a61a6fe6fa42f0f02956755c93a2ef9de590c39e2ef21099`.
UART capture confirms `cupc8_wifi` starts, ESP-IDF 5.5.5, Wi-Fi station mode,
without a boot error in the four-second capture. After machine reset the boot
ROM's slot table at $0002 reads `00 00 00 00 00 03`: Wi-Fi identified in slot 6
over SPI. Source detection remains default USB (~430 mV CC); David authorized
`power force` for the radio tests.

Normal `build/rp2040/sysctl.elf` was reloaded and verified before this work,
at David's request. Logs and merged image are in `build/bringup-20261102/`:
`wc101-slot6-uart.log`, `wifi-card-release.bin`, `wc101-slot6-firstboot.log`.

### Wi-Fi scan command and live radio test

Added `net scan` (SSID, signal in dBm, open/secured). The ESP backend now
signals scan completion after the radio finishes, with BUSY maintained until
then; the kernel waits up to ten seconds and handles failures. Failed joins
now report `connect failed` promptly. The ESP ignores the intentional station
leaving event from an old connection during a new JOIN; real disconnect
reasons are logged without passwords.

Flashed the updated ESP application at $10000 (esptool hash verified) and the
new kernel ROM (full 512 KiB readback matches `kernel-scan.rom`). David
explicitly requested trying **without the external antenna**. With `power
force`, live `net scan` completes with `no networks found`. A subsequent JOIN
to `KaplansHome_IoT` reaches the ESP (SSID length 15, save=1), fails with
disconnect reason 201 (`WIFI_REASON_NO_AP_FOUND`), and prints `connect failed`;
`net` reports `link down`. This does not establish radio performance with an
antenna. The user's console was resumed after capturing results, and the
power override remains enabled until reset.

Validation: Wi-Fi core ASan/UBSan 148 checks, zero failures; targeted simulator
scan and kernel layout pass; rebuilt simulator CLI scan passes; native
E2E-013 using real QEMU Wi-Fi firmware passes 13 checks, zero failures,
including `net scan`. Updated card and QEMU images both build. Evidence:
`net-scan-*.log`, `wifi-scan-flash.log`, `rom-readback-scan.bin`, and
`wc101-live-{scan,join,status}-{console,uart}.log` in the host log directory.
Console captures redact the password.

### Storage card: slot 1 (F200)

Resumed at 15:04. David identified the storage connector by fuse F200, slot
1, with no microSD inserted. Flashed `build/rp2040/storage.elf` through SWD:
36 KiB erased/programmed, verified, target running. After machine reset the
boot ROM slot table reads `04 00 00 00 00 00`: storage identified in slot 1.
The kernel `dir` command returns `no SD card`, as expected. Logs:
`storage-slot1-ident.log`, `storage-no-media.log`.

David supplied a microSD in a USB reader and authorized flashing it (using
pkexec). Identified the removable USB device as `/dev/sda`, 15,931,539,456
bytes. Created a DOS partition table and one FAT32 partition at LBA 2048,
label CUPC8, 4 KiB clusters. Rebuilt BASIC and all nine assembly examples
from current source. Copied 15 files: ten PRGs including BASIC and BENCH,
three BASIC demos recovered read-only from the existing `card.img`
(HI1, PRIMES, BOUNCE, all given `.BAS` names), INDEX.HTM and README.TXT.
All file hashes verified, fsck.fat passed; unmounted and powered off the
reader before David transferred the medium. Manifest and preparation log:
`storage-sd-manifest.json`, `storage-sd-prepare.log`.

**Live results.** Initial insertion reported `no file system on the card`;
SWD state showed zero initialized sectors. Resetting just the storage card
made DIR work, although its first two entries printed blank names/zero
sizes. A subsequent whole-machine reset produced the full correct directory
and the banner **BASIC from the SD card**. `LOAD "HI1.BAS"`, LIST and RUN
passed (`hi`). These initial insertion/first-directory anomalies remain
unexplained; robust hot insertion is not established.

With David's authorized `power force`, saved a new `TESTSD.BAS` containing
`10 print "SD WRITE OK"` and `20 end`. After machine reset, NEW then LOAD,
LIST and RUN read that file before any second SAVE and printed the expected
message. This verifies reset persistence, not a physical cold power cycle.
`EXEC "BENCH.PRG"` loaded and ran from SD: CPU 792 K loop instructions/s,
RAM write/read both 133 KB/s, 4 KiB RAM check passed. Restored `power force`
after the reset and resumed the user's console. No storage firmware source
was changed. Physical current/rail tests and cold-power persistence remain
open. Evidence: `storage-boot-load-check.log`, `storage-save-check.log`,
`storage-reload-after-reset.log`, `storage-benchmark-from-sd.log` and
`storage-final-power-force.log`.

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
