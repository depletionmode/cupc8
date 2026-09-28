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

## In flight (2026-09-28)

| Work | State |
|---|---|
| Main board | Salt-9 is replayed into the canonical `build/hw/main` under the strengthened checker: valid receipt, KiCad DRC zero, zero opens and zero schematic parity errors. All ten implemented independent plotted Gerber subchecks pass. The positive J1→F1→U2 hot/min-copper path alone is 73.060 mΩ against the 20 mΩ assembled-loop requirement, with 754 mW modeled instantaneous copper heat at the 3.213 A eFuse limit. MB-005 and board thermal remain red. A relocation trial has four opens/ten DRC findings and only 1.150 mΩ total contact budget left in its ideal-copper sensitivity scenario; the selected connector's published limit is much looser. See `hardware/main-mb005-two-sided-relocation-trial.md`. |
| Cards and fabrication | Canonical CPU, GPU, IO, storage, and Wi-Fi rebuilds have valid receipts, zero pipeline DRC/parity errors, and nine of ten implemented independent Gerber checks pass; the remaining check finds 0.20 mm copper-to-notch against 0.30 mm. At the fixed 3.00 mm pad gap the geometric maximum is 0.255 mm per side at CEM minimum dimensions. E-ink and system canonical rebuilds are paused temporarily for the SI runtime margin. The main board CPL and all other human placement reviews remain unsigned; no manufacturing release. See `hardware/card-notch-qualification.md` and `build/fab-overlays/current` after its final refresh. |
| Power, SI, and co-simulation | Wi-Fi's rebuilt 3V3 sensitivity scenarios pass but fitted capacitor ESR/effective capacitance, return pad/contact resistance, load envelope, and board thermal transfers remain unbounded; WC-005/WC-010 stay red. CPU ideal 3V3 feed is 14.78 mΩ, but CC-005 still lacks fitted contact/load/capacitor and thermal proof. HDMI coupled D0/D1 source-bound diagnostic passes; longer D2/CK runs are in progress on pinned fields. USB three-mesh S11 reverses direction and cannot support continuum extrapolation. Strict E2E route coverage has zero missing paths but still 310 unmodeled nets after routed LED, control, reset, ready, sync and status families; analog behavior remains outside those digital checks. |
| Final gate | The last **completed** full `make verify` recorded 217 pass, 42 fail and 17 pending. A pre-integration run finished its other tests and counterexamples but was intentionally stopped during the duplicate sequential HDMI sweep; its partial output is not a new full result. The canonical board rebuild, long coupled SI, and final integrated full run are pending. Physical power, thermal, notch, Gerber-only completeness, CPL, and strict E2E gates prevent a green release. No manufacturing upload or order. |

## Done (recent)

- Seven card boards regenerated after the Gerber precision checks and passed
  ERC, board DRC and schematic parity; their current receipts validate. The
  main-board rebuild is still routing.
- BASIC follow-ups are integrated: packed ROM image, approved dead-code
  removals, run/hook handshake, isolated Nim cache and assembler comment
  parsing. Focused simulator/host checks, nine counterexamples, native
  E2E-002 and E2E-010 passed on the BASIC branch.
- CPU card now uses six layers. The seven card pipelines were reported complete
  at handoff; final integration reruns and live stock checks remain required.
- SD card model in the native emulator (EMU-008), STO-003, E2E-007 (BASIC
  SAVE/LOAD on the whole machine).
- Storage card software: FatFs core, RP2040 port, kernel/BASIC, 2668 host
  checks, KRN-006.
- Power for four cards and a 3 A source: TPS259470 eFuse, 3.5 A PTC,
  TLV62569PDDCR, PWR_HI = 3.0 A; below it no radio and no SD writes.
- Main board: source-driven salt-9 route, post-fill KiCad DRC/parity/connectivity
  all zero, with a current Gerber/BOM/CPL/render receipt. The hot-copper power
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
