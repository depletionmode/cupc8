# Actual first-article M1 scope and evidence

This audit follows David's current goal: get a first article that works.
It does not authorize an order, change a verification limit or waive a
known failure. Current packages are genuine development candidates.

## Confirmed acceptance target (David, 2026-09-30)

**Main + system + CPU + IO + storage + WiFi + either HDMI/GPU or eInk.**
CPU and IO are always fitted. This exact integrated computer is the working
first-article target, with both graphics alternatives checked separately.
System programming, ROM/kernel/BASIC, keyboard, display, microSD SAVE/LOAD
and WiFi must work; clock-case passes alone are insufficient. See the
[first-article plan](first-article-plan.md#first-article-acceptance-target--confirmed-by-david-2026-09-30).
Sole-WiFi/missing-card and general-capacity findings are retained separately,
not used alone to force a repair of this intended first-article configuration.
MainR36 remains33; rejected47/270/390 trials are not adopted.

## Decision under the current goal

A separately recorded **conditional working-M1 first-article profile** is
a legitimate engineering target under David's new direction. It must name
the fitted four cards, tested initial slot maps, supply, firmware and load
scope, and the remaining risks. It is not the ordinary all-green release
or proof of general six-card capacity. The current six-WiFi failure does
not itself establish a fault in that four-card machine; actual four-card
evidence is necessary before deciding whether Main needs any repair.

| Open item | Consequence for this first article |
| --- | --- |
| Six-WiFi capacity fixture fails | Retain failed MB-007/general-capacity report. If actual M1 passes, this does not require repairing Main solely for an unfitted population. A scoped first-article decision must explicitly keep general capacity unresolved. |
| Actual fitted four-card waveform/current/timing fails | Relevant to the user's machine. Resolve the necessary local issue or identify a specific decision; no broad first-article exemption. |
| Any-slot or missing-subset proof incomplete | Do not claim the original any-slot capability is qualified. Record precisely which initial configurations were proved and bring up those; the original capability remains an open project requirement. |
| Existing accepted USB/CPU-bus/GPU conditions | Carry the exact limited approvals and mandatory receiving-pin/USB/burn-in measurements; do not broaden them. |
| Quantities, Ceff/contact/silicon-current/temperature measurements in the existing physical plan | Perform after parts/boards exist. Preserve conditional modeled load assumptions and unguaranteed maxima; do not demand a fictitious pre-order measurement or call unknown bounds proven. |
| Known DRC/manufacturing/topology defect, missing part identity, stock/CPL/options approval | Still a concrete order blocker. A first article needs a manufacturable, correctly fitted package. |

The normal `make verify`/signed-readiness contract remains unchanged. If
the project records this narrower first-article decision, its readiness
artifact must separately report the preserved red general-release rows
and exact conditional scope. The existing all-green generator cannot be
used to disguise that decision as ordinary manufacturing approval.

## The machine to bring up

The authoritative [milestone](../milestone-1.md) and [slot specification](slot.md)
require Main + CPU, a system card for in-system programming, and four I/O
cards: **GPU or eInk, IO, WiFi and storage**. GPU and eInk are never fitted
together. A programmed machine must subsequently work without its system
card. Full M1 networking and SD writes require a 5 V USB-C source advertising
3 A; the 1.5 A mode disables radio and SD writes. Use the existing 3 MHz
SPI and 20 us minimum WiFi interframe gap, existing held-CS firmware,
GPU 252 MHz/1.20 V and approved first-article operating conditions.

The current research maps are GPU1/IO2/WiFi3/storage4 and the WiFi/storage
3/4 swap. Their eInk equivalents replace GPU in slot1. These are concrete
initial bring-up configurations, **not a user-approved restriction**:
the milestone still promises any card in any slot. Slots5/6 are reserved
for future expansion in the initial machine; six WiFi cards are a general
capacity fixture, not the specified four-card M1 population.

## What the existing SCK evidence actually proves

| Evidence | Proven scope | Remaining limitation |
| --- | --- | --- |
| Original33 full-run SCK subgroup | 352 homogeneous/storage-only cases; fourteen failures in the six-WiFi fixture | No mixed M1 profiles in that subgroup. A mixed-machine pass cannot be inferred. |
| Historical v7 | 2,048 terminal passing hypothetical-filter cases: two mixed maps and WiFi alone in slots3/4, 512 each | Script inserts RC/TI input at the old MCU pad and omits the real added A/cap/Y branches. No actual-native electrical bridge to current WiFi exists. |
| Main68 trial | Real-layout value-only SCK192; 76 failures, worst TI band transit14.130ns against12ns | Rejected. It is not evidence that Main33 mixed M1 fails. |
| Actual output270/cap15 studies | Scoped endpoint/body/pulse hypotheses, with original thresholds retained | Final source/native freeze, physical bridge and complete machine timing remain separate. |

The v7 source/result/input hashes, all2,048 unique rows and four profile
counts are audited in
`build/first-article-m1-scope-audit-20260930/v7-audit.json`.
Its own frozen input scope explicitly excludes future physical branches.
Keep all old tests, waveforms and failure reports.

## Next necessary waveform evidence

Before changing Main termination to fix the six-WiFi fixture, obtain a
**direct actual Main33 / WiFi220-and-5.6pF baseline** on the intended mixed
machines. Use authentic current native PCBs and true netlists; no ideal
filter overlays. A narrow initial screen can use the two mixed maps, their
eInk replacements and sole-WiFi slots3/4. Preserve the original complete
IBIS source/package/Cin/line/contact endpoints and actual R/C tolerances;
scope source/receiver rails, grounds, body parasitics and eight-clock
behavior explicitly. The SI owner chooses a justified staged case set;
do not claim a small screen bounds an unproved axis.

The SI owner completed the genuine current-normal baseline:
`build/scratch-si/main-source33-actual-firstarticle-fourmaps-sole192-v2.py`
(job4449). It uses four exact GPU/eInk mixed swap maps and sole-WiFi
slots3/4, 32 original axes each, actual Main33/WiFi220/5.6, no resistor
or ideal-filter overrides. All eight authentic quantity-two receipts
validate before copying. **All128 mixed-map cases pass; six of64 sole-WiFi
cases fail.** The sole-card cases remain documented against the broader missing-card
requirement. After David confirmed all four I/O cards are always fitted in
his first article, they are not the active resistor-repair target. Local270
failed10/44, local390 failed6/44 and Main47 failed12/44 (sole-card cases);
all32 selected mixed endpoints passed each focused trial. Main47's
conditional384 run was not launched. Keep originalMain33/WiFi220/5.6;
no Main reroute or trial-value adoption has occurred.

The focused44 selection retains all six original failures and the maximum
TI band transit in each of sixteen mixed-map/source/package partitions.
It remains a default-parasitic endpoint screen; expanded body/ground/pulse/
timing coverage and genuine selected native/source freezing are separate.
No Main reroute is justified by the current results.

Check every physical receiver, TI current/stress/whole-band slew and RP
Schmitt condition, then actual sampled MOSI/MISO, CS lead/hold and release
turnaround. Source-level held-CS timing does not by itself prove received
timing. ESP unpublished process-wide numeric response bounds remain
visible, with the existing physical SPI-service test after delivery.
Any failing actual M1 case needs a necessary local remedy and replay.

Any-slot/missing-card coverage remains open until actual model equivalence
or required population tests close it. The dry CS topology proof alone
does not establish physical shared-ground/coupling independence.

## Concrete first-article acceptance checklist

### Before an order

- Freeze one coherent actual source/native set; validate fresh eight-board
  quantity-two receipts, genuine normal builds, ERC/DRC, actual full fab
  geometry, BOM/pin consistency and full mechanical fit.
- Close actual intended-machine SPI failures and timing/stress coverage;
  preserve broader capacity failures as separate red results. The current
  [verification contract](verification.md) still requires `make verify`
  green and signed readiness. A limited first-article release contract
  would have to explicitly name remaining general-capacity/any-slot
  qualification gaps and risks. This audit proposes that explicit profile
  under the new goal; it does not sign an order or falsify a full gate.
- Preserve current M1 power/reset qualification, full-current copper
  limits and existing accepted [first-article exceptions](fab-waivers.md).
  Unknown maximum silicon current/droop/contact/biased-capacitance bounds
  do not become guarantees merely because samples are planned. Retain the
  existing modeled M1 scenario and after-delivery measurement obligations;
  distinguish an observed in-scope fault from an unmeasured lot bound.
- Run required functional/native E2E in an environment supporting its
  normal localhost/network operations. Preserve blocked attempts.
- Obtain fresh combined stock checks, true supplier CAD/CPL evidence,
  human unsigned-pack decisions and production-options review. David
  signs readiness and places the order. No fabricated signatures.

### After delivery, before calling the machine working

- Follow the existing [first-article plan](first-article-plan.md) in order:
  notch/finger/solder inspection, unpowered short/fit/contact checks,
  current-limited rail bring-up, programming/POST, then integrated loads.
- Boot real ROM/kernel/BASIC; enumerate the keyboard; produce stable DVI
  or eInk; SAVE/LOAD from microSD; join WiFi and fetch from a real server.
  Repeat with the system card removed after programming and with the
  supported missing-card/power-mode behaviors.
- Apply the plan's exact measurements and sample obligations: reset
  thresholds, rail/load/contact/Ceff/current/temperature, actual receiving
  pin SI, WiFi polling during settings writes and GPU one-hour near40C
  burn-in. Keep failed records; repair or bound the issue before a larger
  run. Two assembled boards do not establish production-wide silicon
  maxima or automatically satisfy larger part-lot sample requirements.

This list separates preparable order evidence from physical measurements;
`kind=hw` measurements require delivered parts and are excluded from the
pre-order aggregate by the existing contract. It does not change either
set's limits or approve a new blanket waiver.
