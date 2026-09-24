# Proposal: an e-ink graphics card (exploration)

**Status: to explore, not scheduled. Raised 2026-09-24 by David.** Nothing is
built. This stub records the request; the full proposal (display options,
design, protocol, tests) is being written and replaces it.

## The request

A second option for the graphics card: a card that drives an **e-ink
(e-paper) display instead of HDMI**, with the **minimum component count**
that makes it work, on the **same slot bus** as the rest of the system
(`../hardware/slot.md`: the common card protocol, the standard I/O card
outline, the slot's power budget). Record the option and plan it out; do not
implement it.

Also: **find e-ink displays** that could connect to this card, with their
resolution, controller, interface, refresh times, price and where to buy
them, and recommend one.

## What the full proposal covers

- Display options: SPI e-paper panels and modules (roughly 2.9" to 7.5"+),
  and which suit a text console (e.g. 800×480 → 100×30 characters of 8×16).
- The minimal card: a bare panel on a 24-pin FPC with the standard booster
  circuit, or a ready-made module on a header; RP2040 as on the other cards;
  every part from JLC's library with stock (the panel bought separately).
- Protocol and kernel: the text console on e-ink (framebuffer on the card,
  partial refresh, full refresh against ghosting), keeping the HDMI card's
  opcodes where they fit so the kernel barely changes.
- Testing: host tests of the core, the real firmware on the native emulator
  with an e-paper controller model rendering into golden images.
