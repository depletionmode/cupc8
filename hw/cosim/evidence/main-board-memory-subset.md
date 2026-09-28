# Main-board memory and CPU boot digital subset (2026-09-28)

`test/hw/test_cosim_main_board_subset.py` validates the current main, CPU,
and system board receipts, generates a fresh netlist-derived native top, and
measures chipset U7 copper paths to SRAM U9 and ROM U10. It checks 19 address
signals to both chips, eight data signals to both chips, both `/OE` and `/WE`
branches, and the separate RAM/ROM chip selects: **60 package-to-package
paths**. All 60 paths are connected on the current main board. The model
requires the named package pads in the KiCad netlist, so changing ROM DQ0's
net fails source binding. Opening the ROM DQ0 launch track in a private PCB
copy is detected as a missing U7.119-to-U10.13 copper path.

The generated top reports `routed_top: true`, `routed_timing: true`, both
memory `/WE` links, ROM DQ0 read, supervisor reset, CPU clock/reset,
all CPU address/data links, and the three sysctl bridge sources connected.
With a freshly assembled ROM image, the native chipset and CPU-card model
reach PC `$E2B9`, GPO `$02`, `/RST` high after 20 ms. The open ROM DQ0
counterexample instead reaches `$E35B`, GPO `$00`. The native model uses a
deterministic high level for the floating bit; this does not predict its
physical voltage.

The same focused run of the GHDL chipset testbench passed BRG-001 and BRG-002
with zero errors. Those tests exercise the bridge with behavioural SRAM and
SST39 models; they are independent of the main-board copper audit. The
system-card `ping` and `status` commands are included in the full subset
probe, but this sandbox denies the model's TCP loopback listener (`listen
127.0.0.1: EPERM`), so they have not passed here. Run without `--cpu-only`
where loopback is allowed to complete that part.

Current receipt SHA-256 values:

| Artifact | SHA-256 |
| --- | --- |
| main receipt | `2b29afec3aaee9794b7d805f2d82ad89d122e143ddde6119174030fc5e7c2605` |
| main netlist | `30f294dd364913c357e1546647e410e5a448401633c299fc9f0181be5a3b58d8` |
| main PCB | `ec18ea676bcc5dde18b7ee66412d29b94024f0acdf40ac458b825c331398e2f7` |
| CPU receipt | `b61feaf1b9c5538f430a9671d09feccf1bc57b6ac71c2934c38560ae4a586acb` |
| system receipt | `f15e354539b360125490711e30b9e785ee14e3ccdcdb161b05dcbbf1d5796da4` |

Reproduce the available subset with
`python3 test/hw/test_cosim_main_board_subset.py --cpu-only`.
Run the complete digital probe with
`python3 test/hw/test_cosim_main_board_subset.py`.
The strict generated top still has **284 unmodeled nets**. This subset does
not establish complete MB-052 or E2E-001, nor analog bus signal integrity,
rail/reset margin, or thermal behavior.
