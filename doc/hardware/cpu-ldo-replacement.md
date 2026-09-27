# CPU 1V2 LDO replacement assessment (2026-09-27)

**Decision: retain RT9013-12GB in the board design for now; do not substitute
TLV75512PDBVR or clear CC-005.** [Richtek lists RT9013 as
EOL](https://richtek.com/Products/Linear%20Regulator/Single%20Output%20Linear%20Regulator/RT9013?sc_lang=en&specid=RT9013),
so the fitted part needs a replacement before a production build. Existing
distributor stock does not resolve its life-cycle risk.

[TI's active TLV75512PDBVR](https://www.ti.com/product/TLV755P/part-details/TLV75512PDBVR)
is a promising 1.2 V, 500 mA SOT-23-5 candidate. Its
[datasheet, Figure 4-2 and Table 4-1](https://www.ti.com/lit/ds/symlink/tlv755p.pdf)
put IN/GND/EN/NC/OUT on pins 1/2/3/4/5, matching CPU U3's present pin map.
[JLC lists it for assembly as C2877864](https://jlcpcb.com/partdetail/TLV75512PDBVR/C2877864);
its search index showed 3,619 in stock when checked on 2026-09-27, but the
indexed count was about two weeks old. Confirm orderable stock in the actual
JLC BOM before any substitution.

The TI datasheet rates 500 mA output and specifies a 560 mA minimum current
limit under its stated test conditions. It gives ±1.5% output accuracy across
the full junction-temperature range **at 1 mA**, requires at least 0.47 µF
*effective* output capacitance for stability, and calls for nominal 1 µF or
more at both input and output. It does not impose RT9013's 5 mΩ output ESR
floor. The 0.060 V/A DBV load-regulation entry is **typical**, and the load
transient plot is a **typical 3.3 V** test, not a guaranteed 1.2 V droop bound.
These distinctions are visible in datasheet sections 5.5, 5.6 and 7.1.1.

The present CC-005 route model has a 196.8 mΩ nominal centerline path, or
7.9 mV at its assumed 40 mA FPGA core load. Even applying TI's 1 mA accuracy
floor at that load would leave only about 34 mV above the FPGA's 1.14 V
minimum (`1.2 × 0.985 − 0.0079 − 1.14`). That is a **conditional margin**, not
a guarantee at 40 mA: neither the regulator's load-step droop nor the FPGA
current waveform is bounded. The fitted C22's capacitance after DC bias and
temperature, the input capacitor's effective value, the 3V3 socket feed,
minimum finished copper and pad/contact resistance also need bounds. A
replacement requires those inputs and a rerun of the routed power, start-up
and thermal checks with the new part before CC-005 can pass.
