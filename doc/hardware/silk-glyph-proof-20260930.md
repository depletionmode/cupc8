# Independent plotted glyph-height coverage

The release requirement is `doc/hardware/verification.md` §4.9: delivered
Gerbers must be reimported and checked with DRC. The existing source rule for
visible silkscreen text is at least 0.8 mm. No new waiver or lower minimum is
proposed.

Gerber does not identify text separately from graphics. Coverage therefore
uses the complete source UUID inventory, with the saved PCB already bound by
receipt and exact whole-board export parity to the delivered Gerbers. It then
independently verifies every inventory object's actual plotted glyph geometry.

The proof reads the installed font's exported `newstroke_font` data table;
it does not invoke the font renderer, `GetEffectiveTextShape`, or another text
export. Its own decoder maps encoded glyph vertices to the documented 21-unit
font scale. The format and units are described in the primary
[KiCad 10.0.6 font loader](https://gitlab.com/kicad/code/kicad/-/raw/10.0.6/common/font/stroke_font.cpp).
The table SHA is reported, so the font data used in the proof is inspectable.

The delivered Gerber is first fully validated by the independent geometry
parser. A separate parser extracts actual stroke endpoints and aperture widths.
Source identity supplies only the literal glyph sequence, orientation, mirror
state and search location. Least squares fits independent horizontal/vertical
scales to the delivered endpoint pattern; the vertical scale is the measured
font height. Every visible UUID needs exactly one full pattern match, with no
stroke consumed by two identities. Missing/moved/incomplete patterns and
unsupported styles/fonts fail closed.

Gerber 4.6 millimetre coordinates have one-nanometre resolution. The fixed
three-nanometre tolerance accounts for quantization and native integer cursor
rounding; it is not proportional to the design minimum. Nominal source height
must still meet the exact configured rule, and measured font dimensions must
agree with the source within that same fixed bound.

A horizontal-only '-' has no observable vertical scale; it remains an exact
blocker, rather than being assigned an invented height. None of the current
eight plotted boards contains an unsupported/unmeasurable visible object.

Current scratch evidence: main 388, CPU 53, GPU 59, Storage 49, WiFi 30, EInk 61,
System 59 visible objects independently proved. Root independently proved IO's
59 actual plotted objects in its final development package; the report remains
development-only until a completed current receipt exists. Thus all eight
actual text inventories are covered. Eight actual KiCad export tests prove small/missing/moved glyph rejection,
ambiguous overlap rejection, unsupported-style rejection, the horizontal-only
counterexample, and rotated mirrored back text at the configured minimum.

This is design-source-bound plotted DRC coverage. It neither approves a CPL
human review nor creates a receipt, manufacturing pass, or electrical waiver.
