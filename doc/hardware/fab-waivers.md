# Fab waivers and hand checks

Written by people, not generated: `tools/fabready.py` copies this file into
`fab-readiness.md`. Every waiver says what the rule is, what we do instead,
why, and who decided.

## Waivers

| Rule | What we do | Why | Decided |
|---|---|---|---|
| PCIe CEM card-edge bevel 20° ± 5° (Fig. 6-3) | 30° bevel on every card | JLC offers only 30° or 45°; 30° is the nearest, and what JLC recommends for easy insertion. MECH-002 accepts exactly 30° as this waiver. | David, 2026-09-24 |
| "Every part is assembled by JLC" (milestone-1.md) | The Wi-Fi antenna lead (C709347) and SMA antenna (C1509156) are ordered from JLC loose and plugged in by hand | JLC does not assemble cable parts. Plugging an RF lead in is not soldering. | David (milestone-1.md, antenna row) |
| verification.md 3.3: a missing CPU card | Out of scope | A machine without its CPU card is broken hardware. | David, 2026-09-24 |
| verification.md 3.3: a card pulled while running | Out of scope | Cards are plugged or removed only with the power off (`slot.md`). | David, 2026-09-24 |
| `hw/power` current budgets: 10 % margin (POW-006) | POW-006 B5, the machine on a 1.5 A source (radio off, SD writes refused, SD reading, a 500 mA keyboard), needs 5 %. It is 1.383 A, 7.8 % under 1.5 A. | Every tolerance is at its worst at once (vSafe5V min, the Type-C cable's full drop, every resistance at its max, every load at its max), and the case still fits the source class. The full machine is specified on a 3.0 A source. | David, 2026-09-25 |

## Hand checks (to do before ordering, with a date)

| Check | Done |
|---|---|
| 4.9: every board's CPL rendered over its Gerbers, each part's pin 1 and rotation checked by eye (BRD-001 checks rotations against JLC's footprints; this is the backstop) | |
| JLC's order page: each board's options match its `fab/order.json` (layers, 1.6 mm, ENIG, hard-gold fingers and 30° bevel on cards) | |
| The antenna lead is SMA female (jack) and the antenna SMA male, not RP-SMA | |
| Parts with low stock reserved in the JLC parts inventory (the ROM chips, the FPGAs: `parts.md`, Risks) | |
