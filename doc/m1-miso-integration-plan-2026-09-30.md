# Physical MISO candidate integration plan, 2026-09-30

## Current candidate status, 11:43 Israel

The prior actual storage RC layout is not qualified:72 cases found5 clock
and21 chip-select strict failures. Larger capacitors did not resolve this and
caused true TI transition-rate failures. Those value trials are not adopted.
A separate local OE hypothesis passes all48 TI cases with220ohm R65 and10p
C63. Its actual placement/routing remains necessary on storage/eInk (root)
and GPU/IO (release agent). Common proposed source is
`build/rp-spi-oe-local-20260930/proposed-source/rp2040card.py`:
R65 CS_n→CS_OE, C63 CS_OE→GND, U4.1 CS_OE; all MCU RC and main copper remain
unchanged. Earlier source/copper candidates below are frozen research history.

GPU/IO/eInk actual216 replay is active; manufacturer RP2040 Schmitt scope is
being modeled from primary minimum hysteresis with full coverage/timing/stress
retained. Shared firmware now explicitly enables all three SPI input Schmitt
bits and hard-asserts default GPIO voltage mode. All five genuine firmware
builds and their compiled startup calls/check pass; this does not qualify SI.
`build/rp-spi-schmitt-enabled-20260930/qualification.json` binds evidence.

All four actual card16contact ground studies pass their declared convergence.
The initial cap selfR source19+57 was WRONG: RP19 is TESTEN, not package GND.
Those C60–62 results are withdrawn. Corrected actual GND57-only studies pass
for all four cards; C63→U4.3 is unaffected. Exact disabled-layer proofs include
correct source/sink electrodes. DC selfR alone does not establish AC capacitor
return bounce, connector/package/current-slew or total-ground guarantees.
Main v3 all-six-slot90contact ground extraction runs separately on actual new
fills. Main MB-005 power ROI exact geometry/model identity proof passes;
final completed-package receipts and affected gates remain required.

WiFi current local layout still has one CS and five ground opens. No complete
coherent hardware-source adoption or manufacturing approval exists. Final
actual OE routes/SI/timing/ground, normal all8 pipelines, power/reset/fab/mech/
fullverification, supplier CAD/live stock/runtime and human CPL gates remain.

## Historical candidate status, 10:59 Israel

Both storage/eInk isolated local LVC/RC physical candidates now pass native
DRC0/open0, strict original physical pad/component guard preservation, all
unrelated original copper preservation, genuine schematic/ERC/pre-route
source equality and complete guarded route installation. C3 and all seven new
references are visible in separately verified label variants with exact copper
identity. Artifact indexes and proposed sources are under
`build/root-rp-spi-filter-local-20260930/{storage,eink,proposed-source}`.
EInk R64/C62 use B.Cu and require final mechanical/assembly proof. Source
label pinning after seed installation keeps proven positions; storage opts
into bounded4mm initial label search, with default tool behaviour unchanged.
Supplier CAD/stock, full normal pipeline and actual local SI remain open.

Main v3 genuine256 stress cases and192conditionalRP sample cases pass;
fixture-anchored delay31.1794ns against73.6594ns budget gives~42.48ns modeled
margin. ESP response is not qualified. The clock2048 study passes. These are
conditional engineering results, not final manufacturing qualification.

Latest main candidate is `build/spi-main-shunt-v3-20260930/main.kicad_pcb`,
SHA256 c863db75538ed7542ec5266afcb312af8415a2ca7d2b9909bb31287e100a1642.
R109 is at(98,64.5)mm/270degrees with visible reference and normal thermal
relief. Native DRC0/open0 and genuine proposed-generator route guards pass;
all original8143 routed items and original pads are preserved. Actual branch
is8.987974mm plus two conservative full1.76mm barrels=12.507974mm. Fresh
local shunt ground is7.4874mOhm upper observed grid,6.134%convergence,
conditional20.4676mV at2.7336A. Final SI replay uses these values. They do not
bound package/contact/transient offsets. No shared source adoption or final
manufacturing receipt exists. Earlier placements and bounds below are history.

The sections below are the earlier AHC integration plan. That AHC/270-ohm/
10k circuit is now physically generated in round3, but the complete SPI
qualification remains open. Do not use the earlier candidate screen as a
manufacturing approval.

The newer **isolated** candidate uses genuine TI SN74LVC1G125DCKR models,
220-ohm card output resistors, 47k card ground bias, a 100k main pull-up and
a new 4.7k main pull-down near U7.48. Its 120 bounded voltage-stress cases
pass at a common card-ground offset of ±150mV. This is not an established
physical ground bound or a complete timing/current qualification.

Main U7.48 is at (97.75,59.95)mm. The nearest existing ground pad is U7.53,
2.5mm away; its existing via is 2.968mm away. Actual inventory and source PCB
hash are in `build/spi-physical-prep-20260930/main-shunt-locality.json`.
An isolated native-board candidate now places R109 at(96.25,63.0)mm,
180degrees, with four added MISO segments/one via and one GND segment/via.
Actual refilled-board DRC and connectivity pass with all8143 prior copper
items and prior pads retained exactly. The actual U7.48-to-R109 path is
7.868mm. A conservative ground self-resistance extraction retains5.449mOhm,
0.9405% convergence, giving conditional14.897mV at2.7336A. Proofs are in
`build/spi-physical-prep-20260930/main-shunt-complete-proof.json` and
`main-shunt-ground-bound.json`. Refilling changed local planes; prior fill
identity and manufacturing/thermal qualification are not claimed. No shared
shunt source or route has been adopted.

The first scratch shunt above hid R109's reference. Actual generator placement
then proves that its visible reference cannot fit at that location; it is a
**historical physical research candidate**, not the proposed final source. A
bounded native copper/courtyard screen followed by both source designator checks
finds R109 at(98.0,64.5)mm,270degrees, with every existing component unchanged.
The isolated main generator proposal now pins that coordinate, changes R107
to100k and six slot-CS R37–R42 to68ohm C27592 on their existing pads. SCK/MOSI
and AUX CS remain33ohm. A new isolated route/refill/native-DRC and separate
ground extraction are required; old7.868mm/14.897mV figures do not qualify the
revised placement. Shared sources remain unchanged.

Native candidate-low-idle boot qualification now passes actual ROM boot,
empty-slot table/raw00 reception, fitted IO type2 and sparse GPU/IO BASIC42.
All-empty probing takes731.195ms vs37.017ms high, adding694.177ms of emulated
time. No firmware change is needed. This functional result models an explicitly
declared digital idle-low fixture, not physical SI approval. Evidence:
`build/main-miso-absent-boot-20260930/qualification.json`.

Wi-Fi additionally needs its independent ESP supply/VIH relationship solved.
Three local LVC125 buffers with permanently enabled outputs are under study.
Explicit GPIO6/7/10 pull disabling is implemented in firmware and actual
card/QEMU images build. Input transition-rate limits remain mandatory:
the 22pF candidate fails the current pointwise-slope screen. Interpretation
is under audit: TI's [transition-rate white paper](https://www.ti.com/lit/wp/slla364a/slla364a.pdf)
defines a finite transition interval divided by its voltage change, while
[Designing With Logic](https://www.ti.com/lit/an/sdya009c/sdya009c.pdf)
requires traversal of VIL(max) to VIH(min). A pointwise derivative screen
can be stricter than that finite-band calculation. Both conservative full
band-entry-to-final-exit time and the existing plateau/re-entry/clock-quality
checks must be inspected before claiming either qualification or a true
published-rate failure. The completed waveform audit finds 40/96 true
over-12ns band transits for the 22pF candidate (worst42.63ns), and 16/96
for 10pF/main MOSI68ohm (worst16.71ns: eight SCK, eight MOSI; CS passes).
The100ohm/4.7pF discriminator still fails true rate/edge limits. Keeping the
existing main SCK/MOSI33ohm values and local220ohm/4.7pF instead passes64
initial input cases; a separate genuine output220ohm/10pF short-line stage
passes32 cases. The broader independent-corner study then finds four tiny
SCK low-capacitance quality failures in its complete512 clock cases; rate
and stress pass. A targeted SCK5.6pF/MOSI4.7pF refinement is running, with
specific Murata supplier candidates and tolerance accounting recorded in
`build/spi-physical-prep-20260930/small-filter-capacitor-identities.json`.
Pointwise slope remains diagnostic. No local Wi-Fi
level buffers are physically adopted.

Keep shared hardware/tools frozen until active receipt-bound ground studies
finish. Necessary IO capacitance and any qualified SPI repairs should enter
one coordinated source freeze, followed by genuine refreshed pipelines.

## Earlier AHC preparation (historical)

Preparation only. No shared hardware source, parts cache/library, board tool or emulator source is changed by this work. Adoption waits for the root's 640-case SI viability result and source freeze. No router was started. Preserve the already integrated GPU TMDS repair.

## Exact proposed circuit

For GPU/IO/storage/e-ink, replace `rp2040card.core` U4 with **SN74AHC1G125DCKR**, C151890. Wi-Fi uses its separately declared U3. The cached genuine EasyEDA symbol/footprint is outside the hashed library in `build/parts/easyeda/C151890`; pin audit is `/tmp/cupc8-si-resume/C151890-easyeda.json`.

Keep numeric pins 1=active-low OE (`CS_n`), 2=A (`MISO_OUT`, Wi-Fi `MISO_INT`), 3=GND, 4=Y, 5=VCC. Proposed common new labels:

- buffer pin 4 → `/MISO_SRC` → **R60.1, 270 ohm** → R60.2 → `/MISO` → J1.B16;
- **R61.1, 10k** → `/MISO`; R61.2 → `/GND`;
- retain the existing buffer bypass capacitor C18 (Wi-Fi C4).

R60/R61 are free on all five card sources. Use explicit 0402 footprints with existing supplier parts: [270 ohm C25099, UNI-ROYAL 0402WGF2700TCE](https://www.lcsc.com/product-detail/C25099.html) and [10k C25744, UNI-ROYAL 0402WGF1002TCE](https://jlcpcb.com/partdetail/C25744). Both are ±1%, ±100 ppm/°C; the primary [UNI-ROYAL general resistor datasheet](https://www.uni-royal.cn/images/userfile/file/1590821906c56505e6d9ab55c7.pdf) specifies the TCR. The 0603 alternative for 270 ohm is [C22966](https://jlcpcb.com/partdetail/0603WAF2700T5E/C22966), requiring a larger layout. Do not combine C25099 with a 0603 footprint. Existing main R107 is 47k C25819 and remains unchanged. The SI worker owns tolerance/TCR stress qualification and actual-buffer models.

## Rotation and placement

**Actual KiCad rotation is old angle minus 90 degrees, not plus 90 degrees.** Direct `pcbnew.FootprintLoad` and `SetOrientationDegrees` verification:

| Pin | Old SOT-353 at 0 degrees, relative mm | C151890 at 270 degrees, relative mm |
| --- | --- | --- |
| 1 | −0.65, +0.90 | −0.65, +1.10 |
| 2 | 0, +0.90 | 0, +1.10 |
| 3 | +0.65, +0.90 | +0.65, +1.10 |
| 4 | +0.65, −0.90 | +0.65, −1.10 |
| 5 | −0.65, −0.90 | −0.65, −1.10 |

At +90 degrees every directional pin position is reversed. The pad-row centres change by 0.2 mm, and the new pads are larger; existing copper cannot simply be re-labelled.

Initial placement proposals (not clearance-qualified) are in `/tmp/cupc8-miso-prep/placement-proposals.json`:

| Card | Buffer x,y,angle | R60 x,y,angle | R61 x,y,angle |
| --- | --- | --- | --- |
| GPU | 14, −12.5, 270 | 16.5, −13.6, 0 | 18, −14.11, 90 |
| IO | 16.5, −18, 270 | 19, −19.1, 0 | 20.5, −19.61, 90 |
| Storage | 14, −12.5, 270 | 16.5, −13.6, 0 | 18, −14.11, 90 |
| E-ink | 14, −12.5, 270 | 16.5, −13.6, 0 | 18, −14.11, 90 |
| Wi-Fi | 26, −15, 0 | 22.5, −15.65, 0 | 21, −16.16, 90 |

Use short pin-4-to-R60 copper. Placement, courtyards, silk, copper and the actual series launch must be checked after importing the genuine footprint. GPU and IO contain hardcoded U4 silk-shape guards for the previous SOT-353: they will fail on the new TI footprint and require footprint-specific replacement. GPU's separate U6 TMDS ground-escape guard must remain intact. These proposals establish space to explore; they are not DRC evidence. An initial multi-footprint Python preview encountered the local SWIG plugin type issue and produced no verified board.

## Digital integration requirements

`hw/cosim/gen_top.py:card_slot_routes` presently requires direct U4/U3.4 → J1.B16 on `/MISO`. Update it to require the sole **270-ohm** series resistor, reject bypass/parallel ambiguity, and separately prove source copper U4/U3.4 → R60.1 and external copper R60.2 → J1.B16. Verify exact new buffer family, OE pin/net, supply/ground and the 10k `/MISO`-to-GND pull. Preserve mutations that reject missing input, output, OE, resistor, pull or ground legs. Add `/MISO_SRC` runtime coverage and the new family's power pins in `coverage.py`. The top's Wi-Fi-only buffer-net check also needs the split output net.

The main 47k pull-up remains. The passive bus is low when at least one physically fitted card's pull-down reaches the shared bus, and high when no such pull-down is connected. Derive this from the original fitted `slots` plus main/card pull copper, **not** `activeSlots`: a physically fitted card still pulls down while firmware boot is blocked. `test/emu/machinenative.mjs` already combines card and main copper; attach the pull metadata there before native options. Boot's `probe_slot` treats RESP_LEN=00 as not-ready, retries, then stores type00/empty after giving up, so it supports the new empty-slot bias; verify this dynamically and ensure no phantom card appears.

**Required native fix:** `Machine::inputs` currently starts `miso=misoIdle` then ANDs selected card output. Setting idle0 would mask every actively transmitted high bit. Instead resolve enabled push-pull output independently: a single OE-enabled, copper-connected buffer drives its actual bit; passive bias applies only with every driver released. Detect multiple enabled drivers separately, including opposing high/low contention. A disabled card must never count as an active driver. Also correct `Rp2040Card::miso()`'s current output-disabled fallback of1: the selected external buffer remains active while its MCU pad is an input, and must sample that pad's own default pull-down, pull-up or retained/input level. The scratch machine copy includes this correction; verify a selected blank/reset RP2040 card returns0 instead of falsely releasing to the main pull-up.

A reversible scratch implementation is `/tmp/cupc8-miso-prep/miso_bus.h`, with an isolated modified `machine.cpp`. Standalone C++ tests pass active high/low under both idle levels, released buffers, no-card high, arbitrary00/FF/A5/5A bytes under passive low, and separate multiple-driver/contradicting-driver faults. This tests the resolver, **not** a compiled full native machine or boot; that remains required after authorized integration.

## Closure sequence after approval to integrate

1. Import/copy the genuine TI symbol, footprint and audit cache through the existing part tooling; freeze all source/cache inputs before board receipts are generated.
2. Implement the common-core and Wi-Fi circuits, guarded placements and affected silk handling; update digital recognition/resolution and the SI worker's exact model/physical resistor recognition without double-counting candidate elements.
3. Focused tests: output bits survive passive0; empty selection with another card fitted reads00; no-card readsFF; disabled buffers release; shorted/wrong OE and contention mutations fail; missing/incorrect series or pull is rejected; real boot exhausts00 retries without phantom cards.
4. Build changed cards **one at a time**, never a second concurrent Freerouting process. The root owns queue sequencing. Keep the GPU TMDS change in the generated source.
5. Validate actual receipts and run canonical SI on actual resistor/source/output copper, including the unchanged thresholds and full selected voltage/model/rate stress matrix. Run focused digital mutations and then the authorized full co-sim/E2E subset against the same receipt set.
6. Update reports only with real generated evidence; the scratch resolver and placement proposals cannot attest manufacturing readiness.
