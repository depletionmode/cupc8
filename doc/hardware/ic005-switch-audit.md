# IC-005: IO card VBUS switch proof gap

> **Superseded (2026-09-29).** This audit is of the SY6280AAC circuit that
> the IO card no longer uses: David approved the TPS2553DBVR-1 (latch-off,
> RILIM 45.3 kΩ, FAULT to GPIO8, firmware retry) in
> [io-port-switch-proposal.md](io-port-switch-proposal.md). Kept as the
> record of why the SY6280 was replaced; the hashes and net tables below
> describe the old board.

**Status: red.** The catalogue asks for a SY6280 current limit set to
≤500 mA, soft start, and a fault flag on short. The fitted circuit cannot
establish those three claims from the published part data.

## Board and firmware binding

The current IO receipt at `build/hw/io/evidence.json` (SHA-256
`9510660b8c6e4b755e7fc9d6c4bf0a06a39ebc8260510f37e273204fcee3b452`)
binds `hw/boards/io.py` SHA-256
`cb136251bcea4263666eb1a3a9faa377801a49188e9fcd79bf0af01db934f41a`
to `io-routed.kicad_pcb` SHA-256
`880dba53ab75aaf171c340c879baeac3b3faf4b4685cc48e3f8280dd432b0d50`.
Its KiCad DRC has zero violations and zero unconnected items. The routed
board has these actual pad/net connections:

| Path | Routed pads and source behavior |
|---|---|
| Supply | `/VBOOST` → U5 pin 5 IN; U5 pin 1 OUT → `/VBUS` → J2 pin 1, C21 100 µF and C22 100 nF. |
| Limit setting | U5 pin 3 ISET → R10 12 kΩ → GND. |
| Enable | RP2040 U1 pin 9 GPIO7 → `/VBUS_EN` → U5 pin 4 EN; R11 pulls EN low during reset. |
| Sense | `/VBUS` → R12 15 kΩ → `/VBUS_nFAULT` → R13 22 kΩ → GND and RP2040 U1 pin 11 GPIO8. |

The routed `/VBOOST`, `/VBUS`, `/ISET`, `/VBUS_EN` and `/VBUS_nFAULT`
nets have 20, 21, 3, 24 and 15 track items, respectively, and no vias.
`fw/rp2040/io/main.c` reads GPIO8 as `!gpio_get(PIN_VBUS_NFAULT)` and
passes the resulting boolean to `io_vbus_fault()`, which sets status bit 4.
The digital status is therefore a **VBUS-low indication**. An overload may
cause low VBUS, but so may disabled output, a short, low boost voltage, or
ordinary start-up. The board does not expose U5's internal current-limit or
thermal state. U5 has only IN, OUT, ISET, EN and GND pins; there is no FLT pin.

## Manufacturer limits and calculations

Primary source: [Silergy SY6280/SY6280A Rev1.0E datasheet](https://www.silergy.com/download/downloadFile?ftype=note&id=4369&type=product),
pages 2, 4 and 7. The ordering table includes the fitted SY6280AAC. Page 2
defines `ILIM(A)=6800/RSET(Ω)`, so R10=12 kΩ gives **0.567 A nominal**.
Page 4 specifies `ILIM=0.75…1.25 A` at **RSET=6.8 kΩ, VIN=5 V, COUT=10 µF,
TA=25 °C**. If its ±25% ratio were applied to 12 kΩ, the illustrative range
would be 0.425…0.708 A (0.421…0.715 A with an assumed ±1% R10). That is
an extrapolation, **not a guaranteed bound** at 12 kΩ or hot/cold corners.
The sheet also lists a general `ILIM(min)=0.4 A`, which cannot guarantee
delivery of a 500 mA keyboard load.

The only turn-on datum is **130 µs typical** at `RL=10 Ω, COUT=1 µF`; the
board's C21 alone is marked 100 µF. Even an ideal constant 0.425 A would
need at least `100 µF × 5 V / 0.425 A = 1.18 ms` to charge 100 µF to 5 V
with no load. This is a charge lower bound under that assumed current, not
a turn-on guarantee: effective capacitance and the actual transient limit
are unbounded here. The datasheet's 63 mΩ switch resistance, 130 °C thermal
shutdown and 20 °C hysteresis are typical values. It describes constant
current on overload and thermal cycling on a sustained short, but specifies
no maximum current overshoot, fault response time, thermal trip time or
restart interval. It cautions that an output short can ring VIN above the
absolute maximum without adequate input decoupling; a static DRC cannot
bound that transient.

At nominal values the GPIO8 divider produces
`VBUS × 22/(15+22) = 0.5946 × VBUS` (2.97 V at VBUS=5 V). This equation
does not guarantee the voltage or time at which firmware asserts the flag:
that needs the populated resistor tolerances, RP2040 GPIO threshold limits,
VBUS/output capacitance under bias, boost behavior and the fault waveform.
The firmware samples it once per main-loop iteration and adds no timed
qualification or short classifier.

## Closure decision

To retain the catalogue's **≤500 mA** and **fault flag on short** wording,
select a switch with a guaranteed maximum short-circuit/current limit over
the operating corners, a real fault output with bounded assertion behavior,
and a guaranteed minimum limit above the required keyboard current if 500 mA
service is still intended. Then bind its exact populated setting components,
capacitance, input/return path and GPIO logic to the routed board and simulate
or measure the worst-case short/turn-on/thermal response. The existing
SY6280AAC plus VBUS divider cannot fulfill the literal fault-output claim.
Alternatively, revise the requirement to an explicitly bounded VBUS-low
monitor and specify an acceptable current range and detection latency; the
present Silergy sheet still lacks the corner and transient limits needed to
certify that revised requirement. **Do not clear IC-005 from the nominal
equation, typical waveform, or routed connectivity alone.**
