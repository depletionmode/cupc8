# Signal-integrity models in progress

`hw/si/openems_gpu_d0.py` reads the GPU card's routed KiCad board. It models the six top-layer track segments on each side of the HDMI D0 pair, from the output side of RN2 to J1, in openEMS. The input must be a completed GPU pipeline build when run by `SI-003`; its board receipt and file hashes are checked before simulation. The JSON result records the board SHA-256 and the field-energy decay.

The selected [JLC04161H-7628 stackup](https://jlcpcb.com/impedance) puts 0.2104 mm of 7628 prepreg (Dk 4.4) between top copper and the L2 ground plane. The model uses those values, a rectangular L2 ground plane, lossless dielectric, and ideal copper. It excites and terminates the pair with two 100 Ω lumped differential ports, then derives S11 and S21. [openEMS warns](https://docs.openems.de/en/latest/concepts/ports.html) that lumped ports can perform poorly on differential pairs; these results are diagnostic until a calibrated port model is in place. It fails if either route disconnects, changes layers, or adds a via (those changes need new geometry, not a silent approximation).

This is a subset, not `GC-007`. The other seven TMDS pairs, their vias, exact pad and HDMI connector metal, solder mask, finite copper and dielectric loss, and the source/sink behavior are still absent. The reported S21 therefore cannot certify the real insertion-loss budget, and S11 includes the model's launch discontinuities. The script's `--straight-control` option keeps the same ports and endpoints while replacing bends and width changes with straight 0.2 mm tracks; a mesh/port sensitivity run is still needed before using this model to judge the pair's impedance. `GC-007` and the row 4.6 system gate remain pending.

To repeat the subset after building the GPU board:

```sh
python3 hw/si/openems_gpu_d0.py --board build/hw/gpu/gpu.kicad_pcb --out build/hw/si/gpu-d0.json --require-evidence
```

The prototype used a routed GPU snapshot from the main-board worktree (SHA-256 `021f70e4940aba932c09a430a0c38e2d13f5977d85b31c86dd4ca646bcbec2cf`; its `gpu.py` matched this branch). That snapshot has no `evidence.json`, so it cannot pass `SI-003`'s provenance check. On openEMS v0.37.0-rc3, the routed pair reached -40.05 dB energy decay in 85,020 steps. At 1.26 GHz it gave S11 -10.66 dB and S21 -0.26 dB. The straight control reached -40.11 dB in 71,940 steps and gave S11 -12.23 dB and S21 -0.41 dB. The routed model's squared S11 plus squared S21 is 1.027 at that frequency (a passive two-port should be at most one), which is another reason to treat these values as diagnostics until the port model and mesh are checked. Neither run establishes the row 4.6 impedance or loss target.
