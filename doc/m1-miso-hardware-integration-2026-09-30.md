# AHC MISO source integration — 2026-09-30

Five card sources now use TI SN74AHC1G125DCKR C151890. GPU/IO/storage/eink share U4 in `rp2040card.core`; WiFi uses U3. Pin1 OE is CS_n, pin2 A is MISO_OUT (WiFi MISO_INT), pin3 GND, pin4 Y is MISO_SRC, pin5 VCC is local3V3. R60=270 ohms C25099 connects MISO_SRC to connector MISO; R61=10k C25744 connects connector MISO to GND. Both are0402 footprints and ±1%±100ppm parts; SI uses ±3% thermal/tolerance corners.

The genuine supplier SC-70 footprint requires relative−90° from the old SOT353: RP2040 card U4 rotation270°, WiFi U3 rotation0°. Each new locked launch checks the exact pin/net map and output-pad alignment. WiFi R60 rotation180° faces pin1 toward U3. IO's added resistors move below existing IOVDD C3 after the initial proposal produced a real collision. Obsolete old-package U4 silk edits were removed; existing inductor guards and GPU TMDS launch corrections remain.

## Source preparation evidence

Sequential source generation stopped at `kicadgen.autoroute`; **no router was launched**. The five new schematics pass ERC and actual exported netlists pass exact co-simulation AHC-network recognition. `kicad-cli pcb drc --severity-all --all-track-errors` has **zero violations involving the new buffer, R60 or R61 on every card**. WiFi has a new PWR_FLAG on its regulated3V3 rail: power reaches the AHC power-input pin through passive L1.

Scratch outputs and logs: `/tmp/cupc8-miso-prep/CARD/`, `CARD-preroute.log`, `CARD-drc.json`, `verified-preroute-summary.json`. Other preroute violations/open connections remain expected inputs to the full pipeline: GPU53/133; IO52/136; storage55/141; eink49/131; WiFi52/95. These are not final DRC or manufacturing passes. Root must run the canonical sequential full board pipelines, receipt validation, pin audit and actual-netlist SI before qualification.

## CS release timing audit

ROM and all four kernel SPI drivers write CS through explicit on/off helpers. `cs_off` stores zero then executes `pop pcl`, `pop pch`; the next on helper loads the SPI register offset, moves1 and stores it. The off-to-on software interval therefore exceeds one12MHz clock83.33ns. No delay was added.

TI SCLS377M section5.6 specifies output-disable max16ns at3.3V±0.3,−40..125°C, CL50pF (12.5ns at15pF). The actual distributed load with270ohm source isolation is a separate conditional engineering load bound;16ns is not a guaranteed timing specification for an arbitrary77pF load. The MISO-only640 matrix does not quantify CS path skew. The final full slowbus analysis must check routed CS timing/skew against this software release interval. Digital emulator contention detection is immediate and does not prove analog disable timing.
