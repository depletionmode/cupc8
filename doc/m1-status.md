# Milestone 1: status and decisions log

What is decided, what is running, and what is left, kept current so the work
survives a lost session. Newest first within each section. Specs live in
`doc/hardware/`; this file points at them.

## Decisions carried forward (2026-09-25–27)

- BASIC is a loadable program at $7000, loaded from SD or the ROM fallback;
  networking stays in the kernel (`proposals/basic-program.md`,
  `proposals/kernel-api.md`). Keep BASIC's checksum on reload.
- Banked RAM is 512 KB with the $8000–$bfff window selected by RAM_BANK
  (`proposals/extended-ram.md`). SRAM A16–A18 must be connected.
- USB console uses the system card's second CDC port, with the documented
  timeout (`proposals/usb-console.md`).
- The native emulator runs Wi-Fi QEMU in lockstep. The 125 MIPS versus
  160 MHz approximation is recorded in `emu/machine/README.md`.
- M1's e-ink display is the Waveshare 7.5-inch HAT V2
  (`hardware/eink-card.md`).
- Main board: six layers; POWER and RESET at the front, machine initially
  off, system card unpowered while off (`hardware/power.md`). Eight layers
  would need a new cost decision. Preserve socket alignment and mounting
  geometry while opening routing channels.
- All eight boards need assembled parts, stock at twice the order quantity,
  branding/revision and the common LED placement. Final stock is checked
  online. David performs the fabrication hand checks and places the order.

## Decisions (David, 2026-09-24)

- **Card form factor:** the CPU card has the I/O card outline (62 × 39.05 mm
  above the tab) on its x8 tab; on the main board the CPU socket is first,
  then the six I/O slots, one row, all aligned. The system card keeps its
  own shape, its socket off to one side (`slot.md`, `cpu-bus.md`).

- **Power: the full M1 machine requires a USB-C 3.0 A source** (four cards
  no longer fit 1.5 A with margin). Below 3 A the radio stays off and SD
  writes are refused. The power agent re-derives the CC threshold, the
  input switch/fuse and the POW/THM checks; the main board takes its parts
  from `hw/power/design.py`.

- **E-ink card: built for M1** as the second graphics option (replaces the
  HDMI card, type $01; `proposals/eink-gpu.md` Decisions; pins `eink_mcu`).
  The native emulator gets a UC8179 panel model.

- **Storage card** (card type $04, `hardware/storage-card.md`): a separate
  RP2040 card for files, microSD in M1, a medium-neutral protocol so a later
  card can be tape or a hard disk. Replaces the microSD on the IO card
  (`proposals/io-microsd.md`, superseded). FatFs on the card, `SAVE` writes
  text, 4 handles. The IO card stays keyboard only.
- **Earlier e-ink exploration decision superseded:** the e-ink card is included in M1.
- **Native emulator** (`emu/`) is the emulator from now on; the JS one
  (`test/emu/machine.mjs`) is legacy and not kept up to date. Another agent
  owns `emu/`'s core work.
- **Card bevel 30°** (JLC's nearest to CEM's 20° ± 5°), a written waiver
  (`hardware/fab-waivers.md`).
- **Wi-Fi antenna**: MHF III-to-SMA lead C709347 and SMA antenna C1509156,
  both loose from JLC (the module's receptacle is MHF III, not U.FL).
- **Out of scope**: a missing CPU card (broken hardware); cards plugged or
  pulled while powered (`slot.md`).
- **LEDs**: a power LED in the same place on every board, other LEDs in a
  row along the top edge, TX/RX LEDs where data leaves a board
  (`milestone-1.md`, Indicator LEDs).
- **Board revision** on every board's silkscreen and title block.

## In flight (2026-09-27)

| Work | State |
|---|---|
| Main board | Salt-1 route and deterministic power/ground repairs are merged. The six-layer package has a valid receipt, 0 KiCad DRC violations, 0 opens and 0 parity errors. Worst slot is 16.85 mΩ at nominal 20°C copper, but 20.17 mΩ at 70°C before thickness tolerance; MB-005 remains red. The isolated, pushed `main-power-trial` branch adds U2/C15 placement and parallel power copper. It passes a source-replayed KiCad DRC with zero opens and models 19.128 mΩ at 100°C under assumed copper, but 20.452 mΩ at 115°C with thinner via plating. Finished copper minima, GND contact and thermal coupling remain unbounded; the trial is not merged. |
| BASIC follow-ups | Packed ROM image, approved dead-code removals, run/hook handshake, isolated Nim cache and assembler comment parsing. Simulator checks precede emulator checks. |
| Board verification | All eight boards rebuilt under the latest verifier and have valid receipts with clean KiCad DRC, ERC and schematic parity. Independent plotted fab checks stop at the 0.20 mm connector-notch copper-edge gap on all seven cards, versus the 0.30 mm project rule. Main plotted geometry passes and stops at the missing human CPL review record. The notch's fabrication and mating acceptance requirements are recorded in `hardware/card-notch-qualification.md`. Wi-Fi WC-005/WC-010 remain red at ESR, ground contact and thermal transfer; CPU CC-005 remains red for unbounded physical parameters. Current CPL overlays and top/bottom PNGs were refreshed for all eight boards. |
| SI and schematic co-simulation | The four routed HDMI pair field-model subsets pass against the GPU receipt; full analog SI remains red. Routed main copper is available to the IBIS diagnostic. Strict E2E-001..004 remain red with 389 coverage gaps after routed nPOR, ROM/SRAM write-enable, ROM DQ0, slot-select/shared SPI links, 30 card-local slot nets and 30 QSPI boot nets plus pin-exact waivers for 45 unused reserved contacts. Root wiring and native runtime mutation checks passed after rebuilding the addon. |
| Final gate | The full `make verify` attempt was stopped at the long Wi-Fi lockstep mutation tail before a valid suite result; 17 nonhardware catalogue rows remain pending. Fab readiness is red. Integrate further co-simulation work, rerun the full gate, inspect renders and complete David's hand checks. No manufacturing upload or order. |

## Done (recent)

- All eight boards regenerated after the Gerber precision checks and passed
  ERC, board DRC and schematic parity; their receipts require a final refresh
  after the later CPU power verifier edit.
- CPU card now uses six layers. The seven card pipelines were reported complete
  at handoff; final integration reruns and live stock checks remain required.
- SD card model in the native emulator (EMU-008), STO-003, E2E-007 (BASIC
  SAVE/LOAD on the whole machine).
- Storage card software: FatFs core, RP2040 port, kernel/BASIC, 2668 host
  checks, KRN-006.
- Power for four cards and a 3 A source: TPS259470 eFuse, 3.5 A PTC,
  TLV62569PDDCR, PWR_HI = 3.0 A; below it no radio and no SD writes.
- Main board: source-driven salt-1 route, post-fill KiCad DRC/parity/connectivity
  all zero, and current Gerber/BOM/CPL/render receipt. The hot-copper power
  and signal-integrity gates remain open.

- Wi-Fi card board through the whole pipeline (WIFI-004), TLV62569 buck
  after POW-003/THM-001, TX/RX/LINK LEDs, standard outline.
- `cupc8.py` resyncs on a PING nonce (a killed run's late reply no longer
  passes for the next run's; HOST-002).
- Keyboard path on the whole machine: IO card serves the slot during USB
  enumeration; boot ROM and kernel retry a not-ready READ.
- Power/thermal (4.4/4.5), footprint/pinout/rotation (4.3, BRD-001),
  mechanical fit (4.7, MECH-*), fab readiness report (`make verify`).

## Left before ordering

- E2E-001 (co-sim from the netlists);
  E2E-002/003/004 green on the native emulator; SI (4.6); the fab-readiness
  hand checks; David's sign-off; the final design critique.
