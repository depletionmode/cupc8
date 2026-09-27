# Plotted silkscreen text height

The current KiCad 10.0.6 Gerber exports cannot independently certify the
minimum *nominal text height* from the Gerber files alone. The eight current
`F_Silkscreen.gto` layers have no `.FlashText` attribution or text-size field.
Their `%TO.C` attributes identify a component, not individual text objects.
The plotted ink consists of apertures, strokes, and regions.

This is information loss, not a missing glyph-recognition algorithm. The
`test_silk_text_and_graphic_can_have_identical_plot_commands` fixture plots a
KiCad `PCB_TEXT` dash with nominal height 0.8 mm and an ordinary `PCB_SHAPE`
line. After the file header, KiCad emits identical aperture and draw commands
for both. Thus a checker receiving either Gerber sees the same input while the
source inventory differs. Even if every stroke were recognized as a possible
glyph, a dash has no vertical glyph extent from which to infer nominal text
height. Combining adjacent strokes into words cannot prove all text was found;
ordinary graphics can duplicate the same shapes.

The [Gerber layer format specification, §5.7](https://www.ucamco.com/files/downloads/file_en/554/gerber-layer-format-specification-revision-2026-05_en.pdf)
states that text is plotted as image data and describes optional `.FlashText`
attribution to retain the string. That attribution is absent here, and the
attribute does not supply KiCad's nominal height. KiCad's
[PCB Editor documentation](https://docs.kicad.org/10.0/en/pcbnew/pcbnew.html)
distinguishes text properties from graphical line width in the source editor.

## Acceptance procedure

For the current packages, keep the independent Gerber re-import text-height
gate red. Separately audit every visible `PCB_TEXT` and footprint reference or
value on both silkscreen layers in the saved `.kicad_pcb`: record its UUID,
literal, visibility, layer, and nominal `TextSize.y`; reject below-rule sizes.
Bind that source audit and the regenerated Gerber layers to the same receipt,
compare exported geometry and aperture data with a fresh plot, then review the
plotted legend in CAM at 1:1 for legibility and missing marks. This is a
source-backed manufacturing acceptance route, not an independent plotted
height certificate. A fab may accept that evidence explicitly; the automated
Gerber completeness gate still reports its gap.

To make an independent machine check possible in a later exporter, emit a
sidecar tied to the Gerber hash. It must map *every* text object ID and nominal
height to its plotted operations and identify all non-text operations. A
verifier would reject unmatched, duplicated, or missing operations and text
IDs, and independently check the assigned rendered geometry. Adding a
`.FlashText` string alone does not establish nominal height or complete
operation ownership.
