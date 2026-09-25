# Development environment

What the test suite (`make test`, `test/run.py`) needs, and how to get it on a
stock Ubuntu 24.04 machine such as a cloud container. `tools/setup_ubuntu.sh`
does everything except KiCad.

| Tool | Used by | Where it comes from |
|---|---|---|
| OSS CAD Suite: GHDL, Yosys + ghdl plugin, Verilator, SBY, bitwuzla, nextpnr | HDL, formal, synthesis, the whole-machine emulator's main board | the YosysHQ release tarball in `/opt/oss-cad-suite`. Ubuntu's packages are too old: Yosys 0.33's smtbmc fails BUS-004's induction step and passes bitwuzla 0.1's command line. |
| Nim + sdl2 | `tools/sim.nim` and its tests | apt `nim`; the `sdl2` wrapper from git (`~/.config/nim/nim.cfg` points at it) |
| arm-none-eabi-gcc, pico-sdk, PicoDVI, rp2040js | the RP2040 card firmware and its emulated tests | apt; `tools/fetch_sdks.sh` |
| ESP-IDF v5.5.5, Espressif QEMU | the Wi-Fi firmware, WIFI-003, E2E-003 | `tools/fetch_sdks.sh`. If dl.espressif.com is unreachable, `tools/setup_ubuntu.sh` seeds `tools/devenv/espidf.constraints.v5.5.txt` (a hand-written stand-in with the IDF 5.x major versions, not Espressif's file) and sets `IDF_PIP_WHEELS_URL=` so pip uses PyPI only. QEMU and openocd need `libslirp0` and `libusb-1.0-0`. |
| ngspice, TI PSpice models | POW-*, THM-001 | apt; the TI models are fetched from www.ti.com by `hw/power/models/fetch.py` (pinned by SHA-256; not redistributable) |
| KiCad 10, Freerouting | the board tests (BRD-001, WIFI-004, E2E-006, the board rows) | below |

**Emulator and simulator** (David, 2026-09-25):

- **The emulator** is the native whole-machine emulator in `emu/machine`
  (`CUPC8_EMU=native`, built by `tools/emu_machine_build.sh`; see its
  README). It runs the chipset RTL (Verilated) and every card's real
  firmware, and must be **cycle perfect**; the end-to-end tests
  (`test/emu/test_e2e.mjs`) run on it. `test/emu/machine.mjs` (rp2040js) is
  the legacy JS emulator, kept but no longer updated. Watch it in a browser
  with `tools/machine_view.mjs --native`.
- **The simulator** (`tools/sim`, from `tools/sim.nim`) is the interactive
  way to run real CUPC/8 software locally and build programs: the CPU in
  Nim and the cards' firmware cores compiled in (`tools/simcards.nim`). It
  is not cycle exact, but it must always run the current kernel, ROM,
  memory map and card commands.

## KiCad 10

The board scripts write KiCad 8 files, which Ubuntu's KiCad 7 cannot read.
Without a KiCad 10 package, the official `kicad/kicad:10.0.6-amd64-full`
container image (from any registry mirror, e.g. mirror.gcr.io) can be
unpacked into `/opt/kicad10` and run as a chroot with
`tools/devenv/kicad10-run`, which bind-mounts `/home`, `/tmp` and the proxy's
CA bundle so paths are the same inside and out:

```
CUPC8_OFFLINE=1 /opt/kicad10-run python3 hw/boards/wifi.py
CUPC8_OFFLINE=1 /opt/kicad10-run python3 test/run.py BRD-001
```

Inside the chroot, add numpy (for `hw/tools/logo.py`) and KiCad's default
global library tables in `/root/.config/kicad/10.0/`. Freerouting 2.4 (a jar
from its GitHub releases) needs Java 25, so it runs on a bundled Temurin JRE
under `/opt/freerouting`. `CUPC8_OFFLINE=1` skips the JLC stock check when
jlcpcb.com is unreachable. Without `KAPLAN_LOGO` (the logo's SVG, not in the
repository), the committed logo footprint is used.

## Hosts

GitHub (git and release assets), PyPI, the Ubuntu archive; www.ti.com for the
power models; jlcpcb.com for stock checks; dl.espressif.com is optional.
