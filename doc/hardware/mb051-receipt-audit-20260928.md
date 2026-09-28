# MB-051 routed reset audit — red (2026-09-28)

The current main-board receipt (`build/hw/main/evidence.json`, SHA-256
`2b29afec3aaee9794b7d805f2d82ad89d122e143ddde6119174030fc5e7c2605`)
validates against the board source, and its saved DRC has zero findings.
`python3 hw/power/rail_reset_window.py build/hw/main` binds the reset pins to
that netlist and routed PCB. It measures U6.2 → U7.61 `nPOR` at 94.505 mm
and U13 → slot 1–6 reset copper at 43.321, 48.222, 71.312, 86.890,
110.463 and 130.689 mm. Connected copper does not establish correct
reset release timing.

The fitted MAX811T U6 senses +3V3 only. Its 3.00–3.15 V threshold can
release `nPOR` at +3V3 = 3.100 V, below the required 3.135 V lower edge,
after its hold timer expires. With +3V3 = 3.300 V and +1V2 = 0 V, U6 has no
1V2 fault input. Each `SLOTn_RST_n` has a 10 kΩ pull-up and is driven only
by a TCA9555 pin that powers up as an input; the optional system card need
not be present to boot. Thus all six slot resets can release before +1V2
is qualified. The diagnostic prints both counterexamples and exits nonzero.

## Candidate and limits

The [TI TPS3702 datasheet](https://www.ti.com/lit/ds/symlink/tps3702.pdf),
Table 7-1, gives a 1.2 V window example with worst-case falling undervoltage
trip **1.142 V** and rising overvoltage trip **1.259 V**. These are only
**2 mV above** the FPGA's 1.140 V operating floor and **1 mV below** its
1.260 V ceiling, at the monitor's SENSE pin. The TPS3702CX12 uses a fixed
threshold and open-drain UV/OV outputs. A corresponding TPS3702CX33 is a
possible 3V3 monitor. The datasheet's electrical and timing tables also
specify supply/POR behavior, hysteresis and pulse response; those limits
must be applied to the actual circuit and fault waveform. These parts are
screening candidates, not qualified substitutions or an approved schematic.

The existing POW-002 1V2 low corner is 1.172 V under its assumed 40 mA
step and ripple. It is a regulator model, not a guaranteed voltage at every
FPGA power pin or a bound on the monitor-to-load voltage difference. A
2 mV/1 mV margin cannot absorb an unspecified copper/contact/GND offset,
sensor placement error, card-local rail lag, or an unverified FPGA load
waveform. The earlier TPS3890 threshold screen in
`mb051-rails-good-proposal.md` also has no guaranteed 1V2 window under the
modeled low corner.

LCSC lists TPS3702CX12DDCR as C2067462, but that is distributor
availability only. The live `hw/tools/jlcparts.py check C2067462 C2068031
--min-stock 6` request failed with DNS resolution in this session. JLC
assembly availability at twice the proposed build quantity is unverified.

## Acceptance data before a board change

1. Bound +1V2 and +3V3 at the **monitor SENSE pins and every affected FPGA
   supply pin** through ramp, steady load, load steps and brown-out over
   temperature and manufacturing corners. Include finished copper, vias,
   connector contacts, shared return and the actual FPGA current waveform.
   Show margin to both rail operating limits after threshold accuracy and
   hysteresis, especially the 2 mV/1 mV 1V2 limits above.
2. Qualify the exact orderable supervisor variants, pin maps, thresholds,
   startup and output states, fault propagation and pulse behavior from
   guaranteed datasheet limits. Show that U6's manual-reset input, CPU
   reset gate and six slot clamps stay asserted through standby ramp,
   power-off, absent system card, either rail starting first, slow ramp,
   either rail browning out, and button/sysctl reset. Avoid contention with
   the chipset's push-pull CPU-reset output.
3. Obtain current JLC assembly-library identities and stock at least twice
   the order quantity for every added part. Then revise schematic and PCB,
   rerun ERC, placement, routing, zero-open DRC, receipt and timing/fault
   simulations on the new fitted circuit.

No board source or power requirement was changed in this audit. MB-051
remains red.
