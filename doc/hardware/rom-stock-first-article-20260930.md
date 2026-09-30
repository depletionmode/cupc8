# First-article ROM stock and packaging replacement

The fresh live combined order check queried all 118 exact SKUs for two
assembled boards of each of eight types. 117 passed the existing two-times
combined-demand margin. C645939 alone failed: two Main boards need two ROMs,
so the margin requires four available; JLC reported three.

The live search and subsequent exact query identify C632854 with nine in
stock. Its MPN is SST39VF040-70-4I-NHE-T; the original is
SST39VF040-70-4I-NHE. Microchip DS20005023E page28 identifies the final T as
shipping carrier tape-and-reel, with blank meaning tube/tray. Capacity,
70ns access, industrial temperature range and PLCC-32 package are unchanged.
This is a packaging substitution, not the older reduced-capacity 128KB fallback.

Genuine exact supplier CAD compared against current Main U10 and CPL passes
all32 numbered pads and pin functions, maximum center deviation0.1625mm
within the unchanged0.2mm review limit. No footprint movement, trace change,
new routing or ROM software change is required by that comparison.

The substitution is qualified for adoption into the final Main source/BOM.
It is not yet a newly built final package or reservation. Adopt legitimate
part/cache/rotation records, run the normal builder and compare actual pads,
copper, fills and CPL to the previous Main; then rerun live combined demand
against the final genuine package set. Preserve the original shortage report.

Evidence: `build/spi-development-working-m1-firstarticle-20260930/fresh-live-aggregate-stock.json`,
`build/placement-exact-gap-research-20260930/C632854-main-U10-qualification.json`,
`authentic-cache-origin.json` and `jlc-records/C632854-5.json`.

Primary source: [Microchip DS20005023E](https://ww1.microchip.com/downloads/aemDocuments/documents/MPD/ProductDocuments/DataSheets/SST39LF010-SST39LF020-SST39LF040-SST39VF010-SST39VF020-SST39VF040-Data-Sheet-DS20005023.pdf).
The local official PDF and exact source hashes are retained with the CAD review.
