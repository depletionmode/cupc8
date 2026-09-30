# Wi-Fi power diagnosis, 2026-09-30

The fresh staged board at `/tmp/cupc8-canonical-rebuild-20260930/wifi`
completed its physical pipeline, but receipt generation correctly rejected a
new parts-cache entry appearing during the build. These results are explicitly
**diagnostic**, pending root's fresh pipeline after the shared cache freezes.
No Wi-Fi board, capacitor, ground route, or shared pipeline source was changed.

## Existing circuit and source limits

The accepted 0.1% 453k/100k divider is fitted, as are Samsung C602037 input
and output capacitors. The modeled DC range is 3.226659–3.410548 V. Stress
capacitance with tolerance, typical bias loss, temperature and life drift is
5.220/7.990/0.0765 µF for C1/C2/C3. Published bias and ESR curves are typical,
so these are engineering scenarios requiring first-article qualification.

The [Espressif module datasheet v2.2](https://documentation.espressif.com/esp32-c3-mini-1_datasheet_en.pdf)
specifies a 3.0–3.6 V operating range, supply capability of at least 0.5 A,
and a 350 mA peak at 25 C for 802.11b/20.5 dBm at full duty. The existing
358.3 mA scenario includes LEDs and pull-ups. The 508.3 mA scenario tests the
0.5 A supply capability plus those loads; it does not turn the supply
capability into a guaranteed maximum ESP load.

## Fresh routed diagnostic

The source-bound netlist, fitted LCSC parts and completed DRC match the
existing model. Shortest-path +5V/3V3 resistance scenarios are 34.95/132.19
mOhm. Fixed-width GND path is 158.61 mOhm and J1 return 66.55 mOhm. Ground
mesh discrepancies are 2.4%, with return discrepancies at most 3.2%.

| Scenario, low slot source | ESP minimum | ESP maximum |
| --- | ---: | ---: |
| 358.3 mA, 60% caps, 3 mOhm ESR | 3.121 V | 3.471 V |
| 358.3 mA, stress caps, 3 mOhm ESR | 3.111 V | 3.510 V |
| 508.3 mA, stress caps, 3 mOhm ESR | 3.050 V | 3.506 V |
| 358.3 mA, stress caps, 100 mOhm ESR | 3.125 V | 3.546 V |

All are within 3.0–3.6 V. Scratch executable and output:
`/tmp/cupc8-resume-wifi-20260930/diagnostic.py`, `diagnostic.log`,
`diagnostic.json`. The vendor model's internal global ground remains U2 GND;
the previously corrected deck-ground artifact has not been reintroduced.

Additional combined stress at 508.3 mA, 3/100 mOhm ESR, and 4.75/5.5 V
source also passes: lowest ESP supply 3.049683 V, highest 3.554445 V.
Explicit buck-node maximum is 3.561534 V, with a 5.5 V source giving at most
3.529677 V. Executable/log: `buffer-supply.py`, `buffer-supply.log` in the
same scratch directory. The buck-node reading is relative to U2 GND; it is
not automatically the voltage across the MISO buffer's physical supply pads.

**No capacitor or ground repair is justified by these diagnostic results.**
The remaining supplier/assembly/load coverage gates F5–F8 require the agreed
first-article measurements, including full TX at 40 C. They do not establish
a present physical droop failure. The original module's internal decoupling
was not added to the scenario, preserving the existing conservative load model.

## MISO buffer supply identity

| Card | Buffer supply pad | Actual source |
| --- | --- | --- |
| GPU, IO, storage, eink | U4.5, `/3V3` | Main 3V3 through J1 A4/B4 |
| Wi-Fi | U3.5, `/3V3` | Local TLV62569 output at L1.2; no J1 pin on this net |

This comes directly from the five freshly staged netlists and board source.
Main POW-001 existing model waves reach 3.421924 V after the DC-high scaling;
the broader valid operating ceiling is 3.465 V. Wi-Fi's local modeled
transient can reach roughly 3.56 V in the combined stress above. These
identities were passed to the SI reviewer; using one supply for all five
MISO drivers would be incorrect. No assumption about rescaling IBIS curves
is made here.

## SPI interrupt cache safety: 2026-09-30 continuation

The actual pinned ESP-IDF 5.5.5 card image initially placed `frames_received`
and `frames_preload` at flash addresses 0x4200b022 and 0x4200b116. Merely setting
`CONFIG_SPI_SLAVE_ISR_IN_IRAM=y` placed the driver in RAM but did not make its
callbacks safe. The bus also omitted `ESP_INTR_FLAG_IRAM`, so its interrupt
was suspended while flash cache was disabled, including saved network-setting
NVS writes. Such writes can exceed the protocol's 20 us interframe allowance.

The two frame helpers and their `put` callee now use `IRAM_ATTR`; the bus
requests `ESP_INTR_FLAG_IRAM`. The interface requests
`SPI_SLAVE_NO_RETURN_RESULT`, since completion is consumed exclusively by the
callback, rather than filling an unused two-element return queue. This matches
the pinned IDF's ISR-transfer documentation and cache-disabled SPI-slave test.
The source arms one initial descriptor, then alternates descriptors from its
completion callback; it does not prequeue two transactions.

The real card image builds successfully. Actual ELF disassembly confirms:

| Function | Address |
| --- | --- |
| put | 0x403818fe |
| frames_received | 0x40381914 |
| frames_preload | 0x40381a18 |
| arm | 0x40381a96 |
| done | 0x40381b00 |
| spi_slave_queue_trans_isr | 0x40382954 |
| memcpy called by helpers | 0x4038ef02 |
| memset called by arm (ROM) | 0x40000354 |

Direct helper calls to critical-section and ISR-context functions also resolve
inside RAM. Build/disassembly evidence is in `/tmp/cupc8-wifi-iram-build.log`
and `/tmp/cupc8-wifi-iram-disassembly.txt`. This removes a specific cache-service
failure mechanism; it does not prove a worst-case 20 us response bound, GPIO5
matrix MISO propagation, or silicon SPI operation. Physical saved-NET_CONFIG
writes during minimum-gap polling remain required in the first-article plan.

The QEMU variant also builds and its merged image is regenerated. WIFI-003
runtime verification was attempted but stops before any scenario: the managed
environment rejects even creating a local socket (`PermissionError: EPERM`).
This is not a passing test or a firmware failure. Log:
`/tmp/cupc8-wifi-iram-qemu-test.log`. No alternate transport or sandbox bypass
was substituted for this requirement.

The same actual ELF exposed a second latency problem: per-byte ring `put()`
calls and a 512-byte scalar zeroing loop inside the ISR. The frame queue now
uses at most two RAM memcpy calls, handling wrap without a per-byte function
call. Preload tail clearing uses ROM memset. Final direct-call/address proof
binds the ELF SHA in `/tmp/cupc8-wifi-iram-final-evidence.json`.

`python3 -m unittest test.test_wifi_frames` passes with ASan/UBSan. It executes
the real queue against observed replay bytes, forces both a two-byte header
wrap and payload wrap, preserves order over 3000 varied frames, rejects full-
queue/oversize frames without corrupting pending frames, and verifies preload
suppression. Omitting the wrapped remainder memcpy is a verified failing
counterexample. Only platform attributes/critical primitives are stubbed;
this test does not measure silicon timing or concurrent ISR/task execution.
