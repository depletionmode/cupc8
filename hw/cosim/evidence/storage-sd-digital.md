# Storage microSD digital co-simulation subset

Run `python3 test/hw/test_cosim_storage_sd.py` against the canonical board
receipts. The script validates all eight receipts and the pinned co-simulation
top, checks the storage KiCad netlist against RP2040 and TF-01A pins, and
measures seven MCU-to-socket copper paths plus seven ESD and six pull-up
branches. On the current routed board all 20 branches are connected.

The script removes each branch's launch copper on a private PCB copy. All
20 removals are detected. Removing each of the seven socket launches makes
the derived native top disable the SD socket while keeping the storage card
present. An MCU SD clock pin swap is rejected at the source netlist check.

This check closes **digital microSD socket continuity only**. Its native probe
checks whether the socket model attaches; storage read/write behavior is
covered separately by EMU-008 and E2E-007/011. The check does not establish
signal integrity, SD rail/ground return, ESD effectiveness, oscillator or
boot/programming behavior. The current strict top still has 18 unmodeled
storage nets (288 across the whole machine), so SC-051 and verification row
3.1 remain pending. A catalogue row for this focused subset could use:

`cmd = "python3 test/hw/test_cosim_storage_sd.py"`
