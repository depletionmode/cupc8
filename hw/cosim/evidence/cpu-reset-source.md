# CPU reset source copper: bounded E2E execution evidence

This audit uses the archived routed main board at
`build/hw-baseline-c429827/main` and the seven current card builds under
`build/hw`. All 38 archived main artifact hashes match its receipt, including
`main.net` SHA-256
`0b47da7cadb5b7f77f3632663002634090ebcd861b9de67c5a7e73b36d74bca0`
and `main.kicad_pcb` SHA-256
`82594f84282241f279fcf3948493877acf2cb3112e5e5fb02ea2f246c7316834`.
The archived main receipt's source inputs differ from current source in nine
files, including `hw/boards/main.py`; this is pinned snapshot evidence, not
a receipt for the active main route. Each of the seven current card receipts
validates against its producing source tree. Fresh exports from this branch
match all seven current card netlists exactly for components, nets, pins,
resistors, and pin names.

| Current card | Routed PCB SHA-256 |
| --- | --- |
| CPU | `61604b4792f32657327703dc1450b0fd83dd67ea23793998123042e7327ac6b5` |
| System | `d1fbdb7eecb126fa7067caa27b842cb53188e01b2c1a953b12ed02b57372d2ee` |
| GPU | `7be7a81c7ed291ddb0fffb082c4b9a883bed1af6bc58c4d1987ecbca8c6fadf0` |
| IO | `2dbf557fbc5339235121e368d580c31db4807b3f8a8033d77971212a143f9e41` |
| Storage | `11382ab5be4b8c2994d6ac9c92c37c1c1d799384da6f439658ac0544c9e309ca` |
| Wi-Fi | `d19a8e1c03c61d3ff5e959136892ea829f8bfd846fd44fb31b214f80752243e6` |
| E-ink | `30cf2ebe6aa1f1f3097b2caa2c99a1e48ba91f4db199517b5e56cd7a475dfec0` |

The chipset CPU reset output crosses three verified routed legs:

| Electrical net | Pads | Planar copper |
| --- | --- | ---: |
| `main:CPU_nRST_SRC` | U7.32 → R34.1 | 12.342 mm |
| `main:CPU_nRST` | R34.2 → J2.B16 | 103.930 mm |
| `cpu:CPU_nRST` | J1.B16 → U1.22 | 27.014 mm |

The netlist check also requires R34 to be the 33 Ω series resistor between
the chipset and CPU socket. The existing native `cpu_rst_connected` input
consumes the conjunction of all three copper legs. Removing the single
U7.32 launch segment leaves the other two legs routed, marks
`main:CPU_nRST_SRC_reset_copper` missing, clears `routed_top`, and holds the
native CPU at its reset vector `$E000` with `/RST` low instead of booting to
`$E2B9` in the 20 ms probe. Forced-low voltage at an open pad is a digital
counterexample; this does not establish the analog open-pin voltage or reset
edge quality.

The hybrid manifest has 248 executed nets, 358 strict unmodeled nets, 214
structural-only nets and 45 pin-bound reserved-contact waivers. Adding this
executed source net reduces the strict gap count from 359 to 358; the two
downstream reset nets were already modeled. The full E2E-001 through
E2E-004 gates remain open, and the active main route needs its own receipt
and copper audit before the result can be applied to that board.
Both the native runtime suite and the routed wiring mutation suite exited
zero on this hybrid. The wiring suite reported 1,242 connector contacts and
484 checked paths; its source-open probe observed PC `$E2B9` → `$E000`.

Reproduce after `tools/emu_machine_build.sh`, with card ELFs in
`build/rp2040`:

```sh
python3 hw/cosim/gen_top.py \
  --main-netlist build/hw-baseline-c429827/main/main.net \
  --card-board-dir build/hw \
  --system-board build/hw/system/system-routed.kicad_pcb \
  --cpu-board build/hw/cpu/cpu.kicad_pcb \
  --output build/hw/cosim/hybrid-top.json
python3 test/hw/test_cosim_runtime.py --top build/hw/cosim/hybrid-top.json
python3 test/hw/test_cosim_wiring.py \
  --main-netlist build/hw-baseline-c429827/main/main.net \
  --main-board build/hw-baseline-c429827/main/main.kicad_pcb \
  --card-board-dir build/hw \
  --system-board build/hw/system/system-routed.kicad_pcb \
  --cpu-board build/hw/cpu/cpu.kicad_pcb
```
