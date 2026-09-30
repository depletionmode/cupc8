# M1 SPI receiver and local filter discriminator

## Decision

No new clock/control hardware is adopted and the normal gate remains red.
The current isolated native proposal preserves main bus routes: Main SCK/MOSI33 Ω,
six CS68 Ω; RP receiver220 Ω/10p filters; genuine TI LVC125 MISO and separate
local OE220 Ω/10p. Manufacturer-scoped RP Schmitt qualification is bound to
explicit firmware state and compiled proofs. All96 bounded actual OE screens
pass; the broader768-case opposed screen and128-case actualMainv3 CS4
recheck also completed with zero required failures. Actual WiFi level-stage
routing, combined population/timing coverage, ground/transient assumptions,
source adoption and component/manufacturing gates remain open. The sections
below retain earlier failed hypotheses and show the progression of evidence.


## Pad versus die

The actual M1 slot4 storage CS worst case was simulated at both physical receiver pads and modeled die inputs. RP2040 and genuine TI AHC OE pads ring together; the package adds little to the observed excursion. The same failure survives 10 ps to 5 ps timestep refinement. Genuine FPGA fixture replay is within 9.24 ps crossing / 0.11 mV endpoint. Thus the problem is a routed/receiver resonance within the model, not simply an invented RP2040 package resonance or poor source fixture reproduction. MCU capacitance/package/clamp approximations remain a limitation; this is not a measured false-clock claim.

## Bounded passive trials

The initial trials in this section used ideal research passives. Later sections separately introduce actual routes, explicit ESR/ESL/return sensitivity and concrete supplier identities; those developments do not retroactively qualify these initial trials.

- Six source-side CS trials: baseline 33/330 Ω, 100 pF after the source resistor at 68/150/330 Ω, and 220 pF at 150 Ω. All fail strict quality. Pure C slows the charge and shifts the resonance instead of dissipating it.
- Four source-side series-RC shunts: 68/100 Ω with 100/220 pF, source series 33/68 Ω. All fail.
- Six card-end CS trials at the shared AHC OE input: four AC termination branches, plus direct 47/100 pF shunts with 68 Ω source. The RC branches fail. Direct 47 pF passes genuine AHC OE strict quality and voltage stress at this single maximum case; remaining RP2040 whole-band adverse excursions are 24.85 mV rising and 37.35 mV falling. The corresponding physical-pad values are 20.67/33.30 mV. Direct 100 pF leaves RP excursions 134.16/145.26 mV and also passes AHC OE at this point.

Artifacts: `/tmp/cupc8-si-resume/control-{wave,pad-filter,rc-filter,receiver-filter}-audit/`; classification is `control-receiver-filter-audit/hysteresis-classification.json`.

## Receiver-specific primary requirements

The [RP2040 datasheet](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf), Table625, lists minimum 0.2 V input hysteresis at nominal 2.5/3.3 V with Schmitt enabled; Table341 resets SCHMITT to1. Section5.5.3 describes process/temperature/voltage characterization, but supplies no continuous hysteresis curve across the actual 3.135–3.465 V allocation. Table624 gives case temperature −40..85°C; a different component's 100°C junction target cannot extend that scope.

Current `fw/rp2040/common/slotspi.c` calls `gpio_init` for SCK/MOSI/NCS. The installed SDK implementation masks IE/OD only; SCHMITT is preserved. No firmware call disabling input hysteresis was found. A future firmware change must preserve this prerequisite explicitly.

The blanket 1 mV monotonicity test is a conservative waveform proxy, not the manufacturer's RP2040 guaranteed glitch rejection threshold. For a guaranteed Schmitt threshold pair, the necessary conservative diagnostic bounds the **largest adverse excursion over the entire edge**, after clipping to the full VIL–VIH interval. It includes late re-entry and accumulated small reverse steps, not just each local ripple. A bounded excursion below applicable guaranteed hysteresis cannot reset any possible threshold pair. A full VIH-to-VIL recross fails. Large excursions exceeding hysteresis prevent proof but do not identify the unknown threshold of a particular chip.

The new `hysteresis_edge_diagnostics` is unused by production gates. Six regressions cover small safe reversal, cumulative reverse steps, late full-band re-entry, falling polarity, missing coverage and unchanged voltage-stress rejection. All 25 focused SI tests pass.

AHC OE has no published Schmitt rejection guarantee, so its strict control criterion stays unchanged. ESP32-C3 also lacks a published guaranteed input hysteresis in the audited module DC table; RP2040 reasoning cannot qualify Wi-Fi.

## Actual M1 mixed SCK discriminator

Hypothetical R36=68 Ω plus equal local input capacitors on GPU, IO, Wi-Fi and Storage was tested at typ and coupled min/max corners, with respective 0/−40/+40 mV card-ground sensitivities. These are six genuine solver cases for 47/100 pF and three for 68 pF, not full independent loading/corner proof.

| Each card's SCK capacitor | Worst RP whole-band adverse, typ/max/min | Latest settling, typ/max/min |
| --- | --- | --- |
| 47 pF | 160.49 / 205.41 / 141.45 mV | 44.104 / 34.920 / 44.214 ns |
| 68 pF | 143.86 / 151.89 / 107.85 mV | 54.675 / 45.479 / 56.815 ns |
| 100 pF | 85.20 / 83.25 / 77.77 mV | 69.944 / 62.595 / 76.645 ns |

47 pF exceeds nominal RP hysteresis at the IO maximum point. 68 pF is below that nominal guarantee in these points, but Wi-Fi still has 4–38 mV slope reversals without a guaranteed receiver hysteresis. All three 68 pF cases therefore retain strict failures. No stress failure appears in these bounded filter cases under the existing shared-rail receiver approximation; actual independent Wi-Fi supply/input stress remains unqualified.

At 3 MHz, the existing fixed response/setup allocation is 64.25 ns. The bounded current RP-card MISO maximum fixture-anchored delay is 42.5042 ns (six-identical IO J16 diagnostic). Combining it with the largest 68 pF SCK delay gives a **conditional 3.097 ns margin** against the 166.667 ns half-period. This is too tight to adopt before capacitor/series bounds, package/loading independence, actual mixed MISO and coherent final copper. 100 pF already exceeds this combined timing allocation. MOSI setup/hold and CS enable/release must also be recalculated on the final candidate.

Artifacts: `/tmp/cupc8-si-resume/sck-card-filter-audit/` and `sck-card68-filter-audit/` with scripts, logs, snapshots and waveforms.

## Genuine local Schmitt option for Wi-Fi

The [TI SN74LVC3G17](https://www.ti.com/lit/ds/symlink/sn74lvc3g17.pdf) provides three noninverting Schmitt buffers, tolerant inputs and local-supply outputs. Its published hysteresis minimum is 0.56 V at 3 V, and its 3.3±0.3 V propagation maximum is 5.4 ns in the 85°C table. The primary timing reference is Figure3, the second fixture, with 50 pF and 500 Ω at 3.3±0.3 V; the preceding Figure2 is the separate 15 pF fixture. The initial fixture ambiguity is resolved. It could isolate Wi-Fi SCK/MOSI/CS from independently varying local supply while preserving main routes, but needs actual input excursions, genuine output/package model, short output routes, supply corners and timing proof. Its output cannot simply be declared perfect.

[TI's product page](https://www.ti.com/product/SN74LVC3G17) links genuine IBIS SCEM364 RevA and behavioral SPICE SCEM602. The raw archive is unavailable locally: permitted shell DNS fails and web fetch cannot decode the binary archive. [SN74LVC1G17](https://www.ti.com/product/SN74LVC1G17) is a smaller single-channel alternative with genuine SCEM299C IBIS, but three signals require three devices.

Official LCSC web pages identify exact TI parts: [DCUR C68245](https://www.lcsc.com/product-detail/C68245.html), [DCTR C18213](https://www.lcsc.com/product-detail/C18213.html), and [1G17DCKR C10425](https://www.lcsc.com/product-detail/C10425.html). Their displayed stocks are 3300 / 1666 / 114690, with crawler freshness four days / two weeks / today respectively. This is sourcing feasibility evidence, **not current JLC assembly-stock qualification**. No library import, purchase or physical adoption occurs.

## Cached genuine faster-MISO candidate

Focused local inventory found genuine SCEM270 Rev1.3, including `LVC1G125_DCK`, but no G17 Schmitt model. The DCK package envelope matches the AHC file; output Ccomp is 4.93–6.96 pF and genuine corners are 3.0/3.3/3.6 V at 100/40/−40°C. The existing TXB0108 model is a bidirectional translator, without a characterized Schmitt threshold; it is not a substitute for the required G17 input guarantee. Inventory: `/tmp/cupc8-si-resume/local-vendor-model-inventory.json`.

64 current-M1 mixed-load hypotheses substitute genuine TI LVC DCK for all four AHC models, retaining the physical copied files unchanged and declaring proposed R60=270/220 Ω, R61=10k and R107=100k. Coupled genuine min/max/package/Cin, both line/connector corners, opposing ±3% resistor bounds and ±40 mV ground are included. This is development evidence, not a change to fitted parts or receipts. All64 pass voltage stress, while 30/32 per value retain early MISO uniform-edge diagnostics. The LVC fixture anchor correctly uses 50 pF, 500 Ω to ground and the specified 1.5 V threshold, with the cached RevU 125°C maximum 4.7 ns.

| Proposed R60 | FPGA peak / trough | Maximum anchored delay | Conditional margin with SCK68 pF | With SCK100 pF |
| --- | --- | ---: | ---: | ---: |
| 270 Ω | 3.3028 / −0.0326 V | 31.7937 ns | 13.8079 ns | −6.0221 ns |
| 220 Ω | 3.3610 / −0.0344 V | 27.1636 ns | 18.4380 ns | −1.3920 ns |

Primary LVC IOZ is 10 μA, versus AHC2.5 μA. With one card, the existing 47k pull-up gives a guaranteed idle upper bound 0.8392 V at main3.465 V, +40 mV local ground, opposed ±3% resistors and +10 μA each of FPGA and disabled-buffer leakage: it fails VIL0.8. The proposed existing-footprint 100k pull-up reduces this to0.555 V; the empty-bus lower bound remains2.105 V with main3.135 V and10 μA FPGA leakage. Removing the pull-up would lose the required empty-bus high state and is not proposed.

For six loaded cards, guaranteed LVC VOH≥2.4 V at 3 V/16 mA, source and every shunt ground at −40 mV, R60 +3%, each 10k shunt −3%, R107 +3% at main 3.135 V, five disabled-output leakages of 10 μA and FPGA leakage of 10 μA give high floors **1.99613 V at 270 Ω (fails VIH 2.0 V)** and **2.05512 V at 220 Ω**. The earlier 2.00199 V calculation incorrectly left the shunt grounds at main ground while shifting the source; that assumption is removed. Corresponding four-card floors are 2.10560/2.14860 V. The original six-loaded SI requirement is not waived. Sole-active fast stress, full-six/interior/independent corners, physical exact part/stock/import and final sampled timing remain required before adoption. Also extract controller-to-buffer A traces and the new input Ccomp: these MISO cases start at buffer Y and do not prove the RP2040/ESP32 output-to-buffer input delay. Existing local /MISO_OUT cases cover storage/eink only; no nominal 5 pF RP2040 pad-delay assumption should silently cover a larger substituted input load. Artifacts: `/tmp/cupc8-si-resume/miso-genuine-lvc-dck-audit/{inputs,fixture,results,summary}.json`; all64 solver cases completed in93 seconds with frozen hashes unchanged.

A separate terminal 64-case nearest/farthest discriminator covers GPU/IO/Wi-Fi/storage, alone and six-identical loaded, genuine min/max, line 0.9/connector1, paired package/Cin, opposed ±3% passives, ±40 mV card grounds and the proposed 100k pull-up. **All64 pass unchanged voltage stress**, while all retain the old uniform early-edge diagnostic. FPGA peak/trough bounds are 3.5818/−0.0505 V at 270 Ω and 3.6160/−0.0619 V at 220 Ω. The 220 Ω sole-GPU J16 crest exceeds the DC 3.6 V limit and passes only the existing Lattice allowance of at most3.66 V for at most1.6 ns; no new allowance or voltage-limit relaxation is introduced. Maximum fixture-anchored delays are 39.0160 ns at 270 Ω (six IO, J16, slow corner) and 31.7659 ns at 220 Ω (six IO, J16, fast corner). The latter leaves a conditional 13.8357 ns with the previously screened SCK68 pF delay; SCK100 pF still misses by5.9943 ns. This is not capacitor-tolerance or full independent-corner qualification. Solver runtime90 seconds, input hashes unchanged. Artifacts: `/tmp/cupc8-si-resume/miso-genuine-lvc-extremes-audit/{inputs,fixture,results,summary}.json`.

The genuine input Ccomp envelope is 0.87–1.36 pF for LVC versus0.81–1.00 pF for AHC, before package and local trace capacitance. Both A and OE input loads must be re-extracted if the buffer changes; the small capacitance increase is not itself evidence of a delay failure, but has not yet been included in controller-to-A or CS waveform/timing proof.

### Wider ground-envelope discriminator

A separate 32-case 220 Ω/10k/100k nearest/farthest sole/six discriminator at **±80 mV** completed in48 seconds, with input hashes unchanged. Eight sole-card fast-corner cases fail unchanged voltage stress. J11 GPU/storage reach3.616 V for204.82 ns above3.6 V; IO3.614 V/209.34 ns and Wi-Fi3.614 V/214.05 ns. J16 GPU/storage reach3.656 V for118.20 ns, IO3.654 V/122.44 ns, Wi-Fi3.652 V/118.27 ns. These exceed the existing1.6 ns AC-duration allowance. No case is accepted under a wider envelope. Six-card guaranteed high at−80 mV is2.01519 V; sole-card guaranteed idle upper at+80 mV is0.59116 V. Static logic feasibility does not repair the positive-ground voltage-stress failure. Artifacts: `/tmp/cupc8-si-resume/miso-genuine-lvc-ground80-audit/{inputs,fixture,results,summary}.json`.

### MOSI sampled-data classification

RP2040 MOSI now uses the earliest qualified routed rising-SCK crossing minus worst published input-pad skew as its setup deadline. Voltage stress remains required; final threshold crossing covers the interval through the next data transition, and existing setup/hold timing budgets remain mandatory. Old early-edge diagnostics remain in the report. Clocks, CS/OE and ESP32 inputs are not qualified by this change: ESP32 AC setup/hold is unpublished. Focused sampled-data/voltage/hysteresis/rate regressions:28 pass, including early ripple, late recross, overvoltage and missing-clock counterexamples.

### Genuine LVC control-capacitor discriminator

With actual M1 mixed copper, genuine LVC A/OE input loads, source68 Ω ±3%, card grounds±40 mV, paired min/max package/Cin, both line corners and connector1, 40 bounded cases test SCK68 pF and shared-buffer CS47 pF, each±5%. All40 pass unchanged voltage stress; all32 LVC OE inputs pass strict asynchronous quality. Latest SCK/CS crossings are59.9446/15.485 ns. All24 RP SCK receiver cases have whole-band adverse excursion below the published200 mV minimum; worst191.4618 mV leaves only8.5382 mV before additional independent bounds. This diagnostic does not replace the production clock gate or characterize ESP hysteresis.

Four GPU fast CS cases still have RP whole-band reversals up to1.2 V despite the clean LVC OE input. Shared-buffer capacitance does not damp this separated local MCU branch adequately. A second local capacitor at GPU U1.7 was tested:10 pF±5% passes voltage stress, LVC OE strict quality and RP200 mV diagnostic in all8 bounded min/max/both-line cases; worst RP excursion129.8277 mV, latest CS15.685 ns.22 pF produces two LVC OE strict failures, so10 pF is the candidate for broader screening. U1.7 F.Cu pad is(29.4375,−15.8) mm with C12(31.2,−17.2) and C3(31.8,−14.4) nearby; actual new placement, ground connection, parasitics and DRC remain unproved. No source adoption.

The first research runner failed to insert capacitors because it compared an integer drive index with a signal-name string; its output is explicitly markedINVALID. The corrected v2 produced valid40 cases. A subsequent waveform replay encountered /tmp quota failures; five saved quota-era waveforms were regenerated after root archival freed space. All final40 waveforms now agree with their independently recorded extrema. Artifacts: `/tmp/cupc8-si-resume/lvc-control-cap-discriminator-v2`, `build/scratch-si/lvc-control-cap-wave-proof`, `build/scratch-si/gpu-cs-local-filter-corners`.

The broader192-case SCK screen is terminal: genuine min/max, independent FPGA package/MCU input-C bounds, both line corners, connector1, all-six-identical GPU/IO/Wi-Fi/storage/eink and actual M1 mixed, source68 Ω±3%, grounds±40 mV, local68 pF±6%. The6% hypothesis covers5% initial tolerance plus conditional C0G30 ppm/°C drift; actual supplier/parasitics still need proof. No voltage-stress failures, but RP200 mV diagnostic fails12/32 GPU,10/32 IO,10/32 storage,7/32 eink and3/32 actual M1 cases. Actual M1 IO J12 falling excursions include203.918/202.520 mV. Six-Wi-Fi has no RP receivers and cannot be called a clock pass without its own hysteresis specification. Latest SCK crossings: sixGPU83.995, IO83.4446, Wi-Fi89.953, storage86.7966, eink86.7734 ns; actual M1 60.4347 ns. These six-card delays exceed the conditional70.651 ns remaining SCK allocation with the screened31.7659 ns LVC MISO delay. Therefore uniform direct68 pF local capacitors are not a full-six solution. Artifacts: `build/scratch-si/sck-independent-six-screen` (234 seconds). Local series-R plus smaller shunt-C is the next bounded physical hypothesis; it can isolate the capacitor from the bus while filtering the MCU pad.

### Local receiver RC clock hypothesis

A terminal64-case discriminator replaces each direct68 pF SCK shunt with a card-local series resistor followed by10 pF at the receiver pad. The local branch resistor filters the pad while isolating capacitance from the shared bus. Main source68 Ω±3%, ground±40 mV, genuine min/max, independent FPGA package/MCU input-C bounds, both line corners and connector1 remain. Local100/220 Ω and10 pF are nominal values at this stage.

| Local branch | Population | Cases | Voltage-stress failures | Uniform clock failures | Worst RP whole-band reversal | Latest crossing | Conditional LVC220 margin |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 Ω /10 pF | actual M1 mixed |16|0|0|0 mV|27.035 ns|43.616 ns|
| 220 Ω /10 pF | actual M1 mixed |16|0|0|0 mV|30.255 ns|40.396 ns|
| 100 Ω /10 pF | six IO cards |16|0|6|8.100 mV|32.965 ns|37.686 ns|
| 220 Ω /10 pF | six IO cards |16|0|0|0 mV|36.035 ns|34.616 ns|

The220 Ω branch is the candidate for subsequent bounds: it passes the unchanged uniform clock check, not merely a reinterpretation of small RP ripple. This is a hypothetical new resistor/capacitor near each receiver, requiring local track interruption and placement; main signal routing is unchanged. Actual resistor/capacitor tolerance, ESL/ESR, pad/ground connection, all card kinds/slots, independent Wi-Fi supply and final physical copper are not yet qualified. Wi-Fi’s shared-rail waveform passing these points does not prove its independent-rail input range. Artifacts: `build/scratch-si/sck-card-rc-discriminator` (69 seconds).

### Supply-corner methodology

[IBIS7.1](https://ibis.org/ver7.1/ver7_1.pdf), pp78/91, defines pull-up rail referencing and explains that models without ISSO PU/PD do not explicitly characterize I–V changes with supply variation. Genuine SCEM2701.3 contains neither keyword. Referencing its3.6 V fast I–V table to a lower external rail is possible algebraically, but neither the supply-dependent transistor modulation nor switching weights are validated. It cannot be asserted as a guaranteed conservative replacement without vendor evidence or a validated model; no waveform is rescaled and no fast corner is discarded.

The [TI TLV62569 datasheet](https://www.ti.com/lit/ds/symlink/tlv62569.pdf), Table6.5, bounds VFB at0.588–0.612 V.453k/100k at opposed0.1% tolerances gives3.38991 V DC upper; adding25 ppm/°C divider drift from25°C to100°C gives approximately3.40035 V. These calculations do not bound dynamic ripple, light-load power-save elevation, startup or load-release overshoot: the published waveforms are typical. The design's3.465 V maximum is a qualification target, not a vendor-guaranteed transient ceiling. Wi-Fi's previous modeled main-referenced3.58128 V maximum is also conditional. A measured/validated local supply-plus-ground envelope remains necessary before using smaller actual-rail corners for qualification.

## Remaining actions against the original M1 requirements

The governing documents are `doc/hardware/verification.md` §4.6/§5, `doc/hardware/slot.md` and catalogue MB-007. The accepted operating-rate qualification is3 MHz;6 MHz remains an unsupported diagnostic. MB-007 still explicitly calls for six slots loaded. The actual four-card M1 screen is essential, but cannot silently replace the published six-loaded requirement or turn its failures into an accepted future-only exception. Accepted IO/System USB first-article exceptions do not authorize SPI stress or clock exceptions.

| Finding | Disposition | Concrete next action |
| --- | --- | --- |
| Fitted33 Ω SCK/MOSI/CS produce large modeled input excursions | Electrical qualification failure; MCU clamp approximation is a model limitation, not permission to exceed limits | Complete source-resistor/candidate input-load sweep on coherent final copper, preserving voltage bounds and all required loads.68 Ω removes bounded stress, but full proof is unfinished. |
| Large SCK reverse excursions can exceed RP guaranteed hysteresis | Clock qualification failure, not sampled-data early-ring exemption | Use whole-edge adverse bounds with actual Schmitt settings and manufacturer operating conditions; prove final clock timing/stability.68 pF is a candidate, not adopted. |
| RP >1 mV slope failures below published applicable Schmitt minimum | Overly strict generic proxy may demand unnecessary repair | Treat published3V3-class Schmitt data as manufacturer qualification evidence under rated supply, VSEL, enabled input and case-temperature conditions. Absence of a continuous hysteresis curve alone is not proof that a new buffer is necessary. Retain scope and sensitivity explicitly; do not extrapolate to out-of-range operation. |
| AHC OE ringing/negative excursion | Asynchronous control qualification failure | Bounded shared-CS47 pF candidate passes one point; test all slots/types, all tolerances and new LVC input loads if substituted. Prove CS stable before first SCK and release/nonoverlap across handover. No Schmitt guarantee is assigned to AHC. |
| Early MISO uniform-edge diagnostics | Often harmless for sampled data, provided stress and deadline/stability proof pass | Apply actual sample/setup interval, fixture-anchored delay and no later threshold-band recross; retain original diagnostic separately. Full final-copper coverage is required. |
| MOSI early-edge diagnostics | Sampled data, with independent setup/hold obligations | Evaluate its actual sample windows rather than inferring failure from harmless early slope reversals; do not treat clocks or OE this way. No MOSI gate change is made in this audit. |
| Wi-Fi independent local rail versus main high level; GPIO clamp/hysteresis unpublished | Incomplete electrical proof; no demonstrated silicon damage and no permitted overvoltage assumption | Solve coincident local rail, receiver voltage and ground reference. If input range cannot be preserved, qualify genuine local tolerant-input Schmitt/level buffer on SCK/MOSI/CS. Acquire authentic model and stock evidence when permitted network access returns. |
| LVC faster-MISO candidate and pull-up | Viable bounded timing hypothesis, still incomplete | Qualify sole-active fast stress and full six/interior/independent cases; choose270/220 based on guaranteed static high, voltage margin and timing.100k pull-up is needed for guaranteed sole-card idle with LVC leakage. Exact part/stock/library/source guards and all physical pipelines follow only after viability. |
|±40 mV ground sensitivity | Conditional engineering envelope, not guaranteed total ground bounce | Complete DC/contact extraction and conservatively bound simultaneous switching/package/connector return. A DC resistive raster cannot prove nanosecond bounce. Verify model bounds on first articles. |
| AHC/LVC thermal/current operating assumptions | First-article calibration obligation; not automatic PCB repair | Measure buffer current/input bias and package temperature under40°C simultaneous M1 activity. Stay inside actual vendor slow-model temperature and RP case limits; update model allocation if exceeded. |
| ESP SPI response and20 μs descriptor rearm | Silicon qualification obligation acknowledged by verification§5; absence of vendor AC table is not a failed fabricated board | Root's IRAM closure, interrupt flags, result-queue handling and memory-loop repairs have real-build/regression evidence. Measure ready/rearm and MISO setup under radio, NVS flash and sustained back-to-back traffic. A missed deadline requires firmware/protocol/hardware repair; host/QEMU tests do not supply a silicon maximum. |
| Vendor50 pF OE-disable versus distributed routed load | Actual release proof missing | Compare actual routed/load disable, CS skew and firmware gap; measure selected-output Hi-Z/nonoverlap on first articles. Datasheet50 pF maximum cannot alone prove every larger distributed load. |
| Fresh-copper/provenance/stock | Fabrication qualification gate | Freeze final coherent Main/all-card source, rebuild each physical pipeline, then rerun required corner matrix and unchanged normal receipt/stock checks. Development snapshots are not manufacturing receipts. |

### First-article measurement scope

Record exact boards, silicon part/lot, supply/input conditions, firmware hash and40°C ambient. Measure local buffer/ESP VCC–GND and input/output relative to both local and FPGA ground, coincident with simultaneous card activity. Measure sampling/setup, actual CS-to-Hi-Z and descriptor readiness, plus digital false-clock/frame-error counts. Passive10× probe loading may substantially change a small-capacitance input; account for probe capacitance in the reproduced model. The roughly1.3 ns modeled oscillation needs suitable high-bandwidth, low-capacitance instrumentation: the existing100 MHz rail scope cannot validate its amplitude. Functional stress alone cannot establish the unchanged absolute voltage bound.

These measurements close model/silicon/calibration obligations; they do not waive a known voltage, clock or control failure. Few first articles also do not establish future-lot process maxima. Model failures need their cause resolved before a claim of design qualification; missing silicon-only observations remain explicit pending first-article work rather than invented simulation proof.

## Continued bounded qualification: local RC and exact TI identity

The direct 68 pF SCK-to-ground candidate is superseded by a local receiver filter hypothesis: Main's existing source resistor becomes 68 Ω; each MCU SCK branch receives 220 Ω in series and 10 pF to its local ground. Isolating the capacitor from the shared bus reduces aggregate capacitive loading. On the frozen research copper, phase 1 completed 192 cases and phase 2 completed 384 cases: all 576 passed unchanged voltage stress and strict clock checks. These include the M1 GPU/IO/Wi-Fi/storage mix and six identical cards of each type, genuine min/max driver corners, independent FPGA package and MCU input-capacitance bounds, both line bounds, ±3% resistor and ±10% capacitor sensitivity, and opposed ESR 0/30 Ω and ESL 0/2 nH cases. ESR/ESL are engineering sensitivity bounds, not supplier guarantees. Both phases used connector maximum; minimum connector and sole/empty states are included in the next combined replay.

A unified local CS candidate also passed all 32 bounded native-TI cases: Main CS source 68 Ω; each MCU CS branch 220 Ω plus 10 pF; buffer OE branch retains a separate 47 pF shunt. This includes the ESP receiver's unchanged strict control criterion. It supersedes the earlier GPU-only direct 10 pF CS hypothesis. It does not close Wi-Fi's independent-supply DC input-range gap, nor establish final physical capacitor placement/parasitics.

The earlier genuine-LVC waveform studies sometimes retained AHC component identities while replacing the underlying model. Their OE/A thresholds were therefore AHC thresholds, not actual LVC TTL thresholds. Native `SN74LVC1G125DCKR` identity is now supported explicitly: input VIH 2.0 V, VIL 0.8 V, input upper absolute rating 6.5 V; genuine DCK package and independent output/input Ccomp. Native local-CS replay passes. Component identity substitution remains an in-memory development hypothesis; no physical BOM or fabrication receipt is changed.

### TI negative-input current condition: implemented without a blanket voltage change

TI SCES223U Table 5.1 footnote 2 permits exceeding the negative input voltage rating when the input current rating is observed; IIK is −50 mA. All 64 RP2040-to-buffer-A cases were instrumented with a zero-volt series source before the genuine package/Ccomp model, measuring the entire pin current rather than a static clamp-table sample. The largest absolute pin current was **14.4028866 mA**; the deepest modeled input excursion was approximately −0.941 V. Thirty-two cases failed the previous voltage-only −0.5 V guard. Replaying their exact saved waveforms through the manufacturer-conditioned check leaves zero failures across all 64.

Production SI now instruments both A and OE for an explicitly identified TI LVC part. The exception applies only with complete finite pin-current coverage and, conservatively, |I| ≤ 50 mA throughout the waveform. Positive voltage, threshold/recrossing, sampling and other manufacturers' checks remain. Missing current, incomplete/nonfinite coverage, and overcurrent remain failures. This is absolute-input-rating evidence, not a guarantee of logic operation outside the recommended input range, an aggregate VCC/GND current proof, or a measured silicon response. All 36 focused regressions pass, including overcurrent, missing-current, positive-overshoot and other-part counterexamples.

Artifacts are under `build/scratch-si/miso-input-current-full` (`results.json`, saved NPZ waves, and `current-rating-audit.json`), `sck-card-rc-bound-phase1`, `sck-card-rc-bound-phase2`, and `cs-native-ti-local-rc`. The combined M1 candidate replay is under `build/scratch-si/spi-m1-combined-local-rc`; its running log and eventual results/timing files must be inspected before any conclusion. It includes M1 mixed, each sole card at its assigned slot, and empty states with both connector/line bounds. Physical/source provenance and remaining independent corner coverage are recorded in its manifest; it is development evidence, not manufacturing qualification.

### Combined M1/sole/empty result and corrected input-route timing

All **224** combined network cases genuinely completed in **337 seconds**. Final JSON serialization initially failed because a NumPy comparison produced `numpy.bool_` in a sampled-data window. The raw `results-unqualified.json` and every NPZ waveform were already complete. The SI helper now returns ordinary JSON boolean/float scalars; a regression covers NumPy deadline inputs. No computed case was rerun or discarded. A separate postprocessor records hashes of the raw network/input results and its current qualification code, preserving the frozen original study.

Requalification combines those exact 224 network results with the independently completed 64 nominal-3.3 V RP-output-to-native-TI-input cases. The budget now explicitly reserves the separately measured RP pad-to-buffer-A routed settling delay; this is distinct from the buffer's published A-to-Y propagation delay. Production MB SPI case generation includes that local route and refuses sampled-MISO qualification when its coverage is missing. The extra route delay consumes the sample budget; regressions cover missing and excessively slow local routes.

Results on this conditional frozen candidate:

| Check | Result |
| --- | --- |
| SCK unchanged strict clock and stress checks | All covered mixed/sole/empty cases pass; latest MCU settling 31.325 ns. |
| CS unchanged strict control and stress checks | All covered mixed/sole cases pass; latest MCU settling 22.775 ns. |
| MISO sampled criterion plus unchanged stress | All covered mixed/sole cases pass. |
| Native TI local inputs, manufacturer-conditioned negative injection | All 64 pass; maximum whole-pin current 14.4029 mA. |
| RP MOSI setup at 3 MHz | 115.608 ns margin. |
| RP MOSI hold at 3 MHz | 129.297 ns margin. |
| RP MISO turnaround at 3 MHz, including local A-input route | 39.065 ns margin. |
| Hardware-maximum 6 MHz diagnostic | −44.268 ns; unsupported, not qualified. |
| ESP MOSI quality | 16 covered mixed/Wi-Fi-sole cases retain strict early ringing failures. No unpublished ESP sampling/setup margin is invented. |
| ESP slave AC timing | Remains missing required silicon qualification. |

This demonstrates a promising minimal local topology rather than a finished design qualification. The separate local-input study brackets nominal RP output behavior; it does not establish a new guaranteed GPIO output envelope over all supply/temperature loads. Opposed local RC/component corners, arbitrary slot placements and coherent final physical geometry remain to be completed where required. All 39 focused regressions pass.

The independent Wi-Fi rail issue still needs a real level interface. A local TTL-input, 5.5 V-tolerant Schmitt buffer powered from the exact ESP rail can structurally resolve the static VIH/input-range mismatch, with its output on short local SCK/MOSI/CS routes. The external MISO buffer OE branch can remain separate, since its tolerant TTL input is already qualified on the bounded CS waveform. Published light-load VOH ≥ VCC−0.2 V offers a defensible static output basis against ESP VIH=0.75VCC, subject to actual pad/leakage load and rail bounds. Genuine output/package modeling, source/stock/CAD identity, output edge/stress and SPI timing qualification remain necessary; no idealized Schmitt output is substituted as proof.

Retain Main routing. Candidate value/local-network changes are Main source SCK/CS 68 Ω, MOSI 270 Ω, R107 100k; card MISO genuine TI LVC with R60 220 Ω/R61 10k; MCU SCK and CS local 220 Ω/10 pF; buffer OE 47 pF. These are unadopted research hypotheses. Total ground/transient bounds and the proposed Wi-Fi local buffer remain real open issues, not implied acceptance of ±40 mV or a new voltage allowance.

### Published ESP CS timing constraint

[ESP32-C3 TRM v1.4 §27.6, printed page 639](https://documentation.espressif.com/esp32-c3_technical_reference_manual_en.pdf) requires slave CS setup and hold **longer than half the SPI clock period**. Setup is measured to the first latch edge and hold from the last latch edge; mode 0 latches on rising SCK. At 3 MHz the required interval is therefore >166.667 ns. This is separate from the software inter-card gap used to check output contention.

The combined candidate's Wi-Fi SCK rising arrival span is 11.025–31.325 ns, CS assertion/fall 13.500–22.025 ns, and CS deassertion/rise 12.845–22.775 ns. Independent extrema give an 11.000 ns setup penalty and an 18.480 ns hold penalty. If only the automatic FPGA busy signal asserted CS at transfer start, the exact half-cycle source lead would not establish the required receiver setup after skew. An earlier explicit firmware `cs_on`/hold may supply sufficient lead and must be audited. `soc/spi_master.vhd` retains CS one half-cycle after the final falling edge; for mode 0 this gives a full source period after the final rising latch edge, so automatic hold appears ample subject to actual call/control sequence. The parent is auditing that sequence. No MOSI input setup/hold process/temperature maximum is inferred from the published SPI maximum frequency or these CS requirements.

### Wi-Fi-only MOSI local filter: bounded terminal result

A subsequent 128-case study added **220 Ω ±3% in series and 10 pF ±10% to local ground only at Wi-Fi's MCU MOSI pad**, retaining Main MOSI 270 Ω. Both M1 mixed and Wi-Fi-sole states, independent FPGA package/MCU input capacitance, genuine min/max corners, both line and connector bounds, and conditional ±40 mV ground were covered. All 128 solver cases completed in 327 seconds. The Wi-Fi MOSI waveform passes unchanged strict edge-quality and voltage checks in every case. Mixed-case RP early-data diagnostics pass the existing RP-only sampled criterion; no ESP edge criterion was relaxed. All copied source/board hashes remain unchanged.

The latest Wi-Fi MOSI settling is 65.805 ns. Against the earliest input-band entry of the separately covered routed SCK candidate, the external wire-only stable setup interval is 107.217 ns. This is not a published ESP setup/hold guarantee, nor a new qualified internal-pad/synchronizer maximum. Full matched final-copper clock/data coverage and first-article silicon timing remain necessary.

Artifacts: `build/scratch-si/wifi-mosi-local-rc-v2/{results-unqualified,results-requalified,summary-requalified,inputs}.json`, saved waveforms, and its terminal log. The initial preparation-only directory records a runner typo that stopped before solver execution; corrected v2 is the completed study. No physical source was changed. This closes the bounded MOSI waveform-quality hypothesis without requiring a Schmitt buffer solely for early ringing; independently varying supply/guaranteed VIH and input-range compliance can still require a tolerant local level interface.

At completion of these studies there are no SI or routing jobs owned by this agent running. The next engineering steps are a qualified Wi-Fi DC level interface or defensible coincident rail/input bounds; actual total return/transient bounds; physical implementation/provenance of the minimum viable filters and exact TI parts; matched final-copper all-required-population/corner timing and stress; and the published ESP CS setup/hold plus silicon readiness/output-release checks. The conditional ±40 mV cases and development copper never establish manufacturing approval.

## Later bounded M1 robustness studies and current blockers

### Main MISO bias topology

The subsequent permanent-low-idle hypothesis retains the existing **R107 100k pullup to Main 3V3**, adds a **new Main 4.7k MISO-to-Main-GND shunt**, changes every card R61 to **47k to its local ground**, and retains genuine TI LVC DCK buffers with **220 ohm R60**. It does not reconnect R107 to ground. The initial shunt is at the U7.48 model node with an ideal launch, so it is a viability screen rather than final physical qualification.

All 120 bounded cases in `build/scratch-si/miso-main-pulldown-discriminator` completed: each card type, near/far slots, sole/mixed-four/six-identical diagnostics, genuine min/max corners, paired package/input-capacitance extremes and conditional ±80/±150 mV card ground. All passed unchanged voltage-stress rules. Worst FPGA crest was 3.608 V, only 0.400 ns above 3.6 V, within the existing 3.66 V/1.6 ns allowance; worst minimum −0.1541 V. Worst fixture-anchored output-plus-line settling was 37.1593 ns. These are not arbitrary-slot/opposed-corner full qualification results.

The opposed ±3% resistor/DC screen gives four-card high floor 2.1611 V at −80 mV and 2.0945 V at −150 mV, using published TI VOH=2.4 V at 3 V/16 mA and receiver/output leakage bounds. Sole idle is 0.2415/0.2476 V at +80/+150 mV; empty-row low nominal floor is 0.1329 V before leakage. Static calculations and assumptions are in `build/scratch-si/miso-ground-static-screen`. Actual current/power allocations and resistor identity still belong in final integration evidence.

The parent found a DRC-clear physical R109 location at (96.25,63.0), angle180, with MISO pad 3.2066 mm straight from U7.48 and a separate ground launch. `build/spi-physical-prep-20260930/main-shunt-placement-proof.json` records this. Its real routed signal/ground parasitics must replace the ideal first-screen shunt before final qualification. A ±150 mV sensitivity pass is not a guaranteed total ground-bounce envelope.

ROM absent-card handling rejects zero-length responses after 20 retries of 5 ms; nonzero responses still require C8 signature. A permanent low idle can therefore add about 100 ms per empty slot, including an entirely empty row, without satisfying the signature test. This is an authorized proposed boot tradeoff, requiring documentation and native boot regression before physical adoption.

### TI local level-buffer input transition interpretation

[TI SLLA364A §1–2](https://www.ti.com/lit/wp/slla364a/slla364a.pdf) describes transition rate as a finite rise/fall interval divided by its voltage span and identifies the region between VIL and VIH as the sensitive interval. The native TI125 gate now conservatively measures first entry through final exit of the complete **0.8–2.0 V band**, including later reentry, against the published 10 ns/V maximum: 12 ns over this band. Instantaneous sampled derivative remains diagnostic. Existing clock/control monotonicity, recross and voltage/current rules remain separate and unchanged. A brief local plateau is not automatically a manufacturer-rate failure; a long whole-band transit is. Regression coverage tests both examples.

The 22 pF/220 ohm local-input study completed 96 cases; 40 retain finite-band rate failures, worst 42.63 ns. The 10 pF/220 ohm, Main MOSI68 variant completed 96 cases; 16 retain rate failures (8 SCK,8 MOSI), worst 16.71 ns. Historical pointwise failure lists in those raw artifacts are not the current manufacturer's finite-band classification.

The smaller **100 ohm/4.7 pF SCK/MOSI** discriminator completed 64 cases in 121 seconds with the corrected gate. 52 cases retain local failures: 8 SCK and8 MOSI rate failures plus strict waveform-quality failures. Worst whole-band transit is 15.830 ns (13.192 ns/V); worst MOSI in-band reversal is 89.212 mV. Thus reducing filtering sacrifices fast-corner waveform quality and still does not close the slow-corner recommended transition limit. No physical local TI125 input-stage adoption is justified by these studies.

Saved-wave comparison in `build/scratch-si/wifi-local-lvc-input-stage-v3/source-vs-input-band-audit.json` and `source-vs-input-band.png` shows slow-corner source-pad fall transit of 0.620 ns for SCK and 2.840 ns for MOSI, versus 14.558/15.830 ns at the local TI input. The bare FPGA pad transition is sufficiently fast in these loaded cases. The extended local interval arises from distributed bus/loading/filter shaping; it is not evidence that the original unloaded FPGA driver inherently exceeds 12 ns. A local Schmitt interface or different distributed filtering topology remains a plausible repair path, requiring genuine model/part evidence before adoption.

Cached model/component selectors were inspected: SCEM270 contains only LVC1G125 voltage/package selectors; SCLM008 only AHC1G125; SCEM518 TXB0108; SLVM741 TPD4E05U06. No genuine 17/14/3G17 Schmitt model is hidden in these files. Vendor artifact retrieval is currently blocked by environment network/MIME restrictions. No 125 model is substituted for a Schmitt part.

### Firmware and CS timing scope

The necessary ESP input-pull correction, real-card/QEMU builds, ISR closure and exact hashes are documented in [m1-wifi-input-pulls-2026-09-30.md](m1-wifi-input-pulls-2026-09-30.md). QEMU compilation passed; fresh runtime validation was blocked before boot by socket permission restrictions. Silicon ISR readiness remains an explicit first-article requirement.

The parent audited actual ROM/kernel held-CS call sequences. Both execute two mandatory return retirements after CS assertion and before any SPI GO write; together with the engine's two-clock first-edge delay these give at least 333.33 ns source lead at 12 MHz. Subtracting the bounded 11 ns receiver skew leaves **322.33 ns**, above the TRM's 166.667 ns CS setup requirement at3MHz. Mode0 final rising latch to automatic deassert spans two half-periods; subtracting18.48ns skew leaves **314.85ns** hold, with explicit software deassert later. These bounds apply to those audited held-CS call paths and covered candidate skew, not an unheld automatic-start interface or unpublished MOSI internal timing. Final coherent source-hash and copper binding remains necessary.

Current focused regression result: 43 tests pass (`build/scratch-si/si-focused-regression.log`). No SI or routing job owned by this agent is active. Current open gates are genuine local Wi-Fi level-interface/input-condition proof, total return/transient bounds, coherent actual minimal-filter/main-shunt physics, final matched all-required-population/corner timing/stress, exact parts/CAD/supply evidence, and first-article silicon readiness. No new electrical waiver or manufacturing approval follows from these development results.

### Source33 discriminator restores a viable local TI125 window

A single targeted follow-up reduced Main SCK/MOSI source resistors to **33 ohm** and used **220 ohm/4.7 pF** only on the Wi-Fi local TI125 SCK/MOSI A inputs. It retained other RP MCU local220/10 filters and the previous CS candidate. The 64-case independent local-input-corner study genuinely completed in124seconds with **zero failures**, including unchanged other-RP edge checks. The maximum complete TTL-band transit was **10.100ns**, below12ns; latest local-input settling20.025ns. Both line bounds, mixed/sole states, genuine min/max FPGA and independentTI inputcorners, pairedpackage/cap extremes, R±3%,C±10%, and conditional±150mV ground were covered. Opposed independent package/load populations and a coherent final physical matrix remain required.

This result shows a concrete source/receiver damping window rather than a fundamental TI125 rate limitation. It does not require the alternate two-active-buffer Main launch change. Artifacts: `build/scratch-si/wifi-local-lvc-input-stage-v4/{inputs,results}.json`, savedwaveforms and terminal log. Final values are hypothetical and no source resistor or physical buffer was adopted.

A separate 32-case genuine TI125 **output-to-local-ESP** stage also passed unchanged strict edge and voltage checks. It used genuine3.0/3.6V corners with coherentESP VIH=.75VCC/VIL=.25VCC, bothactualDCK packages, a5mm70ohm/35ps shortlocal trace, 220ohm±3% and10pF±10% atESP input, ESP1..10pF input-capacitance bracket, capacitorESR.01..30ohm/ESL.001..2nH envelope. Worst fixture-anchored A-to-ESP settling was **11.327ns**, maxcrest3.5998V and minimum.0001V. The scalar sum20.025+11.327=31.352ns is a conservative research-stage delay allocation, not an analog fullcascade model or final routed SPI timing proof.

Artifacts: `build/scratch-si/wifi-local-lvc-output-stage/{inputs,results}.json`,32savedwaveforms and terminal log. Light-load published VOH relativeESPrail remains contingent on pullsdisabled, actualpadleakage and noaddedDCYload. ESR/ESL and arbitraryshorttrace are sensitivity assumptions pending realparts/routes. OE remains hardlocalGND on threeproposedWiFilevelbuffers; the externalMISO-bufferOE47pF branch is separate. This currently offers an actionable minimal locallevel-interface candidate, with all mainbus copper preserved, contingent on fullcorner/current/ground/timing and exactphysicalidentity proof.

### Broader corner exposure and revised capacitor candidate (in progress)

The frozen source33/WiFi220+4.7 study expands independent FPGApackage/MCU input capacitance/localDCK, localrail, all four R/C tolerance combinations, mixed/sole states and pairedline/connector bounds to1536cases. Its512SCKcases completed with four genuine strict failures: WiFi-sole, Mainmin/pkg0, line1.1/connector1, localTImin3V, C−10%/R+3%, bothMCUcap choices and DCKpackages. Reentry is0.4mV forDCK0; reversal1.068mV forDCK1. No finite-rate/stress failure occurred inthose512. They remain failures under unchangedclock checks; the earlier64 pass was limited paired-axis evidence. The rest of1536 remains active, so there is no fullstudy pass claim.

A waveform-informed50-case revised-cap screen completed: **SCK5.6pF±10%26cases pass**; **MOSI4.7pF±12%24cases:20pass/four early-quality failures**, all finite-rate/current/stress checks pass. Maximum completeTTL transit9.630ns. The MOSI failures are1.9–4.4mV rising/4.4–7.5mV falling reversals infastsoledata before any qualified sampling deadline. They are preserved separately fromclockquality and do not justify blanketSchmitt or clock acceptance. A scoped sampled-data/cascade settling analysis is still needed, with actualESPAC unknowns explicit. Artifacts: `wifi-local-lvc-input-stage-v6` results/inputs/waves and terminal log. No hardware value change was adopted.

ActiveSamsung4.7p C318595 initial±.25p plusheat/drift/temperature allocation requires at least±12% inthisscreen. Parent identified tighter Murata4.7p **GJM1555C1H4R7BB01D C161327**, exactolder2017manufacturerapprovalsheet plusindexed2024initialtolerance. Murata5.6p **GJM1555C1H5R6BB01D C161329** has genuineapprovalsheet. Their normalinitial/reflow/drift/temperature additive bounds fit±10%; procurement mustconfirmcurrentexactapprovalrevision andsupplierCAD/liveJLCstock. This is not a blanketlifetime/humidity/durability guarantee. PublishedQat1MHz/ESRat1GHz do not bythemselves establishconstantESR overevery frequency; originalideal/0..30ohm envelopes remain explicitly engineering sensitivities.

The fullA-pin current monitor is beforepackage/capacitance, not justIBISclampbranch. Revised50 maximum1.248mA; early680/1536maximum1.625mA. NewlevelbufferOE ishardlocalGND, so eachnewpackage hasonehost-driveninput. NativeTI50mA whole-pin condition remains required. Aggregateboardcurrent is not incorrectly compared tothe100mA rating ofonepackage; unmodeledpower-aware internalVCC/GND current is not inferred from these monitors.

SIassembly now has explicit independent `miso_shunt_ground_delta` forR61 versuscarddriverground and `main_miso_shunt_ground_offset` forR109 versusFPGAground. Defaults retainoriginalreference. Focusedregressions verifythreeindependent ngspicegroundvoltages anddefaultidentity; **45tests pass**. ActualR109branch qualification is prepared fromauthenticround3geometry plusparent'smanualscratchPCB, augmentingonlythecandidateR109 netlist. The actual7.868mm distributed signalbranch is extracted, not replaced bystraight3.2mm oridealatpad shunt. MainshuntDC14.8965mV andcarddriver/shunt35.651mV opposite references are separate sensitivity allocations overcommon±150mV; connector/package/transient bounds remain open.

### Actual Main shunt v1: terminal128-case physical development result

`build/scratch-si/miso-main-pulldown-physical` genuinely completed128cases in506seconds. It snapshots authenticround3Main/cardnetlists+copper and the parent's manualR109v1 PCB SHA43c227a511a7f1890cf55e23d3c272c88db8414de0274cef72aeee6448fc81d2. R109 alone is explicitly augmented in the candidate netlist; genuineTI substitutions and 220/47k/100k/4.7k values are hypothesis substitutions. This does not satisfy normal source/receipt/fabrication validation.

All128 pass unchangedvoltage-stress checks. MaximumFPGA3.6077V, only0.340ns above3.6V, occursatWiFiJ14solefast withdriver+.150V, cardshuntdelta+.035651V andMainshunt+.0148965V. Minimum−.1487V; maximumfixtureanchored buffer-plus-actualbranchline30.7474ns. BothWiFi/storage3/4assignments/allfourdriverpositions, sole/mixed, opposedMain/cardshuntDCreferences were included, butline.9/connector1 andpairedpackage/source corners make this a boundeddevelopment result. ActualSCK/localRPbufferAroute deadlines remain to be bound; rawuniform-edgeMISO ringingdiagnostics remain reported. `summary.json` bindsrawresultsSHA19c1fbd27276be60019f0efe4daf6359aa082234f5a114aaf8ef292ba3d663dd.

The v1 branch is the actual7.868mm extractedsignalgraph. Mainshuntgroundmesh5.449423mΩ (.9405% .1/.07 convergence) gives aconditional14.8965mV DC bound under2.7336A positiveallocation; all11FPGAgroundpads are retained. This is separate fromcarddriver/shunt35.651mV and common±150mV screeningoffset. Contacts/package/returnL·dI/dt remain unqualified; alltheseoffsets are sensitivity allocations, not a guaranteedtotalgroundenvelope.

The parent's source-render check subsequently rejected visibleR109reference atv1(96.25,63,180). A new(98,64.5,270) localbranch/refill/groundbound is being prepared. **The terminal128v1 evidence is historical candidate viability, not finalphysical qualification.** The newbranch must be replayed. No pad/copper/ground guarantee is inherited merelybecauseexistinglongMainroutes remain preserved.


### Current corner studies and replacement Main shunt (development only)

The broader v5 study is terminal: **1536 cases in 2387 seconds**, comprising 512 cases each of SCK, MOSI and CS. SCK retains the four tiny strict failures described above. MOSI retains 18 early data-quality diagnostics, without finite-band rate/current/stress failures; CS has zero failures. Maximum whole TTL-band intervals are 9.460/9.645/8.040 ns respectively. This supersedes the earlier in-progress statement, without changing those raw results. The raw-results SHA is `026cfd4d88f390cf5e3147024dd45ee8b018b59128d1dd98145cdfa6f2be2129`.

The revised **SCK5.6 pF** study v7 is running against immutable authentic round3 copper. It covers 2048 independently opposed FPGA package, MCU input capacitance, local TI package/rail and receiver resistor/capacitor corners, both line/connector combinations, mixed-four and sole-WiFi states, and both WiFi/storage slot3/4 assignments. At 816/2048 cases (1652 seconds), no failures had been emitted; this is progress evidence, **not terminal qualification**. Actual future local filter and buffer traces are not yet present in this immutable board set and require physical replay.

`build/scratch-si/miso-input-actual-rails` independently completed **128 actual local RP-to-TI A-input cases** in approximately 86 seconds. All strict waveform, stress, whole-input-current and finite-band checks pass. The maximum local settling is 5.7523 ns, whole TTL-band interval 2.450 ns and input current 15.1235 mA. The synthetic RP source resistance/edge brackets and local-reference cancellation remain model assumptions; no guarantee for unmodeled RP-to-buffer differential ground follows. Raw SHA: `914edc2c1aeda28e3bfda9c93f4b7007008567a75b537fe162e6b92caee1c3bd`.

The final proposed Main shunt position is now **R109 (98.0,64.5,270)**. `build/spi-main-shunt-v2-20260930/main.kicad_pcb`, SHA `aa649792716583ac0e5046b8acfcab1a07b1aa090a4ca27e77e6fc790c1a0dba`, has native DRC zero/errors and zero opens after real refill, while preserving all 8143 original copper items. Its receiver-to-shunt horizontal centerline/pad-stub length is 8.987974 mm. Two real via barrels remain at (97.5974,58.4195) and (98.75,62.05); the conservative 1.76 mm/barrel conductor bound totals 12.507974 mm, which is not an impedance proof. The replay must retain each adjacent-layer barrel and unused barrel stub, rather than replacing this topology with one 8.988 mm line. The new ground mesh upper 5.604737 mΩ, with 0.889% refinement change, gives a conditional **15.321109 mV** shunt-ground difference under the 2.7336 A allocation. This supersedes v1's route/ground values and still excludes package/contact/transient terms.

A separate v2 MISO runner is prepared, not yet launched, with genuine TI corners, actual v2 distributed branch, independent ±10% barrel-span sensitivity and separate opposed Main/card shunt references. The common ±150 mV driver-offset sensitivity is not a proven total return envelope. V1's completed128 result is retained as historical viability only.

Focused SI regressions now comprise **47 passing tests**. Controller response identity is taken from the authoritative `driver_kind`, with a narrow historical driver-name fallback; arbitrary case text mentioning WiFi cannot misclassify a GPU response as ESP, and unknown identity keeps the gate unqualified. No new electrical waiver follows from these development studies.

The pinned IDF5.5.5 slave-document delay table of 43.75/68.75 ns is inside an `only:: esp32` section. It is not an ESP32-C3 guaranteed tCO/setup/hold specification. The C3's generic supported SPI rate does not replace missing worst-case AC numbers. Coherent external waveform deadlines and actual held-CS source bounds can be shown separately; C3 internal timing/readiness remains a scoped first-article measurement obligation.


Actual local level stages can add three more TI125 parts to the WiFi card. MISO discovery now selects the unique genuine TI output on `/MISO_SRC`, instead of assuming there is one TI buffer in the entire card. A new counterexample rejects two outputs on that source net while accepting independent clock/data level outputs. The five genuine-LVC and nine genuine-AHC regressions pass after this narrow integration change; frozen live-study sources are unchanged.

TI SCES223U section5.5 actually guarantees **VOH≥VCC−0.1 V and VOL≤0.1 V at100 µA**, across both published temperature ranges including−40..125°C. Earlier VCC−0.2 allocation is conservative. At the level stage's minimum3.0 V supply this yields 0.65 V static high margin against ESP's0.75VCC threshold before load/local-reference differences. ESP's published50nA pin leakage maximum is under3.3V/25°C test conditions, so this does not by itself establish a full-temperature light-load guarantee. Explicitly disabling pulls removes a known resistive load; actual local supply/ground and pin-current qualification remain necessary.

The v7 population proof covers mixed-four and soleWiFi, bothWiFi/storage assignments. It does not cover soleGPU/IO/storage or every two/three-card insertion state. Actual physical candidate replay must discriminate those real M1 populations; no monotonic-loading assumption or future-six-card waiver follows from the selected-state study. `build/scratch-si/wifi-local-lvc-output-stage/compositional-window-audit.json` preserves a source-hash-bound historical input/output delay allocation. Its external remaining interval is not an ESP32-C3 published setup/hold guarantee or final physical cascade proof.


### Source-compatible Main shunt v3 replaces v2

The production-generator guard required thermal relief on R109.2. The isolated **v3** candidate corrects only that new pad's zone-connection policy and genuinely refills the board; it preserves every v2 track/via and the same two-barrel signal branch. Native DRC and source-generator geometry guards pass, with zero opens. The final replay target is `build/spi-main-shunt-v3-20260930/main.kicad_pcb`, SHA `c863db75538ed7542ec5266afcb312af8415a2ca7d2b9909bb31287e100a1642`.

A fresh matching ground mesh finds 7.028114/7.487401 mΩ at .1/.07 mm, 6.134% refinement change. Its retained upper value gives **20.46755894 mV** conditional DC shunt-reference difference at2.7336 A, higher than v2's15.321109 mV. `main-shunt-ground-bound.json` binds the actual v3 copper and solver. The prepared v3 MISO replay guards these hashes/allocation, preserves actual vias/stubs and independently varies barrel span±10%; it has not yet run. Neither v1 nor v2 values are silently reused as final evidence. The thermal-relief change does not establish package/contact/transient return bounds or shared hardware adoption.


SCEM270's actual temperature tuple is typ40/min100/max−40°C. The slow analog model is **100°C**, while the4.7ns fixture timing anchor is guaranteed through125°C. A125°C analog waveform is not manufactured by interpolation. For currentM1, local-junction qualification must support the100°C model envelope. SCES223U lists DCK θJA371°C/W and Cpd19pF typical at3.3V/25°C. At3MHz/3.6V the latter contributes about0.739mW internal switching;20–25pF output charging contributes roughly0.78–0.97mW. These indicate modest self-heating, but typical Cpd and package θJA are not a board-specific guaranteed temperature calculation. ICC10µA is tested at rail/GND inputs; ΔICC500µA is specified atVI=VCC−0.6. Independent rail/ground conditions can put a valid TTL-high input below that ΔICC test level. Whole external input-pin-current monitors do not bound internal supply current. Actual local board temperature and static/dynamic IDD therefore remain explicit first-article model-qualification measurements.


The actual-passive assembler now supports `signal_cap_scale`, `signal_cap_esr` and `signal_cap_esl`, with per-reference overrides such as `signal_cap_scale_C60`. Physical card-ground shunts use the card reference rather than global0. ESR/ESL defaultzero, scale defaults1, and invalid/nonfinite envelopes fail closed. These knobs declare component/ground-leg sensitivities; they do not invent supplier guarantees. A transient regression verifies the measured RC charging time, explicit series inductance and local reference; a counterexample rejects negative/nonfinite parameters. Together with the affected genuine-buffer discovery/fixture checks,16 targeted regressions pass after this integration change. The active v7 frozen copy remains unchanged and has ideal shunt capacitors; final actual local replay must include appropriate explicit RF sensitivity.


### Revised SCK5.6: terminal2048-case result

V7 genuinely completed **2048/2048 cases with zero failures in4149 seconds (69.15 minutes)**. Auditing every stored waveform finds maximum whole TTL-band transit10.280 ns (<12 ns), whole A-pin current2.0981 mA with all monitored samples finite, latest local A-valid crossing19.315 ns and latest RP SCK-fall-valid crossing23.005 ns. `build/scratch-si/wifi-local-lvc-input-stage-v7/summary.json` binds raw SHA `7317507747ad3ede68e400a0b91ef242e3c3be565010045e864081ce23603be8`, frozen inputs and captured unchanged runner. The revised5.6p clock candidate closes the four earlier4.7p strict failures in this covered matrix. Real future local branches, missing actual M1 insertion states, RF parasitics/ground qualification and manufacturing identities remain separate; this is not final fabrication approval.

The v3 Main shunt replay is now running256 bounded cases after that genuine terminal. It includes the actual source-compatible distributed branch, two real vias plus unused stubs, coherent ±10% barrel-span/height-capacitance sensitivity, opposed Mainshunt±20.46755894mV and cardshunt±35.651mV references over common±150mV driver-offset sensitivity. A terminal result has not yet been produced.

TI SCES223U section5.1 distinguishes **Y high-impedance/power-off −0.5..6.5 V** from **driven Y −0.5..VCC+0.5 V**. The actual disabled-output probe now uses a separate Y-Z identity; active output, FPGA and input limits remain unchanged. A regression confirms4.2V atVCC3.0 is permitted for the disabled state but fails the driven-state limit, while6.6V still fails disabled Y. The eight affected genuineLVC/physical-cap regressions pass after this state-specific primary-rating correction. No negative-output current exception is inferred without a complete output-current monitor.


### Mainv3 MISO: terminal256-case physical development result

The source-compatible v3 branch study genuinely completed **256 cases in1326 seconds (22.1 minutes)** with zero voltage-stress/simulation failures. FPGA maximum3.6026 V exceeds3.6 for only0.210 ns, within the unchanged published3.66V/1.6ns allowance; minimum−0.1491 V. Maximum fixture-anchored buffer-plus-line validity is31.1794 ns. Actual v3 branch/two-via topology and independent±10% barrel L/C sensitivity are included. Raw SHA `47e28876cda2dc7181bc71c5845e612330afb01e76481e6a5cb303d6eb0dfbe8` and all proof/solver-input hashes are in `build/scratch-si/miso-main-pulldown-physical-v3`.

Combining terminal v7's23.005ns RP falling-clock validity and actual RP-to-TI A-route5.7523ns with existing3ns clock insertion,5.25ns RP pad input, six8ns PIO cycles,7.1ns RP pad output and0.9ns FPGA pad/setup reserves leaves **73.6594ns** for buffer+line at3MHz. The192 covered RP-source cases all pass that conditional sampled-data budget, with about42.48ns worst margin. Raw uniform early-data edge diagnostics are preserved on all256 cases. These budgets still use hypothetical filters at original pad nodes, so final real-filter replay is required. The64 WiFi-source cases have valid modeled line/stress evidence but **no invented ESP controller-response guarantee**. `conditional-rp-sampling.json` and `summary.json` record this distinction.

The next bounded stage uses the native DRC/identity-qualified physical storage filters with actual distributed postR/cap/OE branches, soleJ11/J14/J16 source/corner/tolerance/RF sensitivities. Its actualPCB topology is explicitly overlaid on authentic original circuit metadata pending the isolated source generator's true export. This is development evidence, not schematic parity or a manufacturing receipt. No generic second RC is inserted on an already physical filter.

### Actual RP physical replay: exact pad-width contact repair (11:08)

The first true-export storage replay terminated before simulating any cases:
`/CS_n` extraction declared C63.1→R64.1 open. The frozen PCB has native
zero-open DRC and independent exact native connectivity proves that path.
R64.1 is centred at (35.1875,-16.54); a 0.15 mm track starts at
(35.45,-16.3). Its copper width intersects the pad, although its centreline
endpoint is outside the pad. The previous distributed extractor handled only
centreline/end-inside-pad contacts.

`slowbus_route.py` now requires native zero-clearance pad/track shape
intersection for this contact and retains a finite pad-centre→track-centreline
stub using the connecting track width. This is a narrow-stub RLGC modelling
approximation; it does not claim a field solution of the whole finite pad.
Original track lengths and actual barrel graph remain present; no clearance
or missing-route gate was weakened. Three focused regressions pass: actual
width contact retains both finite stubs, a 0.1 µm true copper gap stays open,
and the existing centred path keeps its original length.

The failed v2 extraction is preserved with no computed results. The new
72-case actual-storage v3 study freezes the repaired extractor, both final
true source-generator circuit exports and their artifact/qualification
indexes. It is development evidence only, and actual clock/sample timing
results are pending. Historical completed studies retain their original
frozen solver sources and are not silently relabelled as using this repair.

The deeper graph audit corrected the initial location diagnosis: R64's pad
contact was already joined. The actual remaining open is the In2 track body
at y=-14.002 touching the 0.6 mm via at (23.95,-13.7). Its centreline misses
the 0.3 mm annulus radius by 0.002 mm, while the 0.15 mm track's copper
width intersects the real annulus. The repair now covers both pad and via
shapes and explicitly retains the 0.302 mm radial conductor stub. Independent
native connectivity agrees. Five regressions pass, including finite-width
via contact and a 0.1 µm actual via/track gap that remains open. V3 preparation
also stopped before cases; v4 freezes this complete repair and final true
exports. No claim rests on either incomplete preparation.

The subsequent extraction also identified a real finite-width MOSI track/body
contact. Exact native contact handling now covers pad, via and track pairs:
real track pieces split at their nearest centreline contact points, and the
remaining finite bridge uses the narrower connecting trace width. A true
centreline intersection remains a zero-length join. Seven focused tests pass,
including two width-only T-join/gap counterexamples. All six actual storage
raw/filtered signal graphs pass a bounded topology-only extraction before
launching v5's real field/RLGC computation. This preflight used mocked field
constants exclusively to check graph closure, and is not voltage evidence.

### First actual storage electrical replay, terminal

`rp-actual-storage-discriminator-v5` completed 72/72 cases in 337 seconds
of simulation, after the actual field/topology preparation. Mandatory strict
clock/control failures remain: SCK 5/24 and CS 21/24. RP MOSI has 0/24
required failures after applying the actual routed-SCK sampled setup criterion;
its original early-edge diagnostics remain available. Raw SHA256:
`b0798c4fe7477fdf17a705c8c745efc922ccb881ae965cc8a426289688277e0d`.

Whole-edge, clipped-band RP diagnostics include late re-entry: maxima are
40.00 mV SCK, 16.04 mV CS and 111.28 mV MOSI, with zero full valid-band
recrossing. They do not silently replace the uniform gate. Manufacturer scope
is the nominal 3.3 V class supply with default voltage select, enabled Schmitt
and −40..85 °C case temperature. The [RP2040 primary datasheet](https://datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf)
§2.9.1 describes nominal supply classes; §5.5.3 states characterization across
specified PVT; Table625 provides minimum hysteresis; Table634 gives allowed
supply range. Pinned SDK `gpio_init`/`gpio_set_function` preserve the Schmitt
reset setting, and the current RP firmware does not disable it. This supports
receiver-specific qualification under that scope, rather than requiring an
exact 3.300000 V rail. Voltage stress and actual clock timing remain separate.

The bounded 48-case bigger-cap study (C60/C62=22p, C63=100p, unchanged
actual copper) also completed: SCK 4/24 fail, CS 24/24 fail, and 15 cases
violate genuine TI's recommended whole-band input rate. Bigger caps are
rejected. TI OE has no Schmitt guarantee and retains its asynchronous-input
requirements. The next isolated hypothesis inserts 100/220 Ω locally before
OE and relocates a 10p capacitor to the OE side; its old capacitor copper
branch remains as an explicit open stub. This is a candidate adjacency model,
not a physically routed or adopted circuit.

### Scoped RP input model correction and minimal OE repair

The current compiled RP firmware now explicitly enables hysteresis on the
three SPI inputs and always asserts default voltage-select mode. Root's
`build/rp-spi-schmitt-enabled-20260930/qualification.json` binds five genuine
compiled targets and their disassembly evidence. SI's scoped helper binds
application source hashes, verifies U1.4/GPIO2 and U1.7/GPIO5 identities,
requires nominal 3.3 V/default mode and rated rail/case-temperature scope,
and measures the largest adverse excursion over the entire edge period.
Absent/disabled state, wrong pin/mode, out-of-scope rail or temperature,
≥0.2 V adverse excursion, missing complete transition or full valid-band
recross fail. Original 1 mV diagnostics, voltage stress and timing remain.
Five focused regressions pass, including accumulated reversals, exact 0.2 V
margin exhaustion, late full recross, and early overvoltage.

Separate raw-wave reclassification artifacts bind this classifier and the
compiled state proof without altering the frozen analog results. Actual
storage72 now has zero required SCK/MOSI failures; 18/24 CS cases still fail
at genuine non-Schmitt TI OE. The new local OE hypothesis48 has zero
required failures with the corrected RP receiver qualification. Both 100 Ω
and 220 Ω plus 10p pass all 24 TI cases: 220 Ω gives maximum whole-band
7.160 ns, maximum final arrival15.505 ns and maximum full-pin current
1.271 mA. Prefer the already selected 220 Ω supplier identity.

Canonical physical proposal is R65.1 raw `/CS_n` → R65.2 `/CS_OE`, with
U4.1 and C63.1 on `/CS_OE`; C63 becomes10p to GND. Existing RP filters stay
220 Ω/10p and main routes stay unchanged. The old C63 raw signal copper
was retained as an explicit stub in the adjacency hypothesis. Actual new
R65/C63 leads must be extracted and replayed after native routing proof;
no arbitrary maximum route length has been treated as established. Source
and component/assembly gates remain separate.

### Explicit capacitor return model, bounded sensitivity

The capacitor helper now accepts per-kind/ref return resistance and excess
return inductance separately from body ESR/ESL. It puts these elements in
the capacitor ground leg and records full branch current plus local AC return
voltage; an optional zero-volt current sensor does not change the circuit.
Default zero preserves earlier solver inputs. A constant ground offset is not
used as a substitute for capacitor-current return bounce. Four affected tests
pass, including measured transient `Vreturn=R*I`, added inductive bounce,
independent per-kind/ref bounds and invalid-value rejection.

Existing RF1's 2nH is a declared capacitor-body envelope. Adding a separate
2nH excess return gives4nH total; this is an engineering sensitivity, not a
physical inductance guarantee inferred from the DC resistor mesh. The signal
TL field model already includes its signal/plane loop inductance, so an extra
return parameter must not be described as a second complete plane loop.
Actual capacitor-to-receiver self resistances support a conditional resistive
path model, while package/contact/plane inductance and unrelated loads'
time-varying ground remain separate qualification gaps.

The preferred220/10p OE return sensitivity48 uses the old actual-storage
self resistances only as research inputs. Its C63 resistance7.166883mΩ does
not bind root's newly relocated C63; that new physical ground leg requires
fresh extraction. V1 setup stopped before extraction because the historical
source template had no firmware subtree; v2 freezes the current full RP
firmware source and genuine compiled-state proof before solving.

V2 genuinely completed 48/48 cases with zero required failures in182s.
The maximum recorded capacitor branch current was9.0465mA and maximum
local return excursion41.3024mV (MCU CS C62, excess return2nH). TI OE's
worst whole-band transit remained7.160ns and valid arrival15.505ns. The
immutable results hash is
`3b996fac19ede5b0adaaffe029c8cba8f3d32e52a25d4d76a582de5a3f782b55`;
summary and current/return probes are retained under
`build/scratch-si/rp-actual-storage-local-oe-return-discriminator-v2`.
This establishes sensitivity within those declared inputs, not a guaranteed
bound on unrelated-load ground bounce or the newly relocated physical C63.

### Actual isolated OE routes

The separate GPU/IO owner completed48/48 genuine new-route cases with zero
required failures under the same limited paired RF scope. Native boards
`be4f8cc4…` and `35d2072d…` contain the actual R65 and C63 branches;
no adjacency hypothesis was added over their physical network. The source,
true circuit exports, NPZ and compiled-state proof are frozen under
`build/scratch-si/rp-actual-new-oe-gpu-io-discriminator-v2`.
A matching storage/eInk actual-route48-case study is running from true
frozen source-generator exports and native boards `d8e544b0…` and
`655703c6…`. This baseline extracts all real branches, including via barrels.
Fresh moved-C63 ground self resistance is pending and is not substituted
with the prior candidate's resistance. These paired-corner sole-card screens
remain narrower than the final independent/population qualification.

The matching actual storage/eInk study genuinely completed48/48 cases,
zero required failures, in173s solverphase. Worst TI whole-band transit was
7.255ns and valid arrival15.665ns; result SHA256
`1fe90b348f594b1d034ecc6d0cd697e2f9674f1c70616e0eab5b78f71382d1a6`.
Together with the GPU/IO owner's separate48, this gives96 actual OE screens
across four native new-route types, retaining the limited paired RF scope.

A second immutable768-case actual OE screen genuinely completed with zero
required failures in2939 seconds under
`build/scratch-si/rp-actual-new-oe-fourtypes-opposed-stage2-v1`.
Its `inputs.json` explicitly records all six slots, both source corners,
opposed package/Cin pairs(0/1 and1/0), both line and connector endpoints,
and opposed R/C tolerance. Body ESR/ESL remains paired with tolerance here;
this stage selects waveform-worst points for separate independent return
and body tests. Sole-card coverage does not qualify untested mixed loads,
complementary coherent package/Cin corners, unknown unrelated-load ground
transients, or the unfinished actual WiFi level-stage geometry. All original
release obligations remain open until their exact coverage is supplied.
The SI process uses `/usr/bin/python`, NumPy2.5.3 and ngspice; SciPy is not
used by this runner.

### Main v3 control-field binding

A genuine old/new native field audit completed16 control graphs in57s,
using the frozen stage2 solver and copied true circuit exports. All SCK and
MOSI graphs and ten CS graphs are exactly equal, including field-derived
reference cross-sections, tracks, pads and barrels. All16 separate aggressor
bounds are also equal. Two CS4 graphs differ despite identical conductor
geometry. A0.975mm source segment loses a distant back reference with
negligible numerical impedance change; a0.5336mm front bus segment changes
its modeled reference from45.887Ω to127.959Ω, and another0.7526mm segment
gets a smaller coplanar-gap change. Unchanged tracks alone therefore do not
establish identical solver inputs after refilling.

Native snapshots, complete16 comparison results and detailed actual field
changes are frozen under
`build/scratch-si/main-v3-control-field-equivalence-v1`.
The changed CS4 slice completed128 actualMainv3 cases with zero required
failures in416 seconds under
`build/scratch-si/rp-actual-new-oe-mainv3-cs4-opposed-recheck-v1`, using
native68Ω CS resistors scaled only±3% and true four-card OE exports.
No new physical repair is inferred from the field difference itself.

Separately, each independent64 body/return sensitivity completed with zero
required failures: GPU/IO use the earlier Main reference; storage/eInk use
actualMainv3. They expand body ESR/ESL/excess-returnL independently at
selected baseline extrema and use newly validated per-cap ground self-R.
GPU/IO's maximum RP whole-band adverse excursion is154.700mV, and local
return maximum48.469mV; root storage/eInk maximum RP adverse41.0503mV,
local return40.5922mV. These remain declared engineering return-L bounds,
not guarantees on shared-package or unrelated-load ground transients. Later
stage2 extrema must be compared against their selection before claiming
final sensitivity coverage.


### Independent receiver rails and local-ground audit correction

The production DCK package helper already applies the local-ground gauge
exactly once. An initial audit claim that TI receiver clamps ignored the
card-ground offset was incorrect and is withdrawn. Historical control
studies retain their declared local-ground sensitivity. Genuine SCEM270
input, OE and output models have no PowerClamp table; assigning passive TI
receivers their fixed genuine-corner local rail therefore changes rail
metadata without changing their clamp/Ccomp equations.

The corrected assembly also assigns the Main FPGA receiver bank and its
R107 pullup their own genuine Main-rail corner, independently of a TI card
MISO driver's3.0/3.6V corner. It permits independently selected genuine TI
receiver corners without rescaling vendor tables. Five new regressions
verify one local-ground shift, genuine clamp common-mode equivalence,
independent Main pullup/bank rails, unchanged overvoltage rejection and
invalid-corner rejection. Together with the affected current, slew,
Schmitt, sampled-data and passive-model tests,53 tests passed in1.566s.
Bounded corrected MISO replay remains necessary; this correction supplies
no new ground-envelope or manufacturing approval.

Terminal raw-result SHA256: the768-case study is
`61c31ff456a31a008f309ee51bcf1c59564be3d0475c1c82ed9723e2bd5e0b9d`;
the actualMainv3 CS4 recheck is
`cd79e7dd09a6877cbfb724f99417969d97a24d47440759d20f6b33647eb865fd`.
The latter's maximum TI whole-band transit is7.810ns and RP whole-band
adverse excursion47.741mV. Neither paired-body study covers every independent
package/body/return combination or physical shared-ground transient.


A corrected independent-Main-bank MISO study is now running under
`build/scratch-si/miso-actual-mainbank-independent-discriminator-v1`.
It freezes the actual Mainv3 and four RP new-OE PCB/netlist pairs, without
circuit/value overlays. Its128 cases cover sole GPU1/IO2/storage4/eInk6,
source min/max independently of Main bank min/max, both driver-ground signs
±150mV, both driver/shunt differential signs±35.651mV, and both genuine DCK
package endpoints. FPGA/package Cin is paired with source, line0.9 and
connector1 are fixed, and Main shunt ground is opposed with source by its
conditional20.4676mV DC allowance. This tests the rail correction and selected
opposed grounds; mixed populations, allslots, independent barrel/body/return
and clock/local-A sampling deadlines remain separate obligations. Early MISO
uniform-edge diagnostics are retained and cannot establish a sampled timing
pass without those deadlines. No guarantee of the assumed ground envelopes
is supplied.


The final source-compatible WiFi physical candidate is
`wifi-final-v127.kicad_pcb`, SHA
`617df7e417f7396cf9207b7a64ee7b2dda07650ee74534b6f8d2dad72cb4c252`.
Normal generator/route-seed guard and genuine native schematic parity pass.
Its actual C63/C69 relocation and longer input/output/cap branches require
new electrical replay. The first materialized runner has56 cases:32 actual
mixed-four CS-to-local-input cases and24 separate genuine TI Y-to-ESP cases.
An estimated216-case description was incorrect. SCK/MOSI were omitted by a
sole-label selector before materialization; this omission is explicit in
its manifest and requires a separate corrected64-case actual SCK/MOSI run.
The56 cases do not establish SCK/MOSI qualification or complete SPI timing.
Both runners use true native/export circuit geometry with no ideal-node or
hypothetical passive overlay. Physical capacitor return-L, independent
body/tolerance coverage and full sampling/cascade timing remain obligations.


The corrected Main-bank MISO study genuinely completed128 cases in654s.
Unchanged voltage-stress checks have zero failures: maximum FPGA3.6016V,
0.220ns above3.6V within the existing3.66V/1.6ns AC allowance, and minimum
−0.1732V. Maximum model-fixture-anchored buffer-plus-line delay is23.7538ns.
All128 retain early uniform-edge data diagnostics; no standalone sampling
pass is asserted. Raw SHA
`5fed2d74a3d298cedda3bd3891ca750a2c17cbc7aa6051ced57aacde12f83bc7`.

The actual WiFi56-case run is terminal in149s. Twenty of32 CS-input cases
pass;12 fail only the external raw U3OE strict monotonic criterion, with
maximum55.8mV reversal. Fourteen of24 genuine Y-to-ESP cases pass. Fast CS
outputs have up to32.2mV early reversal, SCK has2.7–2.8mV reversal in two
high-Cin fast cases, and MOSI has up to181.1mV early reversal plus142mV band
ringback. Voltage stress and input-rate/current checks have zero failures
in this limited run. MOSI requires an actual stable sampling/setup/hold
analysis; its early-data diagnostics alone do not require clock-like
monotonicity. SCK and CS retain the unchanged strict receiver rule.
Corrected64-case actual SCK/MOSI Main-to-local-A input replay and64-case
hypothetical adjacent U3OE220Ω/10p repair are running separately. The
latter removes only the original C69 body, retaining its real copper as an
open stub; it supplies no physical adjacency or manufacturing proof.

The physical owner also found a real normal-builder via-in-pad rejection
at the relocated C69. Native DRC and source/seed equality alone did not
cover that fabrication check. V127 is preserved as development geometry;
legal local via placement and any demonstrated OE repair must be bound to
a new native/source-compatible candidate and electrically replayed.

## Latest actual WiFi and normal pipeline binding checkpoint

The separate actual SCK/MOSI input run completed 64 cases in 505 seconds.
All TI receiver voltage, clamp-current, input-transition, and strict edge
checks pass. Twelve MOSI cases retain early RP edge diagnostics; applying
the production sampled-data criterion with the corresponding actual SCK
waveforms leaves zero sampling failures. Maximum TI valid-band transit is
11.000 ns, below the 12 ns requirement. This remains a bounded input study;
the full cascade and ESP setup/hold obligations are separate.

ESP valid-input thresholds now use the published local-rail fractions:
VIH = 0.75 VDD and VIL = 0.25 VDD. Explicit local Y-to-ESP cases bind their
coherent genuine TI supply corner without rescaling vendor tables. Fixed
nominal diagnostics remain available. The local buffer and ESP share a
rail in these cases; actual differential rail and ground drops require
separate bounds. The correction and existing receiver regressions pass
56 tests. Reviewing the original 24 endpoint output waveforms with the
correct fractional thresholds leaves seven strict diagnostic failures:
two CS, one SCK, and four early MOSI cases. Genuine nominal 3.3 V cases
are evaluated separately, rather than inferred by interpolation.

The adjacent raw OE 220 ohm / 10 pF hypothesis completed 64 cases without
failures. The physical owner then supplied actual v138 geometry with a
legal C69 launch and a separate R68, preserving the real, nonzero OE and
capacitor branches. That actual native v138 replay also completed all
64 cases without failures in 263 seconds. Its maximum TI whole-band
transition rate is 5.3833 ns/V. Evidence is in
`build/scratch-si/wifi-actual-native-oe138-discriminator-v1/terminal-summary.json`;
raw result SHA-256 is
`abeaba461e1154449482cbfb81c7f296e54f189bd6d9edc644e6e76d334d5940`.
The scope contains independent Main/TI corners, opposed package/Cin,
line/contact endpoints and paired body/R/C extremes. It does not prove
all populations, independent return parasitics, or a guaranteed ground
envelope.

Output damping remains unresolved. R270 and C22 value-only hypotheses
both failed six of 16 cases. Explicit 10 ohm capacitor-branch resistance
passed all 64 SCK cases but failed eight of 64 CS cases at the high
intrinsic ESR endpoint. These are rejected development hypotheses, not
adopted component values. A parent-owned 6.8 ohm branch discriminator
adds independent resistor tolerance to test the physically motivated
lower total-resistance window. No body ESR is invented as a component
property.

Normal pipeline serialization adds legitimate ground stitches. Exact
control/MISO ladder comparison closes 25 of 27 graphs after harmless
edge-order canonicalization. The eInk MOSI difference is an undirected segment orientation;
its literal reciprocal ladder proof now passes exactly, closing 26 of 27
graphs. Evidence is `build/scratch-si/eink-normal-round2-field-equivalence-v1/undirected-mosi-equivalence-proof.json`. Main CS6 has a different numerical section partition
from mirrored coplanar field-key ordering, so prior analog results are
not automatically reused. An actual normal Main CS6 128-case replay,
followed by a selected time-step convergence comparison, is running.
No physical coordinate or electrical acceptance tolerance was widened.

The actual normal Main CS6 replay is now terminal: all 128 cases pass in
559 solver seconds. Maximum TI band rate is 6.65 ns/V; maximum RP
whole-period adverse excursion is 56.4565 mV; maximum input peak is
3.3312 V. Raw result SHA-256 is
`e852ba4389776c711eb7a7cc04d6af4cb63f09e9fe403b1117cb5b58d0cf54b1`.
Selected worst rate, adverse-excursion and peak cases are undergoing the
unchanged production half-section/half-time-step convergence check.
The eInk reciprocal MOSI ladder proof already passes exact equality.

The 6.8 ohm output capacitor-branch discriminator also fails (13 of 256
cases); it is not adopted. The next bounded hypothesis changes only the
existing WiFi CS/SCK output series resistors to 100 ohm, retaining native
10 pF capacitors and adding no capacitor-branch resistor. Actual extracted
trace impedances around 94–155 ohm motivate this termination test. The
parent owns its execution against genuine normal-generated v138 geometry,
including genuine min/max sources and independent resistor/capacitor/body
endpoints. A passing narrow screen would still require actual physical
value/source binding, nominal cases, return parasitics and combined timing.

Normal Main CS6 convergence is terminal and passes. Two distinct refined
cases cover all three selected extrema because the RP adverse-excursion
case also has the largest peak. Maximum refined peak difference is
0.1 mV; maximum valid-arrival difference is 7.5 ps; verdicts remain
identical. The unchanged production bounds are 30 mV and 50 ps.
Evidence: `build/scratch-si/rp-actual-normal-main-cs6-convergence-v1/qualification.json`
and `selection-audit.json`, with genuine refined waveforms retained.

The 100 ohm existing-output hypothesis is terminal and rejected: 18 of
256 cases fail unchanged strict edge checks (eight CS and ten SCK).
The worst CS waveform has a smooth driver-die transition while the ESP
receiver exhibits roughly 1 ns ringing, including an 80.2 mV adverse
excursion. This implicates the distributed output/package/capacitor
network; correlation alone does not prove which parasitic dominates.
Completed raw waveforms and a plot are preserved under
`build/scratch-si/wifi-output-launch-diagnosis-20260930`.

Exact extracted contact paths show a material layout difference between
CS and SCK. CS U4.4 to R63.1 is 45.703 mm including six modeled vertical
barrel edges; its total horizontal Y-net copper is 37.525 mm. The paths
from R63.2 to the ESP and C61 are 11.150 and 14.556 mm. These metrics use
finite-pad ideal joins and exclude pad-interior metal length. SCK U5.4 to
R65.1 is already 0.500 mm with no barrel; post-resistor paths to the ESP
and C64 are 8.335 and 4.560 mm. Relocating R65 is therefore not justified
by a long source launch.

A parent-owned CS-only hypothesis retains 220 ohm and moves R63 to ideal
source adjacency while retaining all original Y/output/cap traces and an
explicit near-zero jumper at the old resistor position. It is a bounded
128-case discriminator, requiring real placement and routing proof before
any adoption. A separate native SCK 128-case study tests the original
220 ohm/10 pF topology with independent body/tolerance endpoints. The
previous 6.8 ohm capacitor-branch study had zero SCK failures in its 128
fast SCK cases; all 13 failures were CS. That provides a separate
candidate damping direction if the native SCK study confirms a repair
is needed, without moving its already adjacent source resistor.

The source-adjacent CS-only hypothesis fails 12 of 128 cases; the native
SCK-only independent baseline fails 15 of 128. All failures occur at the
fast genuine source corner with low intrinsic capacitor ESR. Relocation
alone is rejected. The physically motivated combined hypothesis then
passes all 256 fast cases: retain 220 ohm, relocate only CS R63 to its
source, and add explicit 10 ohm resistance in each CS/SCK capacitor
branch. New resistor tolerance is independent of capacitor and output
resistor tolerances. Matched before/after waveforms show the receiver
ripple damping, rather than an assumed body ESR. Selected production
convergence also passes (maximum arrival change 7.5 ps).

That first fast pass used cap-branch R tolerance of ±3%. Exact supplier
identity C25077, UNI-ROYAL 0402WGF100JTCE, specifies 1% initial tolerance
and 200 ppm/C TCR. A conservative full −55..155 C allocation therefore
requires ±4%. The parent owns a genuine min/typ 512-case follow-up and
fast 256-case ±4% complement; their running state is not a pass claim.
The new native component placement, source lead and return geometry must
be independently replayed after the physical owner freezes them.

The separate local Y-output studies schedule isolated edges at a
333.33 ns rise-to-fall separation. This is an edge-quality/stress screen,
not a complete 3 MHz SCK duty-cycle or cascade qualification. Final
selected actual SCK waveforms need an eight-clock byte at 3 MHz with
166.67 ns half periods, receiver-valid pulse widths and actual setup/hold
checks. CS uses the separately proved host-held assertion/release
sequence. No unpublished ESP slave-response or interrupt latency maximum
is inferred.

Storage's mechanically necessary R65 relocation has its own frozen
native/source export and a running 192-case affected CS/OE study covering
all six slots. Prior storage geometry is not silently reused. Matching
final normal generated geometry and capacitor returns remain required.

The affected storage relocation study is now terminal: 192/192 cases pass
in 745 solver seconds, with maximum TI transition rate 6.55 ns/V and
RP whole-period adverse excursion 59.32249 mV. Raw result SHA-256 is
`499695148ebabd5b538186c8016fd20e30c17abe6c7ac643e52ace1e6b4672ed`.
The final normal builder/model bridge and new return scope remain separate.

## Latest terminal follow-up and true-native preparation

The genuine MIN/TYP 512 and FAST ±4% 256 combined-hypothesis studies are now terminal: all 768 cases pass. Parent aggregate `build/wifi-combined-damping-viability-20260930/qualification.json` verifies the declared independent Cartesian axes and raw hashes. These are still isolated edge studies, not final native geometry or complete 3 MHz cascade qualification.

Storage's final normal board now has exact tracks/pads/raw-fill identity to the mechanically repaired candidate, with a genuine new matched return/ground qualification: `build/spi-development-storage-r65-v4-20260930/generated-storage-physical-identity.json` and `build/storage-r65-generated-ground-20260930/qualification.json`. This legitimately bridges the 192 affected CS/OE cases' geometry; package/contact/transient current bounds remain separate.

A fail-closed true-native 24-case eight-clock 3 MHz SCK preparation is available in `build/scratch-si/wifi-native-sck-eight-pulse-stage1-v1.py`. It requires exact PCB/netlist hashes and real R69/R70 private cap nodes, applies ±4% to the traversed resistor without adding that value to capacitor ESR, and keeps resistor body ESL distinct from cap body ESL and routed leads. It has not been executed before the new native source-compatible snapshot exists. Its fixed body/ground choices are explicitly a bounded stage, not universal coverage. Production SI now supports explicit per-physical-resistor scale and separate resistor-body ESL, with three focused regressions passing; default zero-ESL resistor emission is preserved.

The exact C3 source/timing audit is in `doc/m1-esp32c3-spi-timing-audit-2026-09-30.md`. It keeps numerical ESP pad timing and variable-tail DMA behavior unresolved rather than borrowing ESP32-only tables or changing the protocol.

The final native source-compatible damping WiFi board is now frozen (`fa477e83…`), with genuine R69/R70 private capacitor nodes. Parent actual-native SCK eight-pulse study is terminal 24/24 PASS; raw result SHA `1e85d2c5daf34150dc0fc1df6ac60bda1dddada659e63b1c238c8b5c49f97d21`. All 384 half-periods retain the unchanged strict receiver/stress verdict. Postprocessing actual adaptive ngspice timestamps and interpolated fractional-rail threshold crossings gives minimum receiver-valid duration 155.895797 ns. This supersedes the original approximate sample-count-times-median duration, whose maximum correction was 0.217266 ns. Original data and summary remain immutable; `pulse-width-time-integrated-v1.json` stores the honest correction. No published ESP minimum pulse width or full cascade timing is inferred.

The actual-native 192-case isolated CS/SCK MIN/TYP/MAX body/return screen is running under parent ownership, with physical resistor ±4%, independent new resistor body ESL 0/2 nH, cap-body RF endpoints and explicit extra return R0.1 ohm/L2 nH sensitivity. Those return numbers are engineering screen inputs, not guaranteed connector/package/plane limits. Fresh actual matched return bounds and cascaded signal timing remain required.


## Independent reference/body counterexamples and selected follow-up

The actual-native 192-case body screen is terminal 192/192 PASS, but its paired capacitor-body axes do not cover every independent body/return combination. The subsequent actual-normal differential-reference screen fails 4/96 cases, all SCK. An exact matched independent 128-case baseline at native R70=10 ohm fails 8/128 with low intrinsic capacitor ESR and all three inductances at 2 nH. The corresponding R70=22 ohm hypothesis fails 8/128 at high intrinsic ESR and the same inductance endpoints. These strict failures are retained; neither value has final independent coverage or adoption approval. Raw summaries remain under `build/scratch-si/wifi-normal-output-differential-reference96-run-v1`, `wifi-normal-sck-r70-10-independent128-baseline-run-v1`, and `wifi-normal-sck-r70-22-independent128-run-v1`.

Matched waveform extrema identify a finite damping tradeoff. At low ESR, the secondary slope changes from +0.12043 V/ns at 9.6 ohm to negative at 21.34 ohm. At high ESR, the first local dip changes from 2.741802 V to 2.652784 V, crossing the actual 2.685 V upper threshold. External-resistor secants predict a useful interval of approximately 12.06 to 17.09 ohm. This predicts a candidate; it is not interpolation of vendor corners or proof that all resistor values inside that interval pass. Evidence is `build/wifi-damping-tradeoff-20260930/extrema-window-diagnosis.json` and the matched falling-transition plots.

A 16-case discriminator selects R70=15 ohm with independent ±3% tolerance, both intrinsic ESR endpoints, both DCK package choices and both differential ground polarities, fixing all three inductances to the actual failing 2 nH endpoints. The scalar changes only the physically traversed R70; all actual routed branches remain. It keeps the genuine fast vendor waveform and strict receiver criteria. Prepared runner `build/scratch-si/wifi-normal-sck-r70-15-extrema-selected16-v1.py` is not a full corner or 3 MHz pulse proof. Exact official supplier identity C25083 is UNI-ROYAL 0402WGF150JTCE, 15 ohm, 0402, 1%, 100 ppm/C; CAD, live JLC stock and exact manufacturer approval sheet remain separate procurement checks. If this screen passes, full independent body endpoints, complementary genuine corners and actual eight-clock pulse/cascade qualification remain required.

The original mandatory finite shared-SPI catalogue is running independently with all 5,760 production cases: SCK 352, MOSI 352, CS 960, MISO 3,840 and RP-pad-to-buffer input 256. Exact production emitted-deck comparison passes all 5,760 cases for typed R70=22 and the optional R65=100/R70=22 value changes: `build/scratch-si/full-shared-spi-emitted-output-equivalence-v1/qualification.json`. That proves these buffered-output resistor values are not dependencies of this catalogue's current model. It does not prove physical shared-return/current independence, nor permit rebinding to changed actual boards without their source, field and geometry bridge. The catalogue covers its original finite fixtures; it does not substitute for every legal M1 population and independent sensitivity axis.


The selected 15 ohm discriminator is now terminal 16/16 PASS, with raw SHA `02eb4b308715f224a0d8ab50f23a8f4958bb43a8e7333d656c60c3231c4c1208`. This validates the predicted interval at the tested failing points only. The independent 128-case body follow-up is prepared separately. A true 3 MHz eight-clock 384-case preparation covers all genuine corners, package/Cin and independent R/C/reference/ESR choices at the three high-inductance endpoints, calculating receiver-valid durations from actual adaptive timestamps. A separate optional 6,144-case preparation declares independent CS10/SCK15 endpoints across all those corners and all three inductance endpoints. Neither prepared study is a pass claim or a newly invented mandatory release requirement; their actual scope, runtime and need for additional cases must remain explicit. No source, resistor value or native board has been adopted from the selected 16 results.


Parent reports the selected R70=15 ohm independent body matrix terminal 128/128 PASS; its raw hash audit is pending at this checkpoint. The actual 3 MHz 384-case pulse study and combined CS10/SCK15 6,144-case declared engineering endpoint study are now running under parent ownership. These are model qualification expansions with conditional reference/inductance inputs, not guaranteed ground envelopes or universal legal-population claims. The high-ESR first local dip in the selected 16 stays at least 11.959 mV above the actual upper threshold; four selected half-section/half-timestep production convergence checks are prepared to verify verdict stability near that band. Source/native value adoption remains held for final normal geometry/export and completed qualifying evidence.

Fresh matched WiFi return coefficients now have complete existing-criterion qualification at `build/wifi-output-damping-ground-v7-20260930/qualification-with-affine.json`, including tiny remote transfer terms evaluated with an isolated exact affine representation on the same grids. Original raw outputs remain preserved. Retained C61/C64 self resistance is 5.1350/4.0284 mOhm, matching the differential studies. These are pure copper coefficients parameterized by actual currents; no package, connector, return-inductance or current guarantee follows from convergence.


## Cascade preparation and newly expanded counterexamples

The true 3 MHz R70=15 output study exposes new low-C failures: at C64=9 pF, low source/output-resistor tolerance, high intrinsic ESR and the three 2 nH endpoints, the first falling-edge dip reaches 2.681051 V, 3.949 mV below the actual 2.685 V upper threshold, then rebounds by 11.6 mV. Earlier high-C selected16/independent128 passes therefore do not qualify the expanded component envelope. Both packages repeat the failure on all eight pulses. The selected joint hypothesis raises the existing adjacent output R65 from 220 to 270 ohm while retaining R70=15, to reduce early discharge/reflection and lift that dip. Its prepared 128 fast eight-clock cases independently cover Cin/C/R65/R70/reference/ESR endpoints; no physical adoption or threshold change follows from this selection.

The full original catalogue also exposes a distinct upstream failure: six homogeneous WiFi cards produce Main-to-U5.A threshold-band reversals up to 27.2 mV at the fast source corner. This remains a required legacy finite fixture even though six WiFi cards are not a legal current M1 population. Its slow-source worst whole TTL-band transit is 7.88 ns, leaving 4.12 ns to the unchanged 12 ns recommended transition gate. A bounded existing Main R36=68 ohm value trial covers all32 original source/load axes, two resistor endpoints and three populations (legacy six WiFi and two actual M1 mixed maps), 192 cases. Those two M1 maps do not qualify all1,861 maps. The proposed change preserves Main routing and does not alter R70 or delete the legacy fixture.

The [TI SCES223U datasheet](https://www.ti.com/lit/ds/symlink/sn74lvc1g125.pdf), Table5.8/Figure6-2, gives 1..4.7 ns propagation at 3.3±0.3 V and −40..125 C with 50 pF/500 ohm, VI=3 V, VM=1.5 V and input tr/tf≤2.5 ns. The separate recommended input rate is 10 ns/V over the TTL transition. Passing a 12 ns whole .8..2 V transit does not establish that faster propagation fixture condition. IBIS supplies input loading/clamps and output Ku/V-T tables, not an internal A-to-Y transfer model. Existing fixture-anchored sampled MISO timing remains model qualification and must not be described as a datasheet-only guarantee for every actual input slew and load. ESP numerical setup/hold/tCO remains the separate primary-source gap documented in the C3 audit.

`hw/si/spi_cascade.py` and six regressions preserve input re-entry, distinguish operating slew from fast fixture observations, retain actual output-network excess delay, and require received CS lead/hold strictly greater than half a clock. The fail-closed runnable observer and 180-case simultaneous phase/history preparation are under `build/spi-cascade-preparation-20260930`. Three real Main sources plus three selected WiFi Y sources traverse actual nets for an eight-clock byte and held-CS framing. Output Ku schedules are forced within an explicitly conditional timing envelope; no missing internal transfer or dynamic shared-power model is invented. Production active TI drivers now honor the existing per-component genuine corner override, matching their A/OE receivers; the default emitted corner remains unchanged. Thirteen local-reference/cascade regressions pass, including a genuine 3.6 V TI output beside an unrelated Main 3.135 V reference.

PCB ladder waveforms are per net. The existing field-derived PCB coupling bounds are separate diagnostics; the dynamic `Case.couple` implementation covers explicit panel cable coupling. Neither retimed isolated outputs nor a simultaneous-source fixture is a universal physical shared-return, mutual-coupling or power-current proof. The new preparer retains those diagnostics and flags the absent guarantees. All three terminal input/output paths, actual metadata/graph bridges, published framing checks and appropriate sampled-data qualification are prerequisites before a complete cascade claim.


The active-corner fix also carries the actual first-driver corner into its rail proxy and sampled-MISO fixture selection; old raw results fall back to their historical config corner. Twenty targeted reference/sample/cascade regressions pass, including a transition that crossed early but never finished at a valid logic level. Final prepare-only timing scope/source hashes are `build/spi-cascade-preparation-20260930/requirements-v4.json`. Frozen numerical jobs remain on their own previous source bytes. The simultaneous history preparer rejects absent or unrepaired input paths and records forced schedules explicitly; no solve has been launched by the SI owner.

## Terminal expanded studies and the next local hypotheses

The actual Main source 68 ohm discriminator is terminal **76/192 FAIL**. Six homogeneous WiFi cards fail 24 fast cases; each of the two mixed M1 maps fails 16 slow and 10 fast cases. The slow mixed-map worst is **14.130 ns** across the full 0.8–2.0 V input band at J13 U5.A, above the unchanged 12 ns criterion. This is a real fast-reflection/slow-transit tradeoff; source 68 ohm is not qualified. The terminal true 3 MHz 15 ohm output study fails **4/384** and the combined endpoint study fails **14/6,144** (10 CS, four SCK). The largest CS reversal in the completed matrix is **98.271 mV**, rather than the smaller initially reported counterexample. The original raw files and narrower passes remain historical evidence.

Parent subsequently reports the joint SCK source 270 ohm / cap-branch 15 ohm true 3 MHz fast discriminator **128/128 PASS**. This is a viable bounded candidate, with genuine minimum/typical and seven complementary body/return endpoint combinations prepared separately. It remains unqualified outside those tested endpoints. The corresponding CS source 270 ohm / cap-branch 10 ohm discriminator fails **12/128** at low intrinsic ESR; all high-ESR cases pass. Direct waveform extrema give the smallest high-ESR first falling dip as 2.768712 V, **83.712 mV above VIH**. This supports one selected increase to cap-branch 15 ohm to damp the later low-ESR reversal while testing that high-ESR headroom. Evidence is `build/wifi-damping-tradeoff-20260930/cs270-cap10-extrema.json`; the prepared joint CS 128-case script retains the real private cap branch and all strict criteria.

For the distinct upstream A-input problem, one local filter impedance hypothesis preserves Main's existing 33 ohm launch: R64 becomes 470 ohm and C63 becomes 2.2 pF. Genuine TI input C_comp is 0.87–1.36 pF, so the original nominal local RC product is 1.42–1.53 ns and the proposed product is 1.44–1.67 ns, while external shunt capacitance decreases 61%. The aim is stronger local isolation with similar filtering and less bus loading, rather than further slowing the Main source. A prepared 192-case screen retains all original corner/package/Z/Cin/contact axes on six WiFi and both mixed M1 maps, with opposed local component tolerances. The 2.2 pF supplier identity, independent tolerance/body/reference coverage and actual source geometry remain open; this is a physical hypothesis, not an adopted part or pass claim.

The initial 192-case local-input preparation is retained as historical prepare-only evidence. The replacement `main-sck-wifi-input470r2p2-actual-population384-v2.py` materializes **384 cases**, using provisional engineering C63 ±15% and all four independent R64/C63 tolerance combinations. It explicitly covers both higher-R/higher-C slow extremes and lower-R/lower-C fast extremes; exact supplier heat/drift/temperature allocation may require a wider capacitor envelope. Neither preparation is a completed run.

CS270/15 genuine minimum/typical follow-up is terminal **256/256 PASS**, authoritative handle52389. All256 waveform hashes and frozen source/physical/runner inputs validate; the generated cross-section cache only appended66 entries, preserving all981 original entries and solver identity. Independent complementary body/return coverage remains running. A separately reviewed **48-case original-filter source47** trial retains all14 original33 fast failures plus ten strongest source68 band-transit cases, with independent ±3% source tolerance. It retains original WiFi R64=220/C63=5.6p; only Main R36 changes in the candidate model. This avoids inferring a broad passive window from the failed470/2.2 screen.

The corrected populated-storage regression now requires an actual rejected Schmitt clock with ≥200mV whole-band adverse excursion or a full valid-band recross, rather than the older uniform-edge failure wording. The targeted genuine simulation passed; no rejection was removed. The standalone cascade test addition and corrected assertion are bound in the review-only v2 integration manifest.

## First-article evidence priority

The user clarified that the immediate goal is a working first article. Legacy six-homogeneous-WiFi clock counterexamples remain recorded; they do not automatically establish a failure of the planned mixed M1 population. Conversely, old hypothetical stage overlays cannot establish a pass of the final real A/cap/Y geometry.

A new genuine-current baseline is running with all eight normal quantity-two development receipts, every recorded source/artifact hash verified, and real exported netlists/PCBs privately snapshotted. It covers GPU or eInk in slot1, IO in slot2, WiFi/storage in slots3/4 in both orders, and sole WiFi in slot3 or4 for insertion/debug: six profiles × all32 original source/package/line/Cin/contact configurations =192. Native Main33/WiFi input220/5.6 remain unchanged. The study is one 3 MHz rise/fall pair with default body/reference parameters; it does not claim an eight-clock cascade, arbitrary legal populations or a guaranteed physical ground envelope. It is evidence for deciding whether a first-article clock repair is necessary, not a replacement for the preserved general stress catalogue.

### Genuine planned first-article clock baseline and local input trial

The actual normal quantity-two board set from `spi-development-r70-15-20260930` was verified against all eight authentic receipt source/artifact hashes before the baseline copy. Job 4449 genuinely completed 192/192 cases (980 solver seconds): the four GPU/eInk + IO + WiFi + storage maps with WiFi/storage positions 3/4 swapped passed 128/128. Sole WiFi at J13/J14 produced six strict TI clock failures, indices 145/147/149/151 and 176/178 respectively. These sole states are relevant to insertion/debug; the mixed pass does not erase them. All 192 raw NPZ hashes and every immutable input hash were audited; only a new generated cross-section cache was added. Evidence: `build/scratch-si/main-source33-actual-firstarticle-fourmaps-sole192-run-v2/terminal-summary.json`.

Index 145 has a 10.798 mV falling adverse excursion from 1.041513 V to 1.052311 V over approximately 132 ps. Its full TTL-band fall transit is 3.407 ns. The worst mixed transit is 9.245 ns against the unchanged 12 ns requirement. This suggests a bounded local filtering test without changing the Main launch: R64 = 270 ohm, C63 remains the actual 5.6 pF, Main R36 remains 33 ohm. This pole estimate selects a hypothesis; it proves no receiver margin.

Job 36011 tests precisely 44 selected cases: all six sole failures and the maximum mixed transit in each of four maps, min/max source corner and package state (16 points), each at independent ±3% R64 endpoints. Exact selection and baseline result hash are in `build/scratch-si/wifi-input270-firstarticle-focused-selection.json`; execution uses `wifi-input270-firstarticle-focused44-v1.py`. No capacitor, Main routing/value, threshold or gate change is included. This selected screen does not qualify all populations, component/body/reference sensitivities, an eight-clock byte or the A-to-Y cascade.

The complementary CS output studies also genuinely completed: source R63=270 with cap-branch R69=15 passed 256/256 min/typ high-inductance cases (job 52389) and 896/896 genuine maximum-corner remaining independent body/return endpoints (job 48884). All NPZ hashes were checked; primary inputs were unchanged, and generated cross-section cache additions preserved original entries. Their `terminal-summary.json` files remain under `wifi-normal-cs-source270-r69-15-{min-typ256,body-complement896}-run-v1`. These are model endpoint studies, not guaranteed package/return/contact bounds, all population coverage, actual internal A-to-Y timing or final manufacturing adoption.

The original-filter Main source47 focused trial completed 48 cases with 28 failures: it retained the original fourteen six-WiFi fast counterexamples at both source tolerance endpoints. This rejects a Main-only source47 cure; it does not overturn the later actual Main33 mixed-map baseline pass. Main68 and the lighter470/2.2p combined trial also remained rejected; no Main clock resistor change is selected for the first article.

Job 36011 genuinely terminated 44/44 with ten strict failures. The 32 selected mixed tolerance endpoints passed with maximum 9.250 ns whole-band transit; sole J13 failed all eight and sole J14 failed the lower-R two. The 270-ohm change is rejected as a qualified cure. All raw NPZ and immutable manifest input hashes were verified; the cache was newly generated. The Z1.1 counterexample explains why increasing R is not a monotone gate improvement: at original220 a 23.45 mV second ripple lies entirely below VIL (0.76968→0.79313 V), while at261.9/278.1 ohms its amplitude falls to13.59/10.86 mV but shifts into the threshold band (0.92978→0.94338 and0.98823→0.99909 V). Actual filtering improves amplitude while threshold placement exposes a different ripple. Further value selection must account for both effects rather than assume every increment improves the clock verdict.

A single 390-ohm local-input trial was selected from that phase diagnosis, rather than treating a sequence of resistor increments as a bound. The measured second-ripple reduction between261.9 and278.1 ohms is2.74 mV while mixed transit remains≤9.250 ns; 390 ohms deliberately adds filtering beyond a likely still-ringing330-ohm hypothesis. Job1156 runs exactly the same44 selected cases at±3% localR64; this is initially an engineering resistor envelope pending authentic supplier identity. The strict clock/current/negative-voltage/full-edge checks remain unchanged. No source47 fallback is launched; no actual390 source or hardware adoption is implied by preparation.

Job1156 completed44/44 with six strict failures, all soleJ13. The selected32 mixed endpoints passed; the 390-ohm local change is therefore also rejected as a qualified cure. Both J14 counterexamples and upper-R Z1.1 J13 endpoints passed, but Z.9 J13 still reversed4.7/3.8 mV. All NPZ and immutable manifest hashes were verified. No390 hardware adoption occurred.

The fallback now tests one previously motivated Main resistor change, R36=47 ohm at±3%, with native WiFiR64=220 andC63=5.6p restored. Job91939 uses the same44 actual sole/mixed selections and frozen actual normal15 board/receipt inputs. Previous source47 mixed slowdown remained below12ns, while the general six-WiFi stress had failed; this test asks the narrower actual first-article sole/mixed question. The original strict clock, full-edge, input-current and voltage criteria remain unchanged. No Main reroute or blanket general-population pass is implied.

Main47 job91939 completed44/44 with twelve strict failures, all sole endpoints; the selected32 mixed endpoints passed (maximum11.200 ns). All raw NPZ and immutable manifest hashes were checked. The full384 Main47 run was never launched. No resistor-only trial is adopted.

The user subsequently clarified the intended first article always has CPU and IO, with WiFi, storage and GPU or eInk. The actual four mixed maps already passed original33/220/5.6 baseline128. Sole/general operation remains an explicit limitation rather than an assumed required operating population. The two-card diagnostic89163 had started before that clarification and remains diagnostic only. Further sole-driven component-value trials are stopped; original Main33 is retained for intended-population evaluation.

A few millivolts of reversal inside the unspecified125 switching band do not establish guaranteed data corruption or a full VIL-to-VIH recross; they do prevent a promised every-threshold clock immunity without manufacturer hysteresis. A genuine Schmitt1G17 would structurally address this if wider operation is required, but the125 IBIS output cannot be called a validated conservative17 envelope solely from a family name, drive-current rating or matching footprint. A genuine model or measured bounded comparison remains necessary for such an output surrogate. This does not justify changing the already passing intended-population input stage.

## Intended first article: actual mixed data and clock evidence

The intended first article always includes CPU and IO, WiFi and storage, and
GPU **or** eInk. The four studied slot maps place graphics in slot1, IO in slot2,
and interchange WiFi/storage in slots3/4. This scope does not qualify sole WiFi,
arbitrary slot assignments, or the original homogeneous six-card catalogue.
The long general catalogue was stopped with its genuine partial results and
failures retained; it has not passed.

- Actual original Main33/WiFi220/5.6p SCK mixed128 passed all original axes.
  The additional `original33-mixed-eightpulse64-run-v1` genuinely completed
 64/64, with 16 edges at every actual receiver, at real 3MHz. Eight selected
  slow/fast configurations cover four maps and all eight independent
  MainR36/R64 ±3%, C63 ±10% endpoints. Maximum TI input-band transit was
  9.500ns; maximum RP whole-period adverse excursion was116.681mV.
  All64 raw waveform hashes and immutable input hashes passed the terminal
  audit. Solver time was1863.657s. Default body/reference conditions remain
  separate from these component tolerance endpoints.
- Actual mixed MOSI128 has four retained **early data** diagnostic failures
  at WiFiU6.A, with falling-band reversals2.104..4.299mV. All voltage stress,
  complete-pin current, and recommended12ns input-transition checks pass.
  Auditing all256 actual WiFi input edges shows no later wrong-level recross
  from the next source sample through the next data launch. Worst input final
  crossing is17.975ns and worstVM1.5 arrival11.543ns. The four small reversals
  do not by themselves justify a clock filter repair on sampled MOSI data.
- Fresh actual normal U6.Y-to-ESP MOSI48 completed exit0. NativeR67=220 and
  C67=10p, real routes and finite C67 returnR4.102331mΩ are traversed. Genuine
  MIN/TYP/MAX, package/Cin and two declared paired body/tolerance/reference
  endpoints are covered. All96 edges remain correct from the next source
  sample to the next launch; last crossing is at most12.930ns. Raw uniform
  edge diagnostics32/48 are retained. Minimum absolute stress margins are
  99.1mV positive and111.2mV negative. All raw48 waveform and immutable input
  hashes match. This is a bounded data-output observation, not full independent
  body/reference coverage or a coupled internal A-to-Y simulation.
- Actual mixed MISO128 plus localRP-to-bufferA128 completed256/256 with zero
  retained failures. The main FPGA receiver has minimum positive72.1mV and
  negative362mV stress margins in the declared engineering ground sensitivity.
  Local TI input minimum-.9406V exceeds the default-.5V voltage rating, but
  the unchanged SCES223U table5.1 footnote2 current allowance applies with
  complete modeled pin-current peak14.379mA below50mA. All64 such negative
  cases were independently waveform-audited. This is absolute stress evidence,
  not guaranteed logic operation at negative voltage; the RP output model
  remains an engineering bracket rather than genuine vendor output IBIS.

Combining the actual SCK128/MOSI128/MISO256 target results yields RP MOSI setup
margin146.857ns, hold135.687ns and conditional3MHz MISO turnaround43.564ns.
The6MHz budget diagnostic misses by39.769ns and is explicitly unsupported.
The only missing numerical timing item in this combined target table is the
unpublished ESP32-C3 SPI-slave AC timing; it is not silently called a pass.

### Conditional MOSI cascade observation and first-article obligations

The actual input10–90% transition can take22.240ns; therefore the TI propagation
fixture's2.5ns stimulus condition is not met. An independent fixture-anchored
engineering calculation using the actual inputVM arrival, published4.7ns50pF
fixture maximum and observed output-network excess gives24.449ns latency and
142.218ns data-valid interval before the next source SCK sample. This is useful
for first-article planning but is **not** a datasheet-only slow-input delay bound,
an internal A-to-Y model, or a published ESP setup/hold guarantee.

The appropriate next check is receiving-pin measurement and real protocol
exercise under the intended population: verify WiFi MOSI/SCK/CS timing and
levels, MISO response before the3MHz sample, cache-disabled reception, short
IDENT/READ DMA tails, descriptor rearm and the actual20µs interframe gap.
Declared ground/reference sensitivities do not establish guaranteed contact,
package-inductance, transient-current, or differential rail bounds. General
MB007 stays open; these scoped target observations do not invent a new waiver.

Durable evidence: `build/spi-firstarticle-mosi-data-observation-20260930/`
contains upstream waveform observations, combined target timing and audit
scripts. The fresh U6 output run stores its input manifest, raw waveforms,
original diagnostics, output stability audit and terminal summary at
`build/scratch-si/wifi-normal-mosi-output-sampled48-run-v1/`.
MISO's independent owner audit is in
`build/scratch-si/original33-mixed-miso128-local128-run-v1/owner-terminal-audit.json`.

### Final live-stock manufacturing files: scoped evidence binding

The final index is
`build/final-firstarticle-spi-qualification-20260930/qualification.json`.
It verifies all eight genuine final normal build receipts for two boards each,
their source and artifact hashes, actual routed PCB/netlist identities, vendor
models, and the relevant host/card firmware sources. It supports the four
intended GPU-or-eInk + IO + WiFi + storage configurations at 3 MHz.

The final boards contain several small, real trace-stub differences from older
simulation snapshots. These differences were rejected by the exact graph
checker. The affected cases were replayed on the final native geometry:

- CS output: all 1,280 cases completed with zero strict failures.
- Main MOSI: all 128 cases completed; four early WiFi input edge diagnostics
  remain. All 256 actual U6 input edges meet the unchanged recommended rate
  check and remain stable from the next source sampling instant through the
  next data transition. This is a sampled-data observation, not an
  unconditional strict-edge pass or an internal buffer timing guarantee.
- U6 MOSI output: all 48 cases completed. All 96 edges remain stable through
  the source sampling interval; 32 early uniform-edge diagnostics remain
  archived. The minimum positive and negative stress margins are 99.1 mV
  and 111.2 mV within the declared engineering reference envelope.
- Local RP2040-to-buffer inputs: all 128 cases completed with zero retained
  failures. The 64 negative-voltage cases satisfy the unchanged TI input
  current exception; maximum complete pin current is 14.379 mA versus 50 mA.
  This is absolute stress evidence, not guaranteed negative-voltage operation.

Exact native graph, RLC coefficient, source, rail and probe correspondence
binds the remaining 192 SCK cases, 128 mixed MISO cases and 1,280 SCK output
cases to the final manufacturing files. The checker keeps physical differences
separate from node-name and emission-order differences.

The recomputed RP timing margins remain 146.857 ns setup, 135.687 ns hold and
43.564 ns MISO turnaround at 3 MHz. ESP32-C3 numerical slave timing remains
unpublished, and the actual TI input waveform does not meet the fast
propagation-test fixture. Consequently, this index is **conditional first
article evidence**, with receiving-pin timing, real protocol and power/ground
measurements still required. It does not assert a universal MB-007 pass.
Sole-WiFi and general-population counterexamples remain recorded; the 6 MHz
analog timing diagnostic remains unsupported.
