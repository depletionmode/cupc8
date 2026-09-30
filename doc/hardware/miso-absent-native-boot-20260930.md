# Passive MISO low-bias boot qualification

The proposed permanent main 4.7k MISO shunt changes an undriven empty-slot
read from FF to00. The existing ROM treats00 response length as not ready,
retries finitely, then records the slot as absent. No ROM/firmware change was
needed.

Actual native execution passed using the unchanged `rom/boot.s`, real
CPU/chipset RTL, and the routed round3 baseline. A copied top declares exactly
one candidate change, `runtime.miso_idle=0`; this is a functional fixture,
not an actual generated shunt-board receipt or analog SI proof.

| Actual case | Observed result |
| --- | --- |
| All six absent, high passive bias | All six table entries0; selected-empty raw byteFF. Probe interval37.017ms; assertion kernel completes335.075ms. |
| All six absent, low passive bias | All six table entries0; selected-empty raw byte00. Probe interval731.195ms; assertion kernel completes1,029.255ms. |
| IO installed in slot4, low passive bias | IO table entry2, all five absent entries0; selected-empty raw byte00. Probe interval615.168ms; completes913.228ms. |
| Real GPU slot2 + IO slot4, low passive bias | Genuine boot ROM/kernel/BASIC reaches prompt at2,430.072ms and executes `6*7` as42. |

These are **emulated times**, not physical elapsed measurements. Timing
samples request1ms steps; maximum observed sample interval1.010ms. Low bias
adds694.177ms to all-empty probing in this native run. The nominal20×5ms
shorthand was not an upper bound: the conservative ROM busy loop gave a
6.063ms observed IDENT-to-READ delay on the fitted IO card. Each empty slot
still exhausts a finite20 READ attempts and continues; no phantom card/C8
signature is accepted and no hang was observed.

The small assertion kernels are freshly assembled controlled test payloads
loaded by the authentic boot ROM. They check every slot-table byte and a
real selected-empty SPI transfer. The final case separately uses the genuine
maintained ROM builder, full kernel/BASIC and GPU/IO firmware; active response
bits survive the passive low level.

## Reproduce

```sh
python3 test/hw/test_miso_absent_boot.py \
  --top build/development-offline-20260930/round3/top.json \
  --board-root build/development-offline-20260930/round3 \
  --output-dir build/main-miso-absent-boot-20260930
```

The test validates all eight actual receipts before/after execution, retains
source/native-binary/top/ROM/result hashes in `qualification.json`, and
creates no TCP services. System USB/network/full E2E remain independent gates;
this test is not a substitute for them. Physical shunt fit/copper/DRC, voltage
stress, active output-current loading, timing and final generated source
binding remain required before adopting the candidate.
