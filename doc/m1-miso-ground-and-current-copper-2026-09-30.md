# M1 MISO ground, temperature and current-copper audit

## Recommendation

Retain the fitted TI SN74AHC1G125DCKR, 270-ohm series resistor and **10k shunt**. Five freshly routed card screens pass bounded voltage checks; a complete current-copper qualification is still required. The 8.2k alternative buys positive-ground headroom but reduces the guaranteed negative-ground logic-high margin and lacks an imported verified supplier part. It remains a rejected adoption tradeoff, with development evidence retained.

No overshoot waiver, manufacturing receipt exemption, supply rescaling or voltage-limit change is made here. Board stock checks failed under restricted DNS; passing physical outputs can support research without becoming passing fabrication receipts.

## Fresh physical screens

Each screen copies the genuinely refreshed Main/card PCB and netlist after the actual pipeline logged `DRC + schematic parity ok`. Immutable manifests include board, model and solver-source hashes. It directly extracts copper for development; it does not fabricate an evidence receipt.

| Card | Cases | FPGA peak / trough, V | Latest final threshold crossing, ns |
| --- | ---: | --- | ---: |
| Storage | 64 | 3.5738 / -0.0018 | 30.41 |
| Wi-Fi | 64 | 3.5735 / -0.0019 | 30.49 |
| GPU | 64 | 3.5738 / -0.0018 | 30.42 |
| E-ink | 64 | 3.5738 / -0.0018 | 30.41 |
| IO | 64 | 3.5743 / -0.0016 | 32.85 |

All 320 cases complete with zero voltage-stress failures and unchanged frozen source hashes. They cover nearest/farthest slots, single/all-six-card loading, genuine min/max driver corners, both connectors, paired line/load extrema and opposing ±3% physical resistor bounds. DCK/FPGA package extrema are coupled to driver corners in these discriminators; independent package combinations, interior slots and mixed card loads remain required. Maximum corners use +40 mV local ground; minimum corners initially use zero ground. IO uses the repaired genuine pipeline log `io-repaired-refreshed.log`; its older failed run is preserved separately.

An additional 48-case negative-ground study covers actual GPU/Storage/Wi-Fi, minimum 3.0 V, −40 mV ground and maximum series/minimum shunt bounds, comparing physical10k and hypothetical8.2k. All pass stress; worst trough is −0.0391 V and latest threshold crossing30.74 ns. Fully loaded GPU J16 modeled final high is2.47307 V for10k,2.38645 V for8.2k. This does not replace static guaranteed VOH calculations.

Artifacts: `/tmp/cupc8-si-resume/actual-{storage,wifi,gpu,eink,io}-screen/`, associated logs; `/tmp/cupc8-si-resume/negative-ground-sensitivity/`. Normal early data-edge diagnostics are still recorded. These MISO-only screens have no actual-clock-derived sampling qualification by themselves.

## DC ground accounting

Fresh Main ground raster extraction uses the actual U7 ground pads and sampled A3/B17 return fingers in every slot, at0.15/0.1 mm grids. The largest sampled resistance is6.12167 mΩ (J11.A3, coarse). Some coarse/fine changes reach36.46%; **convergence is not established**. Endpoints do not exhaust every ground finger. Copper assumptions are hot/minimum plating and conservative geometric erosion; component/solder terminations and contact bounds remain external.

Fresh Wi-Fi reciprocal extraction uses all15 installed J1 ground fingers. Maximum ESP-pad-to-buffer-ground transfer is3.87794/3.21467/2.98127 mΩ at0.15/0.1/0.07 mm. This is more physically useful than injecting the entire ESP current into the tiny buffer ground pad. The U3 self-pair is13.44468/12.03826/11.74307 mΩ; the U2-to-U3 transfer is0.61041/0.48857/0.45294 mΩ. The first refined transfer change is17%, the last7.8%; retain the larger coarse values for screening.

M1's conservative positive-return allocation is2.7336 A: current `LOADS_3V3` sum0.6253 A, Wi-Fi stress0.5083 A, and both IO/GPU slots' declared0.8 A +5V bounds. This intentionally avoids relying on a guessed minimum converter input voltage. Under the sampled Main resistance it gives16.735 mV. For Wi-Fi, single-contact30 mΩ times0.5083 A adds15.249 mV; ESP0.5 A through the coarse transfer adds1.939 mV; LEDs0.0083 A and the complete0.006 A buffer/bias operating allocation placed at the worst local self-pair add approximately0.193 mV. The resulting **conditional positive DC screen is about34.12 mV**.

Balanced-current reciprocity/maximum-principle bounds allow distributed load returns rather than assuming all current flows through the buffer's ground stub. Main external ground potentials and card-local load response must be superposed, avoiding double counting circulating contact current. A negative main-plane displacement is possible. Conservatively assigning a negative buck-ground injection up to0.5083 A adds15.249 mV through the contact plus0.310 mV through the coarse U2-to-U3 transfer; together with the same16.735 mV Main term, the **conditional negative DC screen is about−32.30 mV**. These depend on the modeled load locations, conservative contact assumption and sampled/converged geometry qualifications; they are not guaranteed measured bounds.

**Neither calculation proves a40 mV total SI ground envelope.** Nanosecond plane/package/connector inductance, simultaneous switching, decoupler return current and negative transient bounce are not modeled by a resistive raster. Fully populated future maximum-power card combinations also cannot inherit the M1 load allocation. Necessary qualification includes complete routed return/contact coverage and actual local-buffer-to-FPGA-ground transient measurement under simultaneous worst M1 activity. A +40 mV DC choice alone cannot waive missing transient proof.

Artifacts: `/tmp/cupc8-si-resume/ground-current-{main,main-b17,cards,wifi-transfer}.{py,log}`, PCB snapshots and `ground-current-main-summary.json`.

## Temperature and input-current scope

The genuine SCLM008 output model declares **typ40°C/min100°C/max−40°C**, not a125°C slow corner. The datasheet14 ns/50 pF/125°C timing anchor does not supply an uncharacterized125°C routed-load waveform.

TI SCLS377M Table5.4 gives DCK θJA289.2°C/W, ψJT117.6°C/W. Table5.5 gives static ICC≤10 µA with inputs atVCC/GND. Table5.8 gives **typical**, not maximum, Cpd14 pF. The operating allocation doubles Cpd to28 pF at3 MHz, includes80 pF distributed bus capacitance and all six shunts, and reserves6 mA in total. This is an engineering allocation requiring measurement; non-rail input bias current has no separate maximum in this datasheet.

Assigning the entire6 mA allocation to one buffer die at3.6 V gives21.6 mW; the published θJA then estimates6.25°C rise and Tj46.25°C at40°C ambient. This leaves53.75°C below the model's100°C slow corner **under the allocation and applicable board thermal conditions**. Neighboring heat, actual board/chassis thermal behavior and non-rail input current are not guaranteed by that estimate. Using ψJT, the same allocation suggests2.54°C above measured package-top temperature; a measured package-top ceiling comfortably below97°C is needed to stay below100°C with additional measurement uncertainty. These are thermal screening estimates, not guaranteed interpolation between IBIS corners.

## Stronger shunt tradeoff retained as development evidence

Hypothetical8.2k passes72 coupled-extreme actual GPU/Storage/Wi-Fi cases: at+40 mV ground peak3.5400 V; at+80 mV peak3.5797 V, leaving20.3 mV stress margin. Latest crossing is29.73 ns atminimum supply. At−40 mV its modeled loaded final high2.38645 V passes.

However, TI's guaranteed VOH≥2.48 V at3 V/−4 mA, maximum278.1-ohm series resistance, six minimum shunts, five2.5 µA disabled-output leakages plus10 µA FPGA leakage, and helpful main pull-up at3.135 V give guaranteed ground0 VIH floors:

| Nominal shunt | Guaranteed bus high, V |
| --- | ---: |
| 10k | 2.11566 |
| 8.2k | 2.04994 |
| 7.5k | 2.01744 |
| 6.8k | 1.97960 |
| 4.7k | 1.81648 |

At−40 mV the8.2k guaranteed floor is approximately2.010 V: only10 mV above VIH. The6.8k/4.7k options already fail the static2.0 V requirement atground0. Retaining10k preserves more guaranteed logic margin while actual transient proof remains open.

## Gates still open

- A frozen coherent all-five-card/Main input set after the pending Main copper repairs.
- Full independent current-copper electrical corners, resistor bounds, ground signs, interior and mixed loading; numerical convergence on the actual worst case.
- Actual routed SCK/MOSI setup/hold and fixture-anchored sampled-MISO deadlines.
- Actual CS/OE skew, firmware handover gap and output release/nonoverlap qualification.
- ESP32-C3 maximum SPI-slave response remains unpublished; the RP2040 PIO bound cannot qualify Wi-Fi.
- Contact/return/DC convergence and transient ground envelope, including local and FPGA package references.
-40°C first-article supply/input-bias/current/temperature and sampling/release measurements.
- Complete valid manufacturing receipts and successful supplier/stock gates.

## Independent ground audit after the v19 power repair

The SHA-frozen, already smoothed v19 Main PCB was independently checked without
refilling: `bc166ffad627ff7e6da78cb13f8327ac00ef20266ec30cf196ffda57f0982ef3`.
The Wi-Fi PCB is the actual completed post-fill physical pipeline output at
`/tmp/cupc8-fill-rebuild-20260930/wifi/wifi.kicad_pcb`. Neither output has a
passing manufacturing receipt. The exact accelerated production copper mesh,
unchanged hot/minimum-copper corner and unchanged CG convergence settings were
used. These are DC copper results; they contain no connector-contact, solder,
component termination or package-ground impedance.

| Path or reciprocal probe | 0.100 mm, mΩ | 0.070 mm, mΩ | Relative change |
| --- | ---: | ---: | ---: |
| Main U7 ground-pad group to J11.A3 | 5.04518 | 4.82018 | 4.460% |
| Wi-Fi all 15 ground fingers to U3.3, self | 12.03826 | 11.74307 | 2.452% |
| Wi-Fi maximum ESP ground-pad transfer to U3.3 | 3.21467 | 2.98127 | 7.261% |
| Wi-Fi buck U2.2 transfer to U3.3 | 0.48857 | 0.45294 | 7.292% |

Every Wi-Fi probe changes by at most 8.043% between these grids. The Main path
was the largest earlier sampled coarse result; this refinement does **not**
prove it is the maximum over every installed slot contact or every independent
FPGA ground reference. The Main sources tie all eleven U7 ground pads to one
ideal potential. Real package-ground voltage differences remain external.
Wi-Fi reciprocity uses every installed ground finger, tied to an ideal common
boundary. A maximum-principle superposition can bound the response to distributed
positive loads once all boundary potentials and load currents are bounded;
it does not justify equal contact currents or erase contact resistance.

Using the larger new mesh values with the earlier **conditional** 30 mΩ
contact assumption gives an illustrative positive Wi-Fi DC sum of 30.82 mV:
Main `5.04518 mΩ × 2.7336 A`, contact `30 mΩ × 0.5083 A`, ESP transfer
`3.21467 mΩ × 0.5 A`, and local self `12.03826 mΩ × (0.0083 + 0.006) A`.
This is not a replacement for the more conservative earlier screen or a
guaranteed global bound. In particular, the Wi-Fi current allocation cannot
automatically qualify IO/GPU returns: their declared 0.8 A +5V allocations
alone contribute 24 mV at a hypothetical single 30 mΩ contact, before their
own +3V3 current and local/Main copper terms. A complete parallel-contact
network or independently justified lower operating-current limits are needed.

The exact fitted I/O-slot socket is **UMAX C404113, 3183-10200P1T**. Its cached
manufacturer drawing `hw/datasheets/C404113_UMAX-3183-10200P1T.pdf`, sheet 5,
references electrical **product specification PS-3G00-01**. That specification
is absent from the audited local cache; the drawing itself supplies no contact
resistance or inductance maximum. The existing 30 mΩ and 1–5 nH SI settings
therefore remain sensitivity assumptions. The separately fitted System socket
SOFNG C19188869 publishes an initial 50 mΩ maximum in its own cached sheet;
this different connector cannot establish the UMAX rating or a lifetime bound.

To establish a total ±40 mV envelope, the remaining evidence must bound:

- Every relevant Main/Card boundary and actual load-return location, including
  negative buck/decoupler current and spatially different shunt/driver grounds.
- Exact mated UMAX contact resistance over the required temperature and wear
  conditions, and pad/solder/termination contributions.
- Main and card plane/via, connector and package ground inductance, with mutual
  coupling and simultaneous switching.
- Corresponding transient current magnitudes and slopes under worst M1 activity.

A resistive mesh cannot bound `L × di/dt`. For illustration only, 1 nH with
10 mA/ns produces 10 mV, already larger than the illustrative DC headroom above.
This does not predict that excursion; it shows why unbounded inductance/current
slopes cannot be treated as zero. Genuine signal-pin IBIS package models do not
by themselves supply a complete shared ground-return transient network.
Qualification needs a defensible complete return model with guaranteed inputs,
or suitably bounded measurements of buffer ground relative to FPGA ground
during worst activity. The proposed LVC buffer passing a ±40 mV sensitivity
screen cannot supply the missing physical guarantee.

Immutable development artifacts and source hashes are under
`/tmp/cupc8-fab-release/miso-ground-v19/` (`main-convergence.json`,
`wifi-convergence.json`, `provenance.json` and matching logs). Both solves
completed successfully; no hardware, current limit or SI voltage limit changed.

## Completed current IO screen and strict clock/control audit

The repaired IO pipeline completed actual DRC and schematic parity in `io-repaired-refreshed.log`. Its immutable 64-case development screen also completed: zero voltage-stress failures, maximum receiver voltage 3.5743 V, minimum −0.0016 V and latest final crossing 32.85 ns. The five current-card screens now total 320 cases; these remain bounded development evidence, not a coherent final matrix or manufacturing receipts.

The separate 256-case routed SCK/MOSI/CS study completed all solver cases. Summary writing initially failed on a NumPy boolean; regenerating the summary from preserved results succeeded without rerunning solvers. Strict failures are 81/96 SCK, 91/96 MOSI and 64/64 CS cases. Voltage-range failures occur in 47, 52 and 53 cases respectively. The AHC OE inputs themselves have 86 failures across 58 CS cases, including negative undershoot and control-band recrossing. Arrival timing alone therefore cannot qualify CS release: its conditional one-cycle firmware-gap calculation leaves 64.73 ns after the published 16 ns/50 pF disable bound, but control integrity and distributed-load output-release proof remain open.

The R36-only discriminator used the actual M1 mix `(GPU, IO, WiFi, Storage, empty, empty)` as well as explicitly separate six-identical-card and farthest-single diagnostics. Each resistor value has 32 cases, including eight M1 cases:

| Hypothetical R36 | Strict failing cases | Voltage-stress failing cases | Latest settling, ns | M1 strict failures |
| --- | ---: | ---: | ---: | ---: |
| 33 Ω | 29/32 | 17/32 | 20.99 | 8/8 |
| 68 Ω | 32/32 | 0/32 | 27.85 | 8/8 |
| 150 Ω | 32/32 | 0/32 | 42.68 | 8/8 |
| 330 Ω | 32/32 | 0/32 | 74.99 | 8/8 |
| 680 Ω | 32/32 | 0/32 | 142.15 | 8/8 |

These results do not authorize a value change. At 330 Ω, a genuine maximum-driver M1 case still has storage clock nonmonotonic excursions of about 164 mV rising and 184 mV falling, with 114 mV falling ringback. A joint 270/330 Ω study on the existing R35/R36/R37–R42 footprints is separate hypothesis evidence; AUX_CS R43 is excluded. Physical values remain 33 Ω.

### Pin limits and ESP scope

TI SCLS377M specifies AHC **input** recommended 0–5.5 V and absolute −0.5–7 V, independently of its local supply. The positive OE spikes near 4 V are consequently not input overvoltage failures. The output's VCC-relative limits remain separate; negative OE undershoot and clock/control quality remain enforced.

The [official ESP32-C3-MINI-1 datasheet](https://documentation.espressif.com/esp32-c3-mini-1_datasheet_en.html) publishes GPIO −0.3 V to VDD+0.3 V as a valid DC input range, without a separate GPIO absolute maximum or clamp-current rating. The numerical screen stays unchanged; its diagnostic now says “published DC input range,” without asserting that every excursion predicts damage. Current waveforms use a capacitance-only MCU input approximation, not genuine ESP/RP2040 IBIS clamps. Source and Wi-Fi local supply corners are also independent in hardware, so a shared driver-corner supply is not a complete local-rail qualification.

Actual Wi-Fi MISO uses GPIO5, through the GPIO matrix, rather than direct IO_MUX GPIO2. The [official C3 SPI-slave guide](https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32c3/api-reference/peripherals/spi_slave.html) publishes no worst-case MISO response delay for that path. The firmware initially queues only descriptor 0, then queues the alternate descriptor from its completion ISR. It assumes a 20 μs host interframe gap and has no proven ISR readiness bound. The root audit found flash-resident callback helpers and a missing IRAM interrupt allocation flag; those software repairs are in progress, with no worst-case latency guarantee inferred. Frequency capability and conditional RP2040 budgets do not supply this missing guarantee. Qualification needs measured response/setup and descriptor readiness under worst concurrent M1 activity, or a separately proven protocol/timing implementation.

### Joint existing-footprint damping result

The 96-case joint study completed in 87 seconds with unchanged snapshot hashes. Both 270 Ω and 330 Ω eliminate bounded voltage-range failures, but neither passes strict clock/control criteria:

| Joint source resistors | Signal | Strict failures | Voltage-range failures | Latest settling, ns |
| --- | --- | ---: | ---: | ---: |
| 270 Ω | SCK | 8/8 | 0/8 | 50.685 |
| 270 Ω | MOSI | 8/8 | 0/8 | 56.025 |
| 270 Ω | Four fitted CS lines | 32/32 | 0/32 | 17.005 |
| 330 Ω | SCK | 8/8 | 0/8 | 60.145 |
| 330 Ω | MOSI | 8/8 | 0/8 | 65.085 |
| 330 Ω | Four fitted CS lines | 32/32 | 0/32 | 19.735 |

These are specifically the current M1 four-card mix, not six-identical-card diagnostics. Conditional RP2040 MOSI setup/hold remain positive at 106.935/113.717 ns, but strict signal quality and Wi-Fi response remain red. No resistor hypothesis was adopted. Artifacts: `/tmp/cupc8-si-resume/spi-joint-sensitivity/{inputs,results,summary}.json` and matching `.log`.

Focused waveform, genuine-AHC, sampled-data and qualification-rate tests pass: 19 tests. The new limit regressions verify that a positive 4.2 V AHC input is distinct from output overvoltage, negative −0.6 V AHC input still fails, and ESP published input-range violations remain enforced without mislabeling them as an unpublished absolute maximum.

### Bounded waveform and numerical audit

One failing actual M1 slot4 CS case at hypothetical 330 Ω was rerun at 10 ps and 5 ps maximum timesteps. The rising nonmonotonic excursion changes from 648.2 to 646.9 mV and rising band ringback from 411 to 413 mV; the failure is not removed by timestep refinement. Genuine FPGA fixture replay agrees within 9.24 ps at crossing and 0.11 mV at the endpoint. The reconstructed Ku/Kd source is smooth; approximately 1.3 ns receiver oscillations ride the slow source-resistor charging envelope. This points to routed/receiver resonance within the model, while uncharacterized MCU input package/clamp behavior remains a qualification limitation. Artifacts and plot: `/tmp/cupc8-si-resume/control-wave-audit/`. No thresholds, source waveform or physical hardware changed for this audit.
