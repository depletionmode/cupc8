# AHC MISO charging bound — 2026-09-30

This is a conditional engineering bound, not an extension of TI's guaranteed
50 pF propagation-delay specification. The primary source is
[TI SN74AHC1G125 SCLS377M](https://www.ti.com/lit/ds/symlink/sn74ahc1g125.pdf),
February 2024, electrical and switching characteristics. TI specifies
VOH >= 2.48 V at -4 mA and VOL <= 0.44 V at +4 mA, VCC = 3 V through 125°C.
The maximum propagation delay is 14 ns at 50 pF through 125°C; it is not
specified for the actual distributed 77.53 pF load with a 270 ohm series
resistor and six 10 kohm shunts.

## Conditional worst charging calculation

Assume that, after its internal transition, the output obeys a monotone
current-voltage characteristic with the specified DC 4 mA point. Then its
minimum sourcing current through the series resistor is
`min(4 mA, (2.48 V - V)/R)`. Use R = 278.1 ohms (+3%), shunt conductance
G = 6/9700 ohms (-3%), and total C = 77.53 pF. Leakage and additional
capacitance must be added separately if not already included in that load.

For a lumped passive RC load, charge to a 2.0 V high threshold:

- Current-limited phase, 0 to 1.3676 V.
- Voltage-limited phase, 1.3676 to 2.0 V.
- Total charging time: 64.078 ns. Steady voltage: 2.11600 V.

The 3 MHz half cycle is 166.667 ns. The existing timing inventory uses
84.688 ns before AHC propagation and MISO settling. Charging plus a presumed
14 ns internal bound would total 162.766 ns, leaving approximately 3.90 ns before any omitted leakage.
This is more conservative than the presently modeled 28.54 ns MISO settling.
A +40 mV source-ground displacement improves the rising bound to 60.176 ns;
with VOL shifted to 0.48 V, discharge from 3.6 V to 0.8 V takes 48.270 ns.
If a -40 mV ground displacement is required, the rising bound becomes
69.653 ns and exceeds the available 67.979 ns after the presumed 14 ns delay.
A distributed transmission-line network requires the SI solver to confirm
that its receiver cannot cross later than the lumped comparison bound.

## Precise remaining qualification condition

The DC table does not guarantee when the lower current envelope begins after
an input transition. The 14 ns specification measures a 50% output crossing
with a specific 50 pF test load; it is not a guaranteed time to establish the
entire DC current envelope under an arbitrary larger load. Consequently,
adding 14 ns to the charging calculation is conditional. A defensible final
pass needs the unchanged actual-load IBIS waveform/current model checked
against the TI 50 pF timing specification, or measured first-article timing
covering the qualification temperature and supply range. Do not label the
64.078 ns estimate as a TI-guaranteed actual-load propagation bound.

## Wi-Fi rail reference

The prior 3.561534 V Wi-Fi buck crest is relative to U2 GND (model node 0).
The slot/main ground is a separate node below U2 GND through the extracted
66.549 milliohm card return. A direct coincident probe of
`v(buck,slot_gnd)` in the same worst-4.75 V, 508.3 mA, 100 milliohm-ESR
scenario gives **3.581281930 V**. This avoids adding separately occurring
voltage and return-current maxima. Reproduction:
`python3 /tmp/cupc8-resume-wifi-20260930/buffer-main-reference.py`.

The voltage is conditional on the existing capacitor/load/contact models.
The actual U3 supply and GND have local branches relative to U2; their
transient differential is not established by this regulator-node probe.
