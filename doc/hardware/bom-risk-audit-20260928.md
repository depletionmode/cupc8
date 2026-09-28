# BOM risk audit for manufacturing (2026-09-28)

Scope: every distinct LCSC part on the eight boards' fab BOMs
(`build/hw/<board>/fab/bom.csv`: main, cpu, gpu, io, storage, wifi, eink,
system), plus the pending parts that are not in `build/hw` yet:

- GPU RN1/RN2 C425067 -> **C182716** (360 ohm arrays, `doc/hardware/pending-hw-parts-C182716.yaml`);
- Wi-Fi R9 C25818 -> **C861412**, R10 C25803 -> **C122538** (already in `hw/boards/wifi.py` and `hw/power/wifi_parts.py`; the built BOM is older);
- main-board MB-051 reset qualifier from `hw/power/reset_supervisor.py`
  (proposed, unreviewed): U17 REF3425 C187836, U18/U20 OPA376 C42134, U19
  SN74LVC07A C7809, D7 BAT54A C92068, R7/R8 C17888 -> RLM12FTCMR001 C393098,
  0.1 % ladder C860320 / C408766 / C860392 / C861593 / C860067, 1 % C23213 /
  C26095, plus one more C21190 and C25803.

113 LCSC codes in all. Stock, library type and price were fetched live from
JLC's parts API (the one `hw/tools/jlcparts.py` uses) and LCSC's product API on
2026-09-28 and recorded in `doc/hardware/bom-risk-20260928.json`.
`python3 tools/bom_risk.py --pending` rebuilds every table below from that
JSON with no network; `--fetch` refreshes it (keeping the hand-written
lifecycle notes). LCSC's own `productCycle` flag reads "normal" for all 113,
including the parts the makers have discontinued, so it is useless as a
lifecycle signal: lifecycle comes from the makers' pages and notices (sources
at the end).

**Quantities.** "Max sets" = JLC stock / quantity used in one full set (one of
each of the eight boards). The first article is 2 of each board (parts.md
plans 3 main boards: one spare). No full-run size is set, so the tables give
the largest run the current stock supports.

## Summary

### Must fix

| # | Part | Problem | Action / alternative | Model impact |
|---|---|---|---|---|
| 1 | **SST39VF040-70-4I-NHE C645939** (main U10 ROM) | Active, but **11 in stock** (JLC and LCSC): caps the run at 11 main boards, and another buyer can take them before the order | Buy 3-4 into the JLC parts inventory now (parts.md Risk 1). Fallback in stock: SST39VF010-70-4I-NHE-T C632851 (33, same footprint, 128 KB: *not* equal, the ROM banking shrinks to 0-63). No equal drop-in stocked at JLC: MX29LV040CQI-70G C2803162 (PLCC-32, 3.3 V, 4 Mbit) has 0 stock and uses AMD-style 555h/2AAh unlock with 64 KB sectors instead of SST's 5555h/2AAAh and 4 KB, so the ROM writer would change | none in `hw/power` |
| 2 | **ICE40HX4K-TQ144 C1521989** (main U7, CPU U1) | 51 at JLC, **24 at LCSC**, 2 per set: 25 sets at most; the first article needs 4 (5 with the spare main) | Reserve 5-6 in the JLC inventory now (parts.md Risk 2). No drop-in: the only other stocked iCE40 HX is ICE40HX8K-CB132 C1521621 (BGA, 50) | - |
| 3 | **RT9013-12GB C58464** (main U4, CPU U3) | **Obsolete** (Richtek lists EOL; DigiKey "no longer manufactured"). 16,181 at JLC, so the first article is fine | Before any run beyond first article: TI TLV75512PDBVR **C2877864** (Active, 3,108 in stock, same SOT-23-5 pin map; `cpu-ldo-replacement.md`). The RT9013 clones (TPRT9013-12GB C587161 etc.) are -40..85 C Ta rated, not equal | `hw/power/design.py` RT9013 dict and RT9013_TOL/THETA_JA, `ldo.py` (POW-002), `board_thermal.py`, `thermal_bind.py`, `cpu_board.py` (CC-005) all rerun with TLV755P data (1.5 % at 1 mA only, 0.47 uF min effective Cout) |
| 4 | **W25Q16JVSSIQ C131025** (the five RP2040 cards' flash) | **EOL**: Winbond obsolescence notice 2026-01-30, last order 2026-04-30, **last ship 2026-07-30** (both passed). JLC still has 13,371 (5 per set: 2,674 sets) | OK for the first article and a modest run from JLC stock. Winbond's replacement W25Q16RVCSJQ is not stocked at JLC (W25Q16RVSSJQ C31137404: 43). Stocked second source: GigaDevice GD25Q16ESIGR **C2922792** (38,949), same SOIC-8 208 mil. Either needs the RP2040 boot2 checked (QE bit / 0x31 SR2 write) on hardware | design.py flash current allowances ("sysctl RP2040 + flash" etc.) to be re-read from the new datasheet |
| 5 | **W25Q32JVSSIQ C179173** (main FL0, CPU FL1) | **EOL**: last order **2026-07-30** (passed), last ship 2027-01-30. JLC 21,299 (2 per set) | OK for first article. Replacement W25Q32RVCSJQ **C54442318** (160 in stock) or GD25Q32ESIGR **C2832998** (16,387). The iCE40 boot sequence (0xAB wake, 0x0B read) is standard on both; confirm on a board | design.py `"W25Q32"` currents (0.015 / 0.002 A) |

"Must fix" for items 3-5 means before a production run, not before the
first article: the stock is there today. Items 1-2 must be acted on before the
first-article order, because the stock is too thin to rely on at order time.

### Watch

| Part | Why | Alternative / note |
|---|---|---|
| Samsung CL21A226MAQNNNE **C45783** (22 uF 25 V 0805: main x5, gpu x3, io x3, storage, eink, wifi x2) | **NRND** on Samsung's product page (and in `wifi_parts.py`); 4.15 M in stock, basic | Samsung's named replacement CL21A226MAYNNNE **C602037** (Mass Production, 79,974, *extended*: +$3 per board order on 6 boards). **Model impact:** `hw/power/wifi_parts.py` CAPACITORS['C45783'] (tolerance, TCC, DF, DC-bias and ESR curves must be re-sourced from the MAY spec sheet, and FITTED C1/C2 changed), `design.py` IOB_COUT / GPUB_COUT assumptions (value unchanged). Keep MAQ for M1 |
| ESP32-C3-MINI-1U-N4 **C2911374** (wifi U1) | **NRND** (Espressif datasheet Table 1-2); 2,206 at JLC | ESP32-C3-MINI-1U-**N4X** C49230958 (recommended, same footprint/pins, chip rev v1.1) has **0** at JLC today; the pinned ESP-IDF v5.5.5 supports rev v1.1. -1U-H4 C3013922 (914) is NRND too |
| PCIE-64P11L C19188869 (main J3) | 151 in stock, single source (Sofng), no other x4 socket stocked | Buy with the ROM/FPGA reservation if a run > ~50 is planned |
| IS62WV5128EBLL-45HLI C1348955 (main SRAM) | 224 in stock; lifecycle not confirmed on issi.com (distributors: active) | Alliance AS6C4008-55STIN C1349756 fits the footprint but is 55 ns vs 45 ns and has 5 in stock: not equal |
| UMAX 3183-10112P1T C404111 / 3183-10200P1T C404113 | 398 and 2,250 (6 per set: 375 sets), single source, THT (hand/wave fee not in the costs) | none stocked at JLC |
| SMD1812P350TF/16 C46970911 (main F1) | 310 in stock | C20815 (2,781) is the 6 V-rated version: *not* equal-or-better |
| SMD1206P110TFT C143975 (slot fuses x6) | 1,442 (240 sets) | SMD1206P110TF C20801 (5,862) has Rmax 250 vs 210 mOhm and 6 V: not equal; would move POW-006's slot drop |
| RT0603BRB0743KL C860392 (MB-051 R_L3, 43k 0.1 % 10 ppm) | 2,337; the only other 10 ppm 43k (PTFR0603B43K0N9 C19679932) has 4 | fine for any plausible run |
| RT0603BRD078K87L C861593 (MB-051 R_T) | 25 ppm/C forces `reset_supervisor.py` R_TOL_25 | **Improvement:** PTFR0603B8K87N9 C19680060, 8.87k 0.1 % **10 ppm**, 4,087 in stock: R_T could use R_TOL (reset_supervisor.py) and widen the 3V3 window margin |
| HSO321S 12 MHz C160457 (main Y1) | 3,076, single maker | OT322512MJBA4SL C725989 (8,294, ±10/±20 ppm) is a candidate; check its OE polarity and supply current before swapping |
| HT7533-2 C82217 | Holtek's 2002 EOL notice names the suffix-less HT7533 (replacement: the -1 suffix); -2 is not listed. No current notice found | alternative if needed: HT7533-1 SOT-23-5 C135539 (3,592) |
| C182716 (pending GPU arrays) | 4,617 (2 per set: 2,308 sets), extended | fine |

Also noted:

- **Single source (by part number):** every IC and connector is a
  single-maker part; the ones without a stocked pin-compatible second source
  at JLC are the FPGA, ROM, SRAM, RP2040, ESP32 module, all three UMAX/Sofng
  sockets, the HDMI/USB-A/USB-C/microSD connectors, TPS259470A, TPS63802,
  TPS61023, TLV62569P, MAX16054, MAX811T, REF3425 and OPA376. The passives,
  LEDs, MMBT3904/2N7002, BAT54A, USBLC6 and the 74LVC parts are multi-source.
- **Extended-part fees dominate small builds.** At 2 boards the main board is
  $206 of parts+fees without the MB-051 parts and $258 with them, of which
  $96 / $132 is the 32 / 44 extended-part fees ($3 each, per order). The
  MB-051 qualifier alone adds 12 extended lines ($36 per main-board order).
- `doc/m1-live-status.md` still says the qualifier uses an OPA2333; the file
  (and hw/parts/C42134.yaml) use the OPA376. The status text is stale.
- The Wi-Fi fab BOM in `build/hw/wifi` still carries C25818/C25803 for
  R9/R10: it predates the droop fix and needs the coordinated rebuild.

## Costs (JLC pricing, 2026-09-28)

Each board type priced as its own JLC order: per BOM line, quantity x boards
+ JLC's attrition count at the matching price tier; plus $3 per distinct
extended part that is not "preferred". **Not included:** PCB fabrication,
stencil, setup/assembly fees, through-hole or hand soldering (UMAX sockets,
headers), gold-finger/ENIG options, shipping, duty, and the loose Wi-Fi
antenna/lead and e-ink panel.

With the pending parts (the tables below):

| Board | Lines | Extended lines | 2 boards: total | per board | 10 boards: total | per board |
|---|---:|---:|---:|---:|---:|---:|
| main | 64 | 44 | 258.49 | 129.25 | 672.61 | 67.26 |
| cpu | 12 | 4 | 51.53 | 25.76 | 195.62 | 19.56 |
| gpu | 26 | 9 | 39.64 | 19.82 | 74.34 | 7.43 |
| io | 28 | 10 | 41.71 | 20.86 | 72.38 | 7.24 |
| storage | 18 | 6 | 26.41 | 13.20 | 49.34 | 4.93 |
| wifi | 14 | 7 | 30.81 | 15.40 | 59.01 | 5.90 |
| eink | 19 | 7 | 29.68 | 14.84 | 52.23 | 5.22 |
| system | 19 | 5 | 23.18 | 11.59 | 44.95 | 4.49 |

Parts with stock for fewer than 100 full sets: C1521989 (51 in stock, 2/set), C645939 (11 in stock, 1/set)

All eight boards, one order each: **$501.45 for 2 of each** ($250.73 per
set), **$1,220.47 for 10 of each** ($122.05 per set). The CPU card stays at
~$20 per board even at 10 because its iCE40 is $17.40.

Without the pending parts (the BOMs as built today):

| Board | Lines | Extended lines | 2 boards: total | per board | 10 boards: total | per board |
|---|---:|---:|---:|---:|---:|---:|
| main | 52 | 32 | 206.32 | 103.16 | 573.21 | 57.32 |
| cpu | 12 | 4 | 51.53 | 25.76 | 195.62 | 19.56 |
| gpu | 26 | 9 | 39.65 | 19.83 | 74.37 | 7.44 |
| io | 28 | 10 | 41.71 | 20.86 | 72.38 | 7.24 |
| storage | 18 | 6 | 26.41 | 13.20 | 49.34 | 4.93 |
| wifi | 14 | 6 | 27.08 | 13.54 | 54.61 | 5.46 |
| eink | 19 | 7 | 29.68 | 14.84 | 52.23 | 5.22 |
| system | 19 | 5 | 23.18 | 11.59 | 44.95 | 4.49 |

Totals as built: $445.57 for 2 of each board, $1,116.70 for 10 of each.

## Per-board tables (pending parts applied)

"JLC" is JLC's library type ("pref" = preferred extended, no fee). Stock is
JLC's (what JLC can place); LCSC's own stock is in the JSON (`lcsc_stock`).
Refs like `R_L1` are the reset_supervisor.py names; the board has not been
annotated with them yet.

#### main

| LCSC | Maker / MPN | Refs | Qty/brd | JLC | Stock | Max sets | Lifecycle | Risk |
|---|---|---|---:|---|---:|---:|---|---|
| C2286 | Hubei KENTO Elec KT-0603R | D11..D6 | 13 | basic | 3866603 | 175754 | Active (no notice found) |  |
| C4190 | UNI-ROYAL 0603WAF2201T5E | R9 | 1 | basic | 7775468 | 7775468 | Active (no notice found) |  |
| C7272 | Analog Devices Inc./Maxim Integrated MAX811TEUS+T | U6 | 1 | extended | 13525 | 13525 | Active (ADI, via Octopart) |  |
| C7519 | STMicroelectronics USBLC6-2SC6 | U1 | 1 | extended | 44473 | 14824 | Active (ST) |  |
| C7809 | Texas Instruments SN74LVC07APWR | U19 | 1 | extended | 14757 | 14757 | Active (TI) |  |
| C14663 | YAGEO CC0603KRX7R9BB104 | C11..C703 | 44 | basic | 57465769 | 1008171 | Active (no notice found) |  |
| C15849 | Samsung Electro-Mechanics CL10A105KB8NNNC | C1,C10,C17,C9 | 4 | basic | 6621857 | 945979 | Mass production (Samsung) |  |
| C17477 | UNI-ROYAL 0805W8F0000T5E | R201..R701 | 6 | basic | 7002586 | 1167097 | Active (no notice found) |  |
| C17888 | UNI-ROYAL 1206W4F0000T5E | R4 | 1 | basic | 2712605 | 2712605 | Active (no notice found) |  |
| C19702 | Samsung Electro-Mechanics CL10A106KP8NNNC | C201..C701 | 10 | basic | 10912270 | 1091227 | Mass production (Samsung) |  |
| C20526 | Jiangsu Changjing MMBT3904(RANGE:100-300) | Q1,Q2 | 2 | basic | 284386 | 94795 | Active (no notice found) |  |
| C21189 | UNI-ROYAL 0603WAF0000T5E | R8 | 1 | basic | 23866966 | 23866966 | Active (no notice found) |  |
| C21190 | UNI-ROYAL 0603WAF1001T5E | R10..R_S | 14 | basic | 22836246 | 992880 | Active (no notice found) |  |
| C22775 | UNI-ROYAL 0603WAF1000T5E | R49,R50 | 2 | basic | 12047811 | 1095255 | Active (no notice found) |  |
| C22833 | UNI-ROYAL 0603WAF1131T5E | R3 | 1 | extended | 7645 | 7645 | Active (no notice found) |  |
| C22935 | UNI-ROYAL 0603WAF1004T5E | R13,R14 | 2 | basic | 6754418 | 3377209 | Active (no notice found) |  |
| C23140 | UNI-ROYAL 0603WAF330JT5E | R17..R708 | 38 | basic | 5724795 | 106014 | Active (no notice found) |  |
| C23162 | UNI-ROYAL 0603WAF4701T5E | R105..R703 | 8 | basic | 22982411 | 2872801 | Active (no notice found) |  |
| C23166 | UNI-ROYAL 0603WAF4122T5E | R15 | 1 | extended | 12369 | 12369 | Active (no notice found) |  |
| C23186 | UNI-ROYAL 0603WAF5101T5E | R1,R2 | 2 | basic | 25815276 | 6453819 | Active (no notice found) |  |
| C23213 | UNI-ROYAL 0603WAF6804T5E | R_F33 | 1 | extended | 29637 | 29637 | Active (no notice found) |  |
| C25803 | UNI-ROYAL 0603WAF1003T5E | R44,R55,R_NPOR_PD | 3 | basic | 22562923 | 4512584 | Active (no notice found) |  |
| C25804 | UNI-ROYAL 0603WAF1002T5E | R101..R87 | 39 | basic | 22069577 | 469565 | Active (no notice found) |  |
| C25819 | UNI-ROYAL 0603WAF4702T5E | R107..R97 | 9 | basic | 1780897 | 197877 | Active (no notice found) |  |
| C26095 | UNI-ROYAL 0603WAF2704T5E | R_F12 | 1 | extended | 14421 | 14421 | Active (no notice found) |  |
| C42134 | Texas Instruments OPA376AIDBVR | U18,U20 | 2 | extended | 23282 | 11641 | Active (TI; status field not read directly) |  |
| C45783 | Samsung Electro-Mechanics CL21A226MAQNNNE | C3..C7 | 5 | basic | 4151070 | 276738 | NRND (Samsung) | WATCH: CL21A226MAYNNNE C602037 |
| C58464 | Richtek Tech RT9013-12GB | U4 | 1 | extended | 16181 | 8090 | Obsolete (Richtek EOL; DigiKey) | MUST-FIX pre-run: TLV75512PDBVR C2877864 |
| C79401 | Analog Devices MAX16054AZT+T | U16 | 1 | extended | 1925 | 1925 | Active (ADI, via Octopart) |  |
| C82217 | Holtek Semicon HT7533-2 | U15 | 1 | extended | 15188 | 15188 | Active (Holtek 2002 EOL notice covers suffix-less HT7533 only) |  |
| C92068 | onsemi BAT54ALT1G | D7 | 1 | extended | 41062 | 41062 | Active (onsemi) |  |
| C95204 | YAGEO RT0603BRD0710KL | R59 | 1 | extended | 1786611 | 1786611 | Active (YAGEO RT) |  |
| C107055 | YAGEO CC0603JRNPO9BN681 | C15 | 1 | extended | 1124634 | 1124634 | Active (no notice found) |  |
| C127691 | UNI-ROYAL 1206W3F500MT5E | R202..R702 | 6 | extended | 83036 | 13839 | Active (no notice found) |  |
| C143975 | PTTC SMD1206P110TFT | F200..F700 | 6 | extended | 1442 | 240 | Active (no notice found) | WATCH: 6/set; C20801 not equal |
| C160457 | HELE HSO321S 12MHZ 3.3V -40~+85℃ | Y1 | 1 | extended | 3076 | 3076 | Active (no notice found) |  |
| C165948 | Korean Hroparts Elec TYPE-C-31-M-12 | J1 | 1 | extended | 446368 | 223184 | Active (no notice found) |  |
| C179173 | Winbond Elec W25Q32JVSSIQ | U8 | 1 | extended | 21299 | 10649 | EOL: last order 2026-07-30, last ship 2027-01-30 (Winbond) | MUST-FIX pre-run: GD25Q32ESIGR C2832998 / W25Q32RVCSJQ C54442318 |
| C187836 | Texas Instruments REF3425IDBVR | U17 | 1 | extended | 26040 | 26040 | Active (TI) |  |
| C193402 | MDD SMF5.0A | D1 | 1 | extended | 577860 | 577860 | Active (no notice found) |  |
| C318884 | XKB Connection TS-1187A-B-A-B | SW1,SW2 | 2 | basic | 550241 | 275120 | Active (no notice found) |  |
| C326727 | YAGEO RT0603BRD0737K4L | R58 | 1 | extended | 12072 | 12072 | Active (YAGEO RT) |  |
| C352826 | Texas Instruments CD74HC4051PWR | U11,U12 | 2 | extended | 25908 | 12954 | Active (TI) |  |
| C357060 | TAI-TECH HPC5020NF-2R2M | L1 | 1 | extended | 2505 | 2505 | Active (no notice found) |  |
| C393098 | TA-I Tech RLM12FTCMR001 | R7,R8 | 2 | extended | 29296 | 14648 | Active (no notice found) |  |
| C398365 | Texas Instruments TLV62569PDDCR | U3 | 1 | extended | 14842 | 14842 | Active (TI) |  |
| C404111 | UMAX 3183-10112P1T | J2 | 1 | extended | 398 | 398 | Active (no notice found) | WATCH: 398, single source |
| C404113 | UMAX 3183-10200P1T | J11..J16 | 6 | extended | 2250 | 375 | Active (no notice found) | WATCH: 6/set, single source |
| C408766 | Viking Tech AR03BTB2002 | R_L2 | 1 | extended | 12375 | 12375 | Active (no notice found) |  |
| C465732 | Texas Instruments TCA9555PWR | U13,U14 | 2 | extended | 39363 | 19681 | Active (TI) |  |
| C645939 | Microchip Tech SST39VF040-70-4I-NHE | U10 | 1 | extended | 11 | 11 | Active (Microchip) | MUST-FIX: 11 in stock; reserve in JLC inventory |
| C702117 | Texas Instruments TLV7011DBVR | U5 | 1 | extended | 6136 | 6136 | Active (TI) |  |
| C860067 | YAGEO RT0603BRB0710KL | R_BT | 1 | extended | 151672 | 151672 | Active (YAGEO RT) |  |
| C860320 | YAGEO RT0603BRB0730KL | R_L1 | 1 | extended | 17501 | 17501 | Active (YAGEO RT) |  |
| C860392 | YAGEO RT0603BRB0743KL | R_L3 | 1 | extended | 2337 | 2337 | Active (YAGEO RT) | WATCH: 2,337; few 10 ppm alternates |
| C861412 | YAGEO RT0603BRD07453KL | R5 | 1 | extended | 7451 | 3725 | Active (YAGEO RT) |  |
| C861593 | YAGEO RT0603BRD078K87L | R_T | 1 | extended | 2567 | 2567 | Active (YAGEO RT) | option: PTFR0603B8K87N9 C19680060, 10 ppm |
| C1348955 | ISSI IS62WV5128EBLL-45HLI | U9 | 1 | extended | 224 | 224 | Active (distributors; issi.com not read) | WATCH: 224, no equal drop-in |
| C1521989 | Lattice ICE40HX4K-TQ144 | U7 | 1 | extended | 51 | 25 | Active (Lattice) | MUST-FIX: 51 JLC / 24 LCSC; reserve |
| C2912578 | Milliohm HoAR0603-1/10W-100KR-0.1%-TCR25 | R6 | 1 | extended | 6544 | 6544 | Active (no notice found) |  |
| C3662799 | Texas Instruments TPS259470ARPWR | U2 | 1 | extended | 2684 | 2684 | Active (TI) |  |
| C19188869 | SOFNG PCIE-64P11L | J3 | 1 | extended | 151 | 151 | Active (no notice found) | WATCH: 151, single source |
| C42431818 | JXTCONN PZ2.54-2X5P-H25 | J4 | 1 | extended | 37507 | 37507 | Active (no notice found) |  |
| C46970911 | RUILON SMD1812P350TF/16 | F1 | 1 | extended | 310 | 310 | Active (no notice found) | WATCH: 310; C20815 is 6 V (not equal) |

#### cpu

| LCSC | Maker / MPN | Refs | Qty/brd | JLC | Stock | Max sets | Lifecycle | Risk |
|---|---|---|---:|---|---:|---:|---|---|
| C1525 | Samsung Electro-Mechanics CL05B104KO5NNNC | C1..C9 | 17 | basic | 23742564 | 344095 | Mass production (Samsung) |  |
| C2286 | Hubei KENTO Elec KT-0603R | D1,D2 | 2 | basic | 3866603 | 175754 | Active (no notice found) |  |
| C11702 | UNI-ROYAL 0402WGF1001TCE | R10,R9 | 2 | basic | 8246998 | 824699 | Active (no notice found) |  |
| C20526 | Jiangsu Changjing MMBT3904(RANGE:100-300) | Q1 | 1 | basic | 284386 | 94795 | Active (no notice found) |  |
| C23733 | Samsung Electro-Mechanics CL05A475MP5NRNC | C15..C22 | 5 | basic | 2529551 | 505910 | Mass production (Samsung) |  |
| C25076 | UNI-ROYAL 0402WGF1000TCE | R6,R7 | 2 | basic | 4433259 | 2216629 | Active (no notice found) |  |
| C25501 | UNI-ROYAL 4D02WGJ0330TCE | RN1..RN8 | 8 | extended | 424328 | 53041 | Active (no notice found) |  |
| C25744 | UNI-ROYAL 0402WGF1002TCE | R1..R8 | 6 | basic | 22915369 | 1909614 | Active (no notice found) |  |
| C52923 | Samsung Electro-Mechanics CL05A105KA5NQNC | C21 | 1 | basic | 6175940 | 686215 | Mass production (Samsung) |  |
| C58464 | Richtek Tech RT9013-12GB | U3 | 1 | extended | 16181 | 8090 | Obsolete (Richtek EOL; DigiKey) | MUST-FIX pre-run: TLV75512PDBVR C2877864 |
| C179173 | Winbond Elec W25Q32JVSSIQ | U2 | 1 | extended | 21299 | 10649 | EOL: last order 2026-07-30, last ship 2027-01-30 (Winbond) | MUST-FIX pre-run: GD25Q32ESIGR C2832998 / W25Q32RVCSJQ C54442318 |
| C1521989 | Lattice ICE40HX4K-TQ144 | U1 | 1 | extended | 51 | 25 | Active (Lattice) | MUST-FIX: 51 JLC / 24 LCSC; reserve |

#### gpu

| LCSC | Maker / MPN | Refs | Qty/brd | JLC | Stock | Max sets | Lifecycle | Risk |
|---|---|---|---:|---|---:|---:|---|---|
| C1525 | Samsung Electro-Mechanics CL05B104KO5NNNC | C10..C9 | 13 | basic | 23742564 | 344095 | Mass production (Samsung) |  |
| C1562 | FH 0402CG330J500NT | C16,C17 | 2 | basic | 1084076 | 135509 | Active (no notice found) |  |
| C2040 | Raspberry Pi RP2040 | U1 | 1 | extended | 71492 | 14298 | Active (RPi: available to >= Jan 2041) |  |
| C2286 | Hubei KENTO Elec KT-0603R | D1 | 1 | basic | 3866603 | 175754 | Active (no notice found) |  |
| C4216 | UNI-ROYAL 0603WAF3302T5E | R27 | 1 | basic | 3287136 | 3287136 | Active (no notice found) |  |
| C8545 | Jiangsu Changjing 2N7002 | Q1,Q2 | 2 | basic | 1704908 | 568302 | Active (no notice found) |  |
| C9002 | YXC Crystal Oscillators X322512MSB4SI | Y1 | 1 | basic | 144325 | 28865 | Active (no notice found) |  |
| C11702 | UNI-ROYAL 0402WGF1001TCE | R1,R2 | 2 | basic | 8246998 | 824699 | Active (no notice found) |  |
| C15850 | Samsung Electro-Mechanics CL21A106KAYNNNE | C21 | 1 | basic | 5353625 | 1070725 | Mass production (Samsung) |  |
| C20976 | RUILON SMD0805P020TF | F1 | 1 | extended | 15876 | 15876 | Active (no notice found) |  |
| C21190 | UNI-ROYAL 0603WAF1001T5E | R4 | 1 | basic | 22836246 | 992880 | Active (no notice found) |  |
| C23024 | UNI-ROYAL 0603WAF3003T5E | R26 | 1 | basic | 586533 | 586533 | Active (no notice found) |  |
| C25744 | UNI-ROYAL 0402WGF1002TCE | R3 | 1 | basic | 22915369 | 1909614 | Active (no notice found) |  |
| C25768 | UNI-ROYAL 0402WGF2202TCE | R20 | 1 | basic | 876199 | 438099 | Active (no notice found) |  |
| C25779 | UNI-ROYAL 0402WGF3302TCE | R21 | 1 | basic | 1253161 | 1253161 | Active (no notice found) |  |
| C25879 | UNI-ROYAL 0402WGF2201TCE | R23,R25 | 2 | basic | 2425061 | 1212530 | Active (no notice found) |  |
| C25900 | UNI-ROYAL 0402WGF4701TCE | R22,R24 | 2 | basic | 15885507 | 7942753 | Active (no notice found) |  |
| C45783 | Samsung Electro-Mechanics CL21A226MAQNNNE | C2,C22,C23 | 3 | basic | 4151070 | 276738 | NRND (Samsung) | WATCH: CL21A226MAYNNNE C602037 |
| C52923 | Samsung Electro-Mechanics CL05A105KA5NQNC | C11,C14 | 2 | basic | 6175940 | 686215 | Mass production (Samsung) |  |
| C131025 | Winbond Elec W25Q16JVSSIQ | U3 | 1 | extended | 13371 | 2674 | EOL: last order 2026-04-30, last ship 2026-07-30 (Winbond) | MUST-FIX pre-run: GD25Q16ESIGR C2922792 / W25Q16RV |
| C138714 | Texas Instruments TPD4E05U06DQAR | U5,U6 | 2 | extended | 166122 | 27687 | Active (TI) |  |
| C167200 | cjiang FXL0420-R47-M | L1 | 1 | extended | 9433 | 9433 | Active (no notice found) |  |
| C182716 | UNI-ROYAL 4D03WGJ0361T5E | RN1,RN2 | 2 | extended | 4617 | 2308 | Active (no notice found) |  |
| C2845237 | Texas Instruments TPS63802DLAR | U7 | 1 | extended | 17825 | 17825 | Active (TI) |  |
| C2858275 | SHOU HAN HDMI 19PIN 043 | J2 | 1 | extended | 66262 | 66262 | Active (no notice found) |  |
| C52140430 | MDD 74LVC1G125GW | U4 | 1 | extended | 8988 | 1797 | Active (no notice found) |  |

#### io

| LCSC | Maker / MPN | Refs | Qty/brd | JLC | Stock | Max sets | Lifecycle | Risk |
|---|---|---|---:|---|---:|---:|---|---|
| C1525 | Samsung Electro-Mechanics CL05B104KO5NNNC | C10..C9 | 13 | basic | 23742564 | 344095 | Mass production (Samsung) |  |
| C1562 | FH 0402CG330J500NT | C16,C17 | 2 | basic | 1084076 | 135509 | Active (no notice found) |  |
| C2040 | Raspberry Pi RP2040 | U1 | 1 | extended | 71492 | 14298 | Active (RPi: available to >= Jan 2041) |  |
| C2286 | Hubei KENTO Elec KT-0603R | D1,D2 | 2 | basic | 3866603 | 175754 | Active (no notice found) |  |
| C7519 | STMicroelectronics USBLC6-2SC6 | U6 | 1 | extended | 44473 | 14824 | Active (ST) |  |
| C9002 | YXC Crystal Oscillators X322512MSB4SI | Y1 | 1 | basic | 144325 | 28865 | Active (no notice found) |  |
| C11702 | UNI-ROYAL 0402WGF1001TCE | R1,R2 | 2 | basic | 8246998 | 824699 | Active (no notice found) |  |
| C12624 | Hubei KENTO Elec KT-0603G | D3 | 1 | extended | 345532 | 38392 | Active (no notice found) |  |
| C15008 | Samsung Electro-Mechanics CL31A107MQHNNNE | C21 | 1 | basic | 2045425 | 2045425 | Mass production (Samsung) |  |
| C15850 | Samsung Electro-Mechanics CL21A106KAYNNNE | C20 | 1 | basic | 5353625 | 1070725 | Mass production (Samsung) |  |
| C21190 | UNI-ROYAL 0603WAF1001T5E | R4,R5 | 2 | basic | 22836246 | 992880 | Active (no notice found) |  |
| C22775 | UNI-ROYAL 0603WAF1000T5E | R6 | 1 | basic | 12047811 | 1095255 | Active (no notice found) |  |
| C23240 | UNI-ROYAL 0603WAF7503T5E | R16 | 1 | extended (pref) | 311778 | 311778 | Active (no notice found) |  |
| C25100 | UNI-ROYAL 0402WGF270JTCE | R14,R15 | 2 | extended | 58089 | 29044 | Active (no notice found) |  |
| C25741 | UNI-ROYAL 0402WGF1003TCE | R11 | 1 | basic | 9424591 | 9424591 | Active (no notice found) |  |
| C25744 | UNI-ROYAL 0402WGF1002TCE | R3 | 1 | basic | 22915369 | 1909614 | Active (no notice found) |  |
| C25752 | UNI-ROYAL 0402WGF1202TCE | R10 | 1 | basic | 1151183 | 1151183 | Active (no notice found) |  |
| C25756 | UNI-ROYAL 0402WGF1502TCE | R12 | 1 | basic | 1207933 | 1207933 | Active (no notice found) |  |
| C25768 | UNI-ROYAL 0402WGF2202TCE | R13 | 1 | basic | 876199 | 438099 | Active (no notice found) |  |
| C25803 | UNI-ROYAL 0603WAF1003T5E | R17 | 1 | basic | 22562923 | 4512584 | Active (no notice found) |  |
| C45783 | Samsung Electro-Mechanics CL21A226MAQNNNE | C2,C23,C24 | 3 | basic | 4151070 | 276738 | NRND (Samsung) | WATCH: CL21A226MAYNNNE C602037 |
| C52923 | Samsung Electro-Mechanics CL05A105KA5NQNC | C11,C14 | 2 | basic | 6175940 | 686215 | Mass production (Samsung) |  |
| C55136 | Silergy Corp SY6280AAC | U5 | 1 | extended | 137219 | 137219 | Active (no notice found) |  |
| C112455 | SOFNG USB-302S-T | J2 | 1 | extended | 3777 | 3777 | Active (no notice found) |  |
| C131025 | Winbond Elec W25Q16JVSSIQ | U3 | 1 | extended | 13371 | 2674 | EOL: last order 2026-04-30, last ship 2026-07-30 (Winbond) | MUST-FIX pre-run: GD25Q16ESIGR C2922792 / W25Q16RV |
| C167203 | cjiang FXL0420-1R0-M | L1 | 1 | extended | 112188 | 112188 | Active (no notice found) |  |
| C919459 | Texas Instruments TPS61023DRLR | U7 | 1 | extended | 46748 | 46748 | Active (TI) |  |
| C52140430 | MDD 74LVC1G125GW | U4 | 1 | extended | 8988 | 1797 | Active (no notice found) |  |

#### storage

| LCSC | Maker / MPN | Refs | Qty/brd | JLC | Stock | Max sets | Lifecycle | Risk |
|---|---|---|---:|---|---:|---:|---|---|
| C1525 | Samsung Electro-Mechanics CL05B104KO5NNNC | C10..C9 | 13 | basic | 23742564 | 344095 | Mass production (Samsung) |  |
| C1562 | FH 0402CG330J500NT | C16,C17 | 2 | basic | 1084076 | 135509 | Active (no notice found) |  |
| C2040 | Raspberry Pi RP2040 | U1 | 1 | extended | 71492 | 14298 | Active (RPi: available to >= Jan 2041) |  |
| C2286 | Hubei KENTO Elec KT-0603R | D1 | 1 | basic | 3866603 | 175754 | Active (no notice found) |  |
| C9002 | YXC Crystal Oscillators X322512MSB4SI | Y1 | 1 | basic | 144325 | 28865 | Active (no notice found) |  |
| C11702 | UNI-ROYAL 0402WGF1001TCE | R1,R2 | 2 | basic | 8246998 | 824699 | Active (no notice found) |  |
| C12624 | Hubei KENTO Elec KT-0603G | D2,D3 | 2 | extended | 345532 | 38392 | Active (no notice found) |  |
| C15850 | Samsung Electro-Mechanics CL21A106KAYNNNE | C20 | 1 | basic | 5353625 | 1070725 | Mass production (Samsung) |  |
| C21190 | UNI-ROYAL 0603WAF1001T5E | R4 | 1 | basic | 22836246 | 992880 | Active (no notice found) |  |
| C22775 | UNI-ROYAL 0603WAF1000T5E | R5,R6 | 2 | basic | 12047811 | 1095255 | Active (no notice found) |  |
| C25744 | UNI-ROYAL 0402WGF1002TCE | R20,R21,R3 | 3 | basic | 22915369 | 1909614 | Active (no notice found) |  |
| C29718 | UNI-ROYAL 4D03WGJ0103T5E | RN1 | 1 | basic | 2241144 | 2241144 | Active (no notice found) |  |
| C45783 | Samsung Electro-Mechanics CL21A226MAQNNNE | C2 | 1 | basic | 4151070 | 276738 | NRND (Samsung) | WATCH: CL21A226MAYNNNE C602037 |
| C52923 | Samsung Electro-Mechanics CL05A105KA5NQNC | C11,C14 | 2 | basic | 6175940 | 686215 | Mass production (Samsung) |  |
| C91145 | Korean Hroparts Elec TF-01A | J2 | 1 | extended | 204074 | 204074 | Active (no notice found) |  |
| C131025 | Winbond Elec W25Q16JVSSIQ | U3 | 1 | extended | 13371 | 2674 | EOL: last order 2026-04-30, last ship 2026-07-30 (Winbond) | MUST-FIX pre-run: GD25Q16ESIGR C2922792 / W25Q16RV |
| C138714 | Texas Instruments TPD4E05U06DQAR | U5,U6 | 2 | extended | 166122 | 27687 | Active (TI) |  |
| C52140430 | MDD 74LVC1G125GW | U4 | 1 | extended | 8988 | 1797 | Active (no notice found) |  |

#### wifi

| LCSC | Maker / MPN | Refs | Qty/brd | JLC | Stock | Max sets | Lifecycle | Risk |
|---|---|---|---:|---|---:|---:|---|---|
| C2286 | Hubei KENTO Elec KT-0603R | D1 | 1 | basic | 3866603 | 175754 | Active (no notice found) |  |
| C12624 | Hubei KENTO Elec KT-0603G | D2,D3,D4 | 3 | extended | 345532 | 38392 | Active (no notice found) |  |
| C14663 | YAGEO CC0603KRX7R9BB104 | C3,C4 | 2 | basic | 57465769 | 1008171 | Active (no notice found) |  |
| C15849 | Samsung Electro-Mechanics CL10A105KB8NNNC | C5 | 1 | basic | 6621857 | 945979 | Mass production (Samsung) |  |
| C21190 | UNI-ROYAL 0603WAF1001T5E | R5 | 1 | basic | 22836246 | 992880 | Active (no notice found) |  |
| C22775 | UNI-ROYAL 0603WAF1000T5E | R6,R7,R8 | 3 | basic | 12047811 | 1095255 | Active (no notice found) |  |
| C25804 | UNI-ROYAL 0603WAF1002T5E | R1,R2,R3,R4 | 4 | basic | 22069577 | 469565 | Active (no notice found) |  |
| C45783 | Samsung Electro-Mechanics CL21A226MAQNNNE | C1,C2 | 2 | basic | 4151070 | 276738 | NRND (Samsung) | WATCH: CL21A226MAYNNNE C602037 |
| C122538 | YAGEO RT0603BRD07100KL | R10 | 1 | extended | 1228110 | 1228110 | Active (YAGEO RT) |  |
| C141836 | Texas Instruments TLV62569DBVR | U2 | 1 | extended | 237268 | 237268 | Active (TI) |  |
| C167747 | cjiang FNR3015S2R2MT | L1 | 1 | extended | 50427 | 50427 | Active (no notice found) |  |
| C861412 | YAGEO RT0603BRD07453KL | R9 | 1 | extended | 7451 | 3725 | Active (YAGEO RT) |  |
| C2911374 | Espressif Systems ESP32-C3-MINI-1U-N4 | U1 | 1 | extended | 2206 | 2206 | NRND (Espressif) | WATCH: ESP32-C3-MINI-1U-N4X C49230958 (0 at JLC today) |
| C52140430 | MDD 74LVC1G125GW | U3 | 1 | extended | 8988 | 1797 | Active (no notice found) |  |

#### eink

| LCSC | Maker / MPN | Refs | Qty/brd | JLC | Stock | Max sets | Lifecycle | Risk |
|---|---|---|---:|---|---:|---:|---|---|
| C1525 | Samsung Electro-Mechanics CL05B104KO5NNNC | C10..C9 | 13 | basic | 23742564 | 344095 | Mass production (Samsung) |  |
| C1562 | FH 0402CG330J500NT | C16,C17 | 2 | basic | 1084076 | 135509 | Active (no notice found) |  |
| C2040 | Raspberry Pi RP2040 | U1 | 1 | extended | 71492 | 14298 | Active (RPi: available to >= Jan 2041) |  |
| C2286 | Hubei KENTO Elec KT-0603R | D1 | 1 | basic | 3866603 | 175754 | Active (no notice found) |  |
| C9002 | YXC Crystal Oscillators X322512MSB4SI | Y1 | 1 | basic | 144325 | 28865 | Active (no notice found) |  |
| C11702 | UNI-ROYAL 0402WGF1001TCE | R1,R2 | 2 | basic | 8246998 | 824699 | Active (no notice found) |  |
| C12624 | Hubei KENTO Elec KT-0603G | D2 | 1 | extended | 345532 | 38392 | Active (no notice found) |  |
| C15850 | Samsung Electro-Mechanics CL21A106KAYNNNE | C20 | 1 | basic | 5353625 | 1070725 | Mass production (Samsung) |  |
| C20975 | RUILON SMD0805P010TF | F1 | 1 | extended | 47481 | 47481 | Active (no notice found) |  |
| C21190 | UNI-ROYAL 0603WAF1001T5E | R4 | 1 | basic | 22836246 | 992880 | Active (no notice found) |  |
| C22775 | UNI-ROYAL 0603WAF1000T5E | R5 | 1 | basic | 12047811 | 1095255 | Active (no notice found) |  |
| C23140 | UNI-ROYAL 0603WAF330JT5E | R10..R16 | 7 | basic | 5724795 | 106014 | Active (no notice found) |  |
| C25744 | UNI-ROYAL 0402WGF1002TCE | R3 | 1 | basic | 22915369 | 1909614 | Active (no notice found) |  |
| C45783 | Samsung Electro-Mechanics CL21A226MAQNNNE | C2 | 1 | basic | 4151070 | 276738 | NRND (Samsung) | WATCH: CL21A226MAYNNNE C602037 |
| C52923 | Samsung Electro-Mechanics CL05A105KA5NQNC | C11,C14 | 2 | basic | 6175940 | 686215 | Mass production (Samsung) |  |
| C131025 | Winbond Elec W25Q16JVSSIQ | U3 | 1 | extended | 13371 | 2674 | EOL: last order 2026-04-30, last ship 2026-07-30 (Winbond) | MUST-FIX pre-run: GD25Q16ESIGR C2922792 / W25Q16RV |
| C138714 | Texas Instruments TPD4E05U06DQAR | U5,U6 | 2 | extended | 166122 | 27687 | Active (TI) |  |
| C492417 | XFCN PZ254R-11-09P | J2 | 1 | extended | 2287 | 2287 | Active (no notice found) |  |
| C52140430 | MDD 74LVC1G125GW | U4 | 1 | extended | 8988 | 1797 | Active (no notice found) |  |

#### system

| LCSC | Maker / MPN | Refs | Qty/brd | JLC | Stock | Max sets | Lifecycle | Risk |
|---|---|---|---:|---|---:|---:|---|---|
| C1663 | Samsung Electro-Mechanics CL10C330JB8NNNC | C15,C16 | 2 | basic | 1015271 | 507635 | Mass production (Samsung) |  |
| C2040 | Raspberry Pi RP2040 | U1 | 1 | extended | 71492 | 14298 | Active (RPi: available to >= Jan 2041) |  |
| C2286 | Hubei KENTO Elec KT-0603R | D1 | 1 | basic | 3866603 | 175754 | Active (no notice found) |  |
| C7519 | STMicroelectronics USBLC6-2SC6 | U3 | 1 | extended | 44473 | 14824 | Active (ST) |  |
| C8545 | Jiangsu Changjing 2N7002 | Q1 | 1 | basic | 1704908 | 568302 | Active (no notice found) |  |
| C9002 | YXC Crystal Oscillators X322512MSB4SI | Y1 | 1 | basic | 144325 | 28865 | Active (no notice found) |  |
| C12624 | Hubei KENTO Elec KT-0603G | D2,D3 | 2 | extended | 345532 | 38392 | Active (no notice found) |  |
| C14663 | YAGEO CC0603KRX7R9BB104 | C1..C9 | 11 | basic | 57465769 | 1008171 | Active (no notice found) |  |
| C15849 | Samsung Electro-Mechanics CL10A105KB8NNNC | C12,C13 | 2 | basic | 6621857 | 945979 | Mass production (Samsung) |  |
| C15850 | Samsung Electro-Mechanics CL21A106KAYNNNE | C14 | 1 | basic | 5353625 | 1070725 | Mass production (Samsung) |  |
| C21190 | UNI-ROYAL 0603WAF1001T5E | R1,R6,R9 | 3 | basic | 22836246 | 992880 | Active (no notice found) |  |
| C22775 | UNI-ROYAL 0603WAF1000T5E | R20,R21 | 2 | basic | 12047811 | 1095255 | Active (no notice found) |  |
| C23140 | UNI-ROYAL 0603WAF330JT5E | R11..R19 | 9 | basic | 5724795 | 106014 | Active (no notice found) |  |
| C23186 | UNI-ROYAL 0603WAF5101T5E | R4,R5 | 2 | basic | 25815276 | 6453819 | Active (no notice found) |  |
| C25190 | UNI-ROYAL 0603WAF270JT5E | R2,R3 | 2 | extended (pref) | 113206 | 56603 | Active (no notice found) |  |
| C25803 | UNI-ROYAL 0603WAF1003T5E | R22 | 1 | basic | 22562923 | 4512584 | Active (no notice found) |  |
| C25804 | UNI-ROYAL 0603WAF1002T5E | R10,R23,R7,R8 | 4 | basic | 22069577 | 469565 | Active (no notice found) |  |
| C131025 | Winbond Elec W25Q16JVSSIQ | U2 | 1 | extended | 13371 | 2674 | EOL: last order 2026-04-30, last ship 2026-07-30 (Winbond) | MUST-FIX pre-run: GD25Q16ESIGR C2922792 / W25Q16RV |
| C165948 | Korean Hroparts Elec TYPE-C-31-M-12 | J1 | 1 | extended | 446368 | 223184 | Active (no notice found) |  |


## Sources

- JLC parts API (`selectSmtComponentList`) and LCSC `wmsc.lcsc.com/ftps/wm/product/detail`, 2026-09-28: stock, library type, prices (recorded JSON).
- Samsung product pages, product.samsungsem.com/mlcc/<PN>.do: CL21A226MAQNNN "NRND", CL21A226MAYNNN and the other eight Samsung MLCCs "Mass Production".
- Winbond Product Obsolescence Notices, table 1260-0009-02-A: W25Q16JV (notified 2026-01-30, last order 2026-04-30, last ship 2026-07-30; replacement W25Q16RV) and W25Q32JV (last order 2026-07-30, last ship 2027-01-30; replacement W25Q32RV), via [DigiKey](https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/8958/EOL_W25Q32JV.pdf) and [Anglia](https://www.anglia.com/registration/pcn_ptn/docs/ptn/PTNW25Q16J280126.pdf).
- Espressif ESP32-C3-MINI-1/1U datasheet, Table 1-2: -1U-N4 / -1U-H4 NRND, -1U-N4X / -1U-H4X recommended.
- Richtek RT9013 product page (EOL) and DigiKey RT9013-12GB (Obsolete): `cpu-ldo-replacement.md`.
- Holtek HT7530/33/36/44/50 EOL notification (2002-11-29): suffix-less parts only.
- TI product pages (Active) for SN74LVC07A, TPD4E05U06, TLV62569 (DBV, DDC), CD74HC4051, TCA9555, TLV7011, TPS259470A, TPS61023, TPS63802, REF3425; OPA376 Active per TI listing but its status field was not read directly. ADI MAX811T / MAX16054A: "Production" via Octopart (analog.com not read). ST USBLC6-2SC6, onsemi BAT54ALT1G: active. Raspberry Pi: RP2040 available until at least January 2041. Lattice: iCE40 HX4K TQ144 active (the iCE40 discontinuance PCN covers other devices). Microchip SST39VF040/VF010: in production (microchip.com blocked the fetch; distributor listings).
- Parts with no lifecycle publication (UNI-ROYAL, KENTO, CJ, RUILON, PTTC, cjiang, TAI-TECH, UMAX, Sofng, HRO, SHOU HAN, XKB, XFCN, JXTCONN, MDD, YXC, HELE): recorded as "Active (no notice found)"; stock is the only signal.
