# Signal-integrity models in progress

`hw/si/openems_gpu_d0.py` reads the GPU card's routed KiCad board and models each of the four HDMI TMDS pairs independently, from a source resistor pack to J1, in openEMS (`--pair d0|d1|d2|ck`). The input must be a completed GPU pipeline build when run by `SI-003`; its board receipt and file hashes are checked before simulation. Each JSON result records the board SHA-256 and the field-energy decay.

The selected [JLC04161H-7628 stackup](https://jlcpcb.com/impedance) puts 0.2104 mm of 7628 prepreg (Dk 4.4) between top copper and the L2 ground plane. The model uses those values, a rectangular L2 ground plane, lossless dielectric, and ideal copper. It excites and terminates the pair with two 100 Ω lumped differential ports on the z=0 copper plane, then derives S11 and S21. [openEMS warns](https://docs.openems.de/en/latest/concepts/ports.html) that lumped ports can perform poorly on differential pairs; these results remain diagnostic pending mesh and port sensitivity checks. The script rejects results where |S11|² + |S21|² exceeds 1.001 or the nominally matched passive port has an incident wave exceeding 1% of the driven port's incident wave at any sampled frequency. These small numerical margins are basic consistency checks, not complete port calibration. It also fails if either route disconnects, changes layers, or adds a via (those changes need new geometry, not a silent approximation).

This is a subset, not `GC-007`. The pairs are solved separately, so inter-pair coupling is absent. Exact pad and HDMI connector metal, solder mask, finite copper and dielectric loss, and source/sink behavior are also absent. The reported S21 therefore cannot certify the real insertion-loss budget, and S11 includes the model's launch discontinuities. The script's `--straight-control` option keeps the same ports and endpoints while replacing bends and width changes with straight 0.2 mm tracks; a mesh/port sensitivity run is still needed before using the model to judge impedance. `GC-007` and the row 4.6 system gate remain pending.

To repeat the subset after building the GPU board:

```sh
for pair in d0 d1 d2 ck; do
  python3 hw/si/openems_gpu_d0.py --pair "$pair" --board build/hw/gpu/gpu.kicad_pcb --out "build/hw/si/gpu-$pair.json" --require-evidence
done
```

On a fresh, provenance-checked GPU board (SHA-256 `95fa5811164a2fb367d8bf085ae1cfb91ced5320b8bb77a9227961c85535c9fa`), the original lumped-port boxes extending from z=-0.05 to +0.05 mm reached -40.06 dB in 87,200 steps on openEMS v0.37.0-rc3-1-g65f8771. At 1.26 GHz they gave S11 -10.66 dB and S21 -0.26 dB, but their squared magnitudes summed to 1.027414, violating passive two-port power balance by 2.74%. The unexcited port had |uf_inc,2/uf_inc,1| about 0.18 and measured -U2/I2 about 145.4 Ω across 0.1–1.26 GHz, despite a declared 100 Ω load. Those data fail the new validity gates.

Changing only the lumped-port boxes to two-dimensional surfaces at z=0 kept the same board, traces, substrate, 0.05 mm x/y mesh, and 100 Ω port resistors. That comparison run reached -40.14 dB in 96,792 steps. Its passive port measured 99.94 - j0.15 Ω at 1.26 GHz, with |uf_inc,2/uf_inc,1| = 0.000775. At that frequency S11 was -12.45 dB and S21 was -0.54 dB, with squared magnitudes summing to 0.939621. The comparison isolates the port thickness as the cause of the 145 Ω mismatch on this mesh.

The routed GPU board used for the four exploratory runs is SHA-256 `86185894b9863e53bdbc19ff3b0940147180a36fb3725be38f39f54d2479b66f`. Each reached at least -40 dB field-energy decay, and all four sampled frequencies passed the port consistency and passive power checks. At 1.26 GHz:

| Pair | Steps | S11 | S21 | Power sum |
| --- | ---: | ---: | ---: | ---: |
| D0 | 102,678 | -12.44 dB | -0.54 dB | 0.939592 |
| D1 | 107,692 | -12.06 dB | -0.57 dB | 0.939937 |
| D2 | 104,640 | -12.34 dB | -0.54 dB | 0.941130 |
| CK | 102,678 | -12.56 dB | -0.52 dB | 0.943002 |

Saved-field postprocessing reproduces the generated geometry for all four pairs after the refactor. A fresh GPU pipeline receipt is required before `SI-003` can accept these runs against current sources. This does not establish the full row 4.6 impedance or loss target: USB routes, connector and pad geometry, physical losses, pair coupling, and a mesh sensitivity study remain open.

## IO card USB field model

`hw/si/openems_usb_io.py` reads the completed IO card's actual F.Cu routes
from the outputs of 27 Ω resistors R14/R15 to USB-A J2 pins 2/3. It verifies
the four pad nets, direct copper connectivity, 0.2 mm track width, and absence
of vias or layer changes. An open D+ segment is rejected by
`test/hw/test_usb_io_field.py`. On the current routed-card snapshot, D+ is
12.821 mm and D− is 27.045 mm. The model includes their ESD stubs and a
rectangular In1.Cu ground plane with the [JLC04161H-7628 stackup](https://jlcpcb.com/impedance).
It omits exact pad and connector metal, ESD-device capacitance, copper and
dielectric loss, solder mask, and the ground plane's local antipads.

Two 2D differential lumped ports are normalized to 90 Ω. A declared 90 Ω
port measured about 81 Ω at the passive end on the 0.075 mm mesh, so its
S-parameters were invalid. A 100 Ω declared resistor measures about 90.0 Ω
and leaves less than 0.05% passive-port incident voltage at 100–480 MHz. The
longer run reached only −34.4 dB energy decay after 120,000 timesteps, short
of the required −40 dB. Its S11/S21 values are therefore **not accepted** as
signal-integrity evidence even though passive power and port checks pass.
The script exits nonzero and writes `converged: false` and
`valid_for_row_4_6: false`. A converged rerun, mesh/straight-route sensitivity,
source and receiver USB PHY behavior, the system card's USB-C path and final
main-board route remain required for `MB-007` and row 4.6.

```sh
python3 test/hw/test_usb_io_field.py --board build/hw/io/io.kicad_pcb
python3 hw/si/openems_usb_io.py --board build/hw/io/io.kicad_pcb \
  --out build/hw/si/usb-io.json --require-evidence
```

## IBIS specification and pinned FPGA model

[IBIS](https://ibis.org/about/) means *I/O Buffer Information Specification*. It describes a chip pin's analog input/output behavior with current-versus-voltage tables, switching waveforms, clamps, and package parasitics. It does not describe the FPGA's logic or the PCB trace. The applicable format reference for our file is the [official IBIS 4.0 specification](https://www.ibis.org/ver4.0/ver4_0.pdf): the vendor file says `[IBIS ver] 4.0`. The [IBIS Open Forum's specification index](https://www.ibis.org/specs/) lists later revisions, including 8.0, but those do not change which format this pinned file declares.

For the bus waveform work, `SI-004` retrieves [Lattice's iCE40 IBIS model FPGA-MD-02034](https://www.latticesemi.com/view_document?document_id=48057) into ignored `build/hw/si/FPGA-MD-02034-2-5-iCE40-IO.ibs`. Its `[File Rev]` is 2.5 and its `[Date]` field is `4/8/2022`; this is the *vendor model revision*, separate from IBIS format version 4.0. The required SHA-256 is `8acc5bf6bc90d6956b80d5e688b7bc47a48386b127533702c8d5f328a57390c9`. To fetch and check the exact file, run `python3 hw/si/fetch_ice40_ibis.py && python3 test/hw/test_ibis_model.py`. The file permits PCB design use but prohibits duplication, so it is downloaded during verification rather than committed.

The file lists `iCE40HK4K` (apparently a typo for HX4K), 3.3 V output curves, and rising/falling waveforms. Its active `[Package]` values are for CM36A, while two *commented* TQ144 entries give typical R/L/C of 0.764 Ω/7.98 nH/1.216 pF and 0.673 Ω/10.53 nH/1.207 pF. The latter follows a `CB132_4K_8K` entry, but the file does not explicitly assign either TQ144 row to HX4K. A TQ144 bus simulation must resolve that choice instead of silently using the active CM36A values. [ngspice lists IBIS support on its roadmap](https://ngspice.sourceforge.io/roadmap.html); an IBIS-to-SPICE behavioral conversion and fixture validation are therefore needed before a bus transient can be claimed. Receiving-device models and routed interconnect remain open. Sourcing the model alone does not simulate the six-slot SPI or CPU/SRAM/ROM buses.

`hw/si/ibis_bus.py` now supplies a **diagnostic** ngspice transient for the
CPU socket and six-slot SCK line. It reads the SHA-pinned Lattice file's
`lvc330io` and `lvc330_b3io` rising/falling waveforms and I/V tables at all
three corners. The IBIS 50 Ω / 25 pF waveform fixture is de-embedded to a
linear Thevenin source, then replayed in ngspice. Its largest sample error is
0.079 V; the I/V endpoint current agrees within 20%. The generated JSON
records the source hash, optional netlist-top hash, 96 transient cases and
every receiver's first VIH/VIL crossing and any subsequent re-crossing.

This is a linearized IBIS **subset**, not a complete buffer model. The bus
uses assumed 120 mm (CPU) and 180 mm (six-slot) 50 Ω lines at 7 ps/mm, with
5/15 pF or 15/30 pF receiver loads. Both commented TQ144 inductances are
bracketed. The script checks that an optional generated KiCad top contains
the six shared SCK paths and 31 CPU series-terminated outputs, but it does
not yet extract branch geometry from routed copper. The provisional run has
24 cases with a VIH/VIL re-crossing after the first edge, all on the
six-slot line; the smallest excursions are on the order of the fixture-fit
error. These are risk indicators, not proof of a physical failure. The
missing receiver IBIS, package assignment, nonlinear clamp behavior and
finished main-board route keep `MB-007`, `CC-007` and row 4.6 pending.

```sh
python3 hw/si/fetch_ice40_ibis.py
python3 hw/si/ibis_bus.py --top build/hw/cosim/top.json --out build/hw/si/ibis-bus-diagnostic.json
python3 test/hw/test_ibis_bus.py --top build/hw/cosim/top.json
```
