# Milestone 1: status and decisions log

What is decided, what is running, and what is left, kept current so the work
survives a lost session. Newest first within each section. Specs live in
`doc/hardware/`; this file points at them.

## Decisions (David, 2026-09-24)

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
- **E-ink graphics card**: to explore, not build (`proposals/eink-gpu.md`).
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

## In flight

| Work | State |
|---|---|
| GPU, IO, storage card boards | IO passes every step; GPU one DRC item; storage drawn. IO gets a keyboard-port boost next (David) |
| System card board | passes every step; merging milestone-1 (kicadgen overlaps with the CPU card's) |
| Main board | routing; picking up the CPU card's pinout and the new power parts |
| E-ink card board | pipeline run |
| E-ink software (firmware, kernel INFO driver, UC8179 model, viewer) | done, all tests pass; merging milestone-1 (renumbers its E2E to E2E-008) |
| Power: keyboard-port boost (B16), default USB = typical loads (B6/B7), drop THM T5–T7 | power agent |
| Firmware bugs: storage slot frames at 20 µs gap, ST_EJECT before programming ends, IOC-004 key repeat | firmware agent |

## Done (recent)

- CPU card board passes every step (4 layers; FPGA pinout reordered to the
  socket's fingers; fmax 59.5 MHz, bus slack 65/64 %).
- SD card model in the native emulator (EMU-008), STO-003, E2E-007 (BASIC
  SAVE/LOAD on the whole machine).
- Storage card software: FatFs core, RP2040 port, kernel/BASIC, 2668 host
  checks, KRN-006.
- Power for four cards and a 3 A source: TPS259470 eFuse, 3.5 A PTC,
  TLV62569PDDCR, PWR_HI = 3.0 A; below it no radio and no SD writes.

- Wi-Fi card board through the whole pipeline (WIFI-004), TLV62569 buck
  after POW-003/THM-001, TX/RX/LINK LEDs, standard outline.
- `cupc8.py` resyncs on a PING nonce (a killed run's late reply no longer
  passes for the next run's; HOST-002).
- Keyboard path on the whole machine: IO card serves the slot during USB
  enumeration; boot ROM and kernel retry a not-ready READ.
- Power/thermal (4.4/4.5), footprint/pinout/rotation (4.3, BRD-001),
  mechanical fit (4.7, MECH-*), fab readiness report (`make verify`).

## Left before ordering

- All boards through the pipeline; E2E-001 (co-sim from the netlists);
  E2E-002/003/004 green on the native emulator; SI (4.6); the fab-readiness
  hand checks; David's sign-off; the final design critique.
