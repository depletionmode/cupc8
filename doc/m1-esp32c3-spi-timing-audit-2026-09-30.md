# M1 ESP32-C3 SPI timing audit — 2026-09-30

## Qualification conclusion

Actual firmware uses SPI2 slave, mode 0, DMA, at the host's qualified 3 MHz. The available exact C3 sources establish supported operation and CS framing requirements. They do **not** supply a numerical guaranteed external-pad MOSI setup/hold or SCK-to-MISO delay sufficient to close our routed cascade timing calculation. Preserve the explicit ESP response/timing unknown; measure the final interface on first articles. The successful isolated analog edge studies do not close this gap.

## Actual implementation

`fw/wifi/port/esp32c3/main/transport_spi.c` uses SCK GPIO6, MOSI GPIO7, CS GPIO10 and MISO GPIO5. Dedicated SPI2 MISO is GPIO2; the pinned 5.5.5 driver consequently routes the bus through the GPIO matrix. Descriptors cover 512 aligned DMA bytes; the host determines shorter actual lengths. Only descriptor 0 is initially queued; the completion callback consumes the actual byte count, prepares and queues the alternate descriptor. IRAM registration and floating input pulls are explicit. Queue depth two does not prove two transactions are prearmed or guarantee the 20 µs rearm deadline.

The [C3 IDF v5.5 guide](https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32c3/api-reference/peripherals/spi_slave.html) states a 60 MHz slave clock limit, requires 50% duty, and describes GPIO-matrix equivalence below 80 MHz. These functional limits are not a worst-case pad delay specification. Its transaction discussion permits the host to finish before the descriptor length and reports the actual transferred length. Its DMA warning also requires host lengths divisible by four, creating the discrepancy discussed below.

The old 43.75/68.75 ns MISO output-delay table and DMA mode-1/3 restriction are inside the pinned documentation's `only:: esp32` block. They are not ESP32-C3 guarantees and were not imported into our timing checker.

## CS framing and real host scope

The [ESP32-C3 TRM v1.4, §27.6–27.8](https://documentation.espressif.com/esp32-c3_technical_reference_manual_en.pdf) requires CS assertion to first latch edge and last latch edge to release each exceed half a clock period. At 3 MHz this is 166.667 ns. It describes mode-0 falling-edge launch/rising-edge sampling and APB-cycle timing controls, without giving the required guaranteed pad AC delays.

ROM `cs_on` and kernel `net_cs_on` explicitly store the held-CS register before returning through `pop pcl` and `pop pch`; SPI start follows the return and additional instructions. Even allowing one distinct 12 MHz clock per retirement, the two return instructions plus the SPI engine's two-clock first-edge delay give a conservative 333.333 ns source-side lead. Receiver CS/SCK cascade and routing skew must be subtracted from that bound using final actual studies. An unheld automatic SPI start has only one half-period source lead and is not independently qualified by this argument.

At mode-0 byte completion the engine's final rising latch precedes its final falling edge and extra done half-period, giving 333.333 ns before automatic release; explicit `cs_off` follows completion polling and returns. Subtract actual CS/SCK differential delay for the received hold proof. This argument applies to the audited ROM/kernel held-CS paths, not arbitrary future direct-register software.

## DMA tail: explicit unresolved documentation conflict

The actual boot probe sends one IDENT byte and the READ path sends variable lengths, including six bytes. The pinned 5.5.5 driver explicitly allows byte-aligned DMA descriptor lengths on non-ESP32 targets and comments that those peripherals can stop DMA without overwriting a partial word. Our 512-byte descriptor meets its alignment checks. C3 `spi_ll_slave_init` sets `rx_eof_en=0`, selecting transaction/CS-driven completion; the HAL reads `slave1.data_bitlen` and reports the actual received bit length. Neither the completion count nor safe memory bounds alone demonstrates that all final 1–3 payload bytes were flushed to memory.

Thus this source evidence supports byte framing but does not resolve the generic guide's discard warning with a silicon proof. Do not label boot broken from the generic warning alone and do not silently pad the protocol. Required first-article test: exercise IDENT and READ, then every frame length modulo four at 3 MHz; compare received final bytes and `trans_len`, including repeated ring wrap and NVS/cache-disabled operation. A pinned C3 hardware test or explicit vendor clarification is needed before claiming the tail behavior qualified.

## Required final timing observations

On final actual native geometry, simulate eight 3 MHz clock pulses with the genuine corners and explicit local ESP rail thresholds. Check unchanged receiver stress/edge requirements throughout every pulse, measure actual high/low intervals and cascaded CS/SCK skew, and anchor TI package delay to the published fixture. Do not replace these with the prior 1.5 MHz isolated rise/fall fixtures. Numerical ESP setup/hold/response and worst ISR rearm remain separate silicon measurements, not invented values derived from the 60 MHz headline.

Source hashes for this audit: `build/scratch-si/esp32c3-spi-timing-audit-20260930/source-hashes.json`. No firmware, framing, electrical threshold or timing gate was changed by this audit.

## Genuine host execution proof

The release owner additionally ran the authentic ROM/kernel/BASIC through a fresh isolated GHDL synthesis and Verilator/native model. `build/host-spi-real-timing-20260930/qualification.json` and `boot-trace.json` bind twelve real boot frames containing 3 MHz eight-clock bytes: minimum observed CS lead 12.250 µs and hold after the last sample 16.083 µs. These observations support the audited host sequence; final analog receiver skew remains to be subtracted. They do not resolve C3 silicon DMA tails or unpublished pad timing.
