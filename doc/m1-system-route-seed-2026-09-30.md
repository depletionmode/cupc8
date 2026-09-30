# System route preservation

The fresh System pipeline exhausted eighteen routing attempts on `/PROG_IO`.
Its previous complete routed board remains bound to the original pipeline's
artifact hashes; its final DRC has zero violations and zero unconnected items.

`hw/boards/system-route-seed.json` records its 1,177 tracks/vias and 59
footprint records. The header records the source board, receipt and final DRC
hashes. This is a design input for regeneration, not a replacement receipt.

The System generator requires exact component positions, rotations and pin/net
maps before replacing pre-route copper with this recorded route. All signal
connections must then close. An incompatible seed aborts instead of rerouting
the accepted USB signals. R18's calculated position is rounded to its intended
44.6 mm coordinate, avoiding a one-nanometre floating-point truncation.

The current source-generation probe passes schematic, ERC and netlist checks,
and restores the seed with every signal connected. A changed U1 placement,
changed programming-pin net and removed programming route are each rejected
by separate adverse probes. The standalone restored pre-fill DRC has no
clearance or short violations; ground opens/dangling items before pours and
stitching are expected and are not a complete board pass.

Logs: `/tmp/cupc8-system-escape/source-probe.log`, `test-seed.log`,
`restored-drc.json`. The full current pipeline, including all DRC, fabrication,
BOM/CPL and stock checks, remains required before canonical adoption.
