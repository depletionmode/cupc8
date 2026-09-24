# Milestone 1: status and decisions log

What is decided, what is running, and what is left, kept current so the work
survives a lost session. Newest first within each section. Specs live in
`doc/hardware/`; this file points at them.

## Decisions (David, 2026-09-24)

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

| Work | Where | State |
|---|---|---|
| GPU and IO card boards, then the storage card board | agent worktree (GPU/IO agent) | GPU/IO route; storage card to follow |
| System card board | agent worktree | routing |
| CPU card board | agent worktree | routing, plane fan-out |
| Main board | agent worktree | routing (the largest board) |
| Storage firmware (`fw/storage`), kernel `storage.s`, BASIC SAVE/LOAD/DIR/DEL, tests | agent worktree | started (retargeted from the IO card) |
| SD card model in the native emulator, card and end-to-end tests | agent worktree | started (attaches to the storage card) |
| E-ink graphics card proposal | agent worktree | research |

## Done (recent)

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
