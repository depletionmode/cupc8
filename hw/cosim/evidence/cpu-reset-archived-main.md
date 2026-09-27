# CPU reset delivery: bounded E2E-001 execution evidence

The main-board input for this audit is the archived routed snapshot
`build/hw-baseline-c429827/main`, with `main.net` SHA-256
`0b47da7cadb5b7f77f3632663002634090ebcd861b9de67c5a7e73b36d74bca0`
and `main.kicad_pcb` SHA-256
`82594f84282241f279fcf3948493877acf2cb3112e5e5fb02ea2f246c7316834`.
Its receipt validates against this isolated branch's board input files.
The seven current `build/hw/{cpu,system,gpu,io,storage,wifi,eink}` receipts
validate against their producing source tree. Fresh exports made by this
branch compare exactly to all seven receipt netlists for components, nets,
pins, resistors, and pin names. Thus this hybrid uses the same electrical
graphs as those seven routed cards;
the archived main is still a separate board revision.

| Card | Routed PCB SHA-256 |
| --- | --- |
| CPU | `61604b4792f32657327703dc1450b0fd83dd67ea23793998123042e7327ac6b5` |
| System | `d1fbdb7eecb126fa7067caa27b842cb53188e01b2c1a953b12ed02b57372d2ee` |
| GPU | `7be7a81c7ed291ddb0fffb082c4b9a883bed1af6bc58c4d1987ecbca8c6fadf0` |
| IO | `2dbf557fbc5339235121e368d580c31db4807b3f8a8033d77971212a143f9e41` |
| Storage | `11382ab5be4b8c2994d6ac9c92c37c1c1d799384da6f439658ac0544c9e309ca` |
| Wi-Fi | `d19a8e1c03c61d3ff5e959136892ea829f8bfd846fd44fb31b214f80752243e6` |
| E-ink | `30cf2ebe6aa1f1f3097b2caa2c99a1e48ba91f4db199517b5e56cd7a475dfec0` |

The chipset drives `main:CPU_nRST_SRC` from U7.32 to R34.1 over 12.342 mm.
R34 is 33 Ω; its output reaches main CPU socket J2.B16 over 103.930 mm on
`main:CPU_nRST`. CPU-card J1.B16 reaches FPGA U1.22 over 27.014 mm on
`cpu:CPU_nRST`. Each pad and resistor is checked in the KiCad netlist and
each leg needs a pad-to-pad copper route. The native RTL CPU reset input now
consumes their combined continuity. With all three routes connected, the
20 ms native probe reaches PC `$E2B9`; with `cpu_reset_connected=false`,
the chipset reset output remains high and the CPU stays at PC `$E000`.
Removing the U7.32 launch segment from the PCB specifically disconnects the
source leg while the other two remain routed. That mutation also makes the
runtime flag false. The open input is held low for this digital
counterexample; actual open-pad voltage is not established. The same
mutation adds `CPU_nRST:main.U7.32->main.R34.1` to `missing_routes` and
sets `routed_top=false`, so `--require-route` rejects it.

Reproduction after `tools/emu_machine_build.sh` and with the card firmware
ELFs available in `build/rp2040`:

```sh
python3 hw/cosim/gen_top.py \
  --main-netlist build/hw-baseline-c429827/main/main.net \
  --card-board-dir build/hw \
  --system-board build/hw/system/system-routed.kicad_pcb \
  --cpu-board build/hw/cpu/cpu.kicad_pcb \
  --output build/hw/cosim/hybrid-top.json
python3 test/hw/test_cosim_wiring.py \
  --main-netlist build/hw-baseline-c429827/main/main.net \
  --main-board build/hw-baseline-c429827/main/main.kicad_pcb \
  --card-board-dir build/hw \
  --system-board build/hw/system/system-routed.kicad_pcb \
  --cpu-board build/hw/cpu/cpu.kicad_pcb
python3 test/hw/test_cosim_runtime.py --top build/hw/cosim/hybrid-top.json
```

Both focused suites exited zero on this hybrid. The generated manifest has
`routed_top=true`, 244 executed nets, 362 strict unmodeled nets, 218
structural-only nets and 45 reviewed reserved-contact waivers. Before this
reset model the same hybrid had 241 executed nets and 365 strict unmodeled
nets. The three added reset nets are executed, not merely structural.

E2E-001 through E2E-004 remain blocked by the 362 strict gaps. The active
main-board route must be completed and audited against its own receipt before
these archived-main results can be transferred. This audit establishes
digital reset delivery and an open-route counterexample; it does not establish
reset edge quality, analog signal integrity, power-up behavior, or full-board
E2E coverage.
