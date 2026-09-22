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
| CPU | Plug-in **CPU card** in a PCIe x8 card-edge socket. M1 card: the existing `cpu.vhd` on an iCE40HX4K-TQ144 (the same part as the chipset), configured by sysctl. The M2 discrete CPU card uses the same socket. |
| Chipset | **iCE40HX4K-TQ144** on the main board: MMU, SPI master, IRQ controller, ROM windows, in-system programming bridge. It sits in-line between the CPU bus and memory. |
| System controller | **RP2040** on the main board. It owns USB-C and programs everything in-system: the FPGA config flash, the CPU-card FPGA, the ROM, and the card MCUs over SWD. It can also stop, step and trace the CPU. |
| RAM | External SRAM IS62WV5128EBLL-45 (512K×8, 45 ns), 64 KB used |
| ROM | **SST39VF040** 512 KB parallel NOR on the chipset's memory bus: boot ROM + kernel, soldered, programmed in-system |
| Slots | 6× **PCIe x1 card-edge** (36-pin) sockets with a custom pinout: SPI, IRQ, power, and a programming port (SWD or UART bootloader). 3 are used by M1 cards, and 3 are free. |
| IO card | RP2040 as a USB host for a HID keyboard, SPI slave to the CPU |
| Wi-Fi card | ESP32-C3-MINI-1U module (external antenna) running the network stack on-card (DHCP/DNS/TCP/UDP/TLS), exposed to the CPU as 4 sockets over SPI |
| Graphics card | RP2040 + PicoDVI, 640×480 DVI on an HDMI connector, driven by a **custom 8-bit-friendly command set** over SPI |
| Branding | Every board carries the **Kaplan Labs logo** on its top silkscreen, generated from `~/.config/omarchy/branding/kaplan-labs.svg` by `hw/tools/logo.py`. At least 10 mm wide, because smaller loses detail below JLC's 0.15 mm silkscreen minimum. |
| System controller placement | Moving sysctl onto a removable **system card** in a keyed slot, so the computer runs without it. Decided 2026-09-22; the rework of the specs, pins and sysctl core is pending. |
| Verification | **Everything is simulated and tested before hardware is ordered.** There is no hardware prototype. The full matrix is [verification.md](hardware/verification.md): HDL lockstep and formal proofs, real firmware binaries in emulators, a co-simulation wired from the KiCad netlists, power, SI, thermal and mechanical checks. Nothing is ordered until `make verify` is green and `fab-readiness.md` is signed off. |

## Specifications

- [Memory map and boot chain](hardware/memory-map.md)
- [CPU bus and CPU socket](hardware/cpu-bus.md)
- [Slot connector](hardware/slot.md)
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
device was programmed through the single USB-C port.
