# Milestone 1 — A real CUPC/8

## Requirements (as given by David, 2026-09-22)

- The first milestone is a **completely working CUPC/8 computer**, designed in
  **KiCad**, with the boards made and **pre-populated by JLCPCB**.
- There is a **main board** and **expansion/side boards** that slot in using
  something like small PCIe or M.2 connectors (form factor only).
- The main board carries **all the main computing components**, including
  **power delivery via 5V USB**.
  - *Amended:* the CPU itself may live on a plug-in **CPU card** (connected
    via one or two connectors) so a discrete-logic CPU can replace the FPGA
    CPU later.
- Expansion boards required now:
  - an **IO board** that lets you use a **USB keyboard**;
  - a **graphics board** that outputs **HDMI**;
  - *Added:* a **Wi-Fi networking card**.
- *Added:* the main board has **extra slots** for future expansion cards.
- There must be a **physical ROM** where the **boot ROM and then the kernel**
  reside.
- **All programming must be in-system.**
- **Everything must be simulated and tested like crazy** before anything is
  sent off to be manufactured.

## Decisions

| Area | Decision |
|---|---|
| CPU | Plug-in **CPU card** in a PCIe x8 card-edge socket. M1 card: the existing `cpu.vhd` on an iCE40HX4K-TQ144 (the same part as the chipset), booting from its own configuration flash. The M2 discrete CPU card uses the same socket. |
| Chipset | **iCE40HX4K-TQ144** on the main board, booting from its own configuration flash: MMU, SPI master, IRQ controller, ROM windows, in-system programming bridge. It sits in-line between the CPU bus and memory, and holds the CPU in reset until the CPU card is configured. |
| System controller | **RP2040** on a removable **system card** in its own keyed PCIe x4 slot, with its own USB port ([system-slot.md](hardware/system-slot.md)). It programs everything in-system: both FPGAs' flash, the ROM, and the card MCUs. It can also stop, step and trace the CPU. **Once programmed, the machine works fully without it.** Each FPGA boots itself, the main board has its own oscillator and reset supervisor, cards run by default, and the USB-C power policy is a main-board comparator the kernel reads. |
| RAM | External SRAM IS62WV5128EBLL-45 (512K×8, 45 ns), 64 KB used |
| ROM | **SST39VF040** 512 KB parallel NOR on the chipset's memory bus: boot ROM + kernel, soldered, programmed in-system |
| Slots | 6× identical **PCIe x1 card-edge** (36-pin) I/O slots with a custom pinout: SPI, IRQ, power, and a programming port (SWD or UART bootloader). Any I/O card works in any I/O slot. 3 are used by M1 cards, and 3 are free. The system card has its own keyed slot. |
| IO card | RP2040 as a USB host for a HID keyboard, SPI slave to the CPU |
| Wi-Fi card | ESP32-C3-MINI-1U module (external antenna) running the network stack on-card (DHCP/DNS/TCP/UDP/TLS), exposed to the CPU as 4 sockets over SPI |
| Graphics card | RP2040 + PicoDVI, 640×480 DVI on an HDMI connector, driven by a **custom 8-bit-friendly command set** over SPI |
| Board thickness | Every card that plugs into a socket (the CPU card, the system card and the I/O cards) is **1.6 mm** thick. The PCIe CEM card-edge spec is 1.57 ± 0.13 mm; that's JLC's standard thickness, and also the thickness of its 4-layer JLC04161H-7628 stackup. Their edge fingers are hard gold with a 45° chamfer, laid out to the PCIe CEM finger dimensions. The fab-package check fails any card whose thickness, finger finish or chamfer is missing or different. |
| Indicator LEDs | *Added 2026-09-24:* every board has a **small, visible power LED**, in the **same place on every board**: centred 3 mm in from the body's top-left corner (component side up, fingers or connector at the bottom). All I/O cards share one outline (`slot.md`, Mechanical), so their power LEDs line up exactly. The system card, in its own slot, may put it elsewhere. Every other LED (activity, link) sits **along the top edge**, in a row with the power LED, so a board's state reads the same way on every card in the machine. Boards that move data to the outside world also have **TX/RX activity LEDs**: the Wi-Fi card (TX and RX on its sockets), the IO card (one LED: a keyboard only sends) and the system card (TX and RX on its USB link to the host). |
| Branding | Every board carries the **Kaplan Labs logo** on its top silkscreen, generated from `~/.config/omarchy/branding/kaplan-labs.svg` by `hw/tools/logo.py`. At least 10 mm wide, because smaller loses detail below JLC's 0.15 mm silkscreen minimum. |
| Board revision | *Added 2026-09-24:* every board (the main board and every card) carries its **name and revision** on the top silkscreen, in the **bottom-right corner** where it fits, as `<name> rev <X>` (for example `CUPC/8 Wi-Fi rev A`). The same revision is in the board's title block, which the Gerbers' X2 attributes carry, so a respun board can always be told from the one before. Revisions are letters, starting at A. Each board script keeps its own `REVISION`, and it is bumped for every order that changes the board. The board pipeline (`hw/tools/kicadgen.py`) refuses to build a board without one, and the silkscreen check keeps the marking clear of pads and courtyards. |
| Whole-machine emulator | *Added 2026-09-23:* an emulator of the **complete machine**, accurate to the hardware and the cards: the CPU and chipset at bus-cycle level, and every card running **its real firmware image** (RP2040 cards in the patched rp2040js, the ESP32-C3 in Espressif's QEMU), wired to the chipset at the SPI pin level as on the boards. The instruction-level simulator (`tools/sim.nim`, C models of the cards) stays for fast tests; the emulator is what the end-to-end tests run on. |
| Emulator speed | *Added 2026-09-23:* the whole-machine emulator runs **natively and in parallel without losing fidelity**: a native (C/C++) RP2040 emulator with the same cycle model as today (dual core, per-cycle PIO with dividers and delays, DMA, USB), each card on its own thread synchronised with the main board in conservative time windows, falling back to per-edge lockstep for a card while its SPI frame (or the bridge) is active, and the main-board loop native around the Verilated core. EMU-001/002/003 and the real-binary card tests (GPU-004/005, IOC-004, SYS-006) are its acceptance suite. Target: from ~48× slower than real time to a few times slower. |
| Verification | **Everything is simulated and tested before hardware is ordered.** There is no hardware prototype. The full matrix is [verification.md](hardware/verification.md): HDL lockstep and formal proofs, real firmware binaries in emulators, a co-simulation wired from the KiCad netlists, power, SI, thermal and mechanical checks. Nothing is ordered until `make verify` is green and `fab-readiness.md` is signed off. |

## Specifications

- [Memory map and boot chain](hardware/memory-map.md)
- [CPU bus and CPU socket](hardware/cpu-bus.md)
- [Slot connector](hardware/slot.md)
- [System slot and system card](hardware/system-slot.md)
- [System controller firmware and USB protocol](hardware/sysctl.md)
- [GPU protocol](hardware/gpu-protocol.md)
- [IO card protocol](hardware/io-card.md)
- [Wi-Fi card protocol](hardware/wifi-card.md)
- [Power budget](hardware/power.md)
- [Key parts and JLC stock](hardware/parts.md)
- [Verification contract](hardware/verification.md)
- [Debugging the hardware](hardware/debugging.md)

## Done when

The assembled boards, powered only from USB-C, boot through the boot ROM to
the BASIC prompt on an HDMI monitor, and you can type on a USB keyboard. The
Wi-Fi card joins a network and fetches a page over TCP. Every
device was programmed through the system card's USB port, and the machine still
boots and runs with the system card removed.

## Final step before sign-off

When everything else is done (specs, implementation, the tests all green, and
the fab packages), run `codex-p` with the astra model at medium reasoning to
critique the whole design, and to propose further tests for every part of the
machine. Consider every comment. Fix anything that is a bug; other suggestions
are optional, and each gets a recorded yes/no with a reason. Worthwhile proposed
tests go into the catalogue and are implemented.

Every bug fixed anywhere gets a test that fails on the bug (a counterexample)
and passes on the fix, so it cannot come back.
