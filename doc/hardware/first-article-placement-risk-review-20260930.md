# First-article placement risk review

David delegated the engineering placement review to Codex. This assessment
uses actual fresh working-M1 PCB, true netlist, fitted BOM and CPL exports,
primary pin drawings and supplier CAD. It is not a supplier production
preview or David’s manufacturing signature.

## What the 75 flagged placements mean

These are review requests, not 75 discovered mistakes. The bound review
snapshot in `build/manufacturing-prep-working-m1-firstarticle-20260930/`
contains 75 original rows, 64 engineering acceptances, 11 specific evidence
gaps, and zero demonstrated physical placement mismatches. Fresh exact CAD
and drawings are being used to close the remaining gaps; the decision index
is authoritative for subsequent counts.

| Group | What was checked | Consequence if incorrectly assembled | Decision about leaving PCB placement unchanged |
| --- | --- | --- | --- |
| 31 LEDs | Native numbered pads, actual net polarity, supplier pad projection, primary polarity marking and CPL rotation | Reversed LED usually stays dark; the particular circuit still matters. It is a component assembly defect requiring local rework, not evidence of a current placement defect. | Accept existing placement on the inspected evidence. Check supplier polarity preview and inspect samples. |
| 10 isolated resistor arrays | Genuine equal-element pair topology and numbered native/supplier pad match | A 90-degree mistake can connect the wrong signals; the proved pair-preserving 180-degree symmetry is electrically harmless. | Accept existing matched rotation. Do not extrapolate symmetry to arbitrary angles or different array topology. |
| 14 connectors | Key, body outline, solder lands, numbered native/supplier pads and primary drawing where available | Wrong numbering or reversed mounting can stop programming/display, or connect power to a signal. This is more consequential than an LED polarity error. | Twelve accepted in the snapshot. Independently verify Main system socket and GPU HDMI contact numbering before closing the other two. |
| 8 TI buffers | Authentic silicon pin functions and native nets; exact supplier origin and side-aware pad projection needed | Reversing a five-pin buffer swaps supply/ground/control/data. SPI can fail and silicon may be damaged. An offset can cause open joints or bridging. | No current native pin error demonstrated. Obtain exact C7833 CAD rather than assuming another supplier part has the same placement origin; check every Top and Bottom instance. |
| 2 tactile switches | Actual common contact pairs and used nets against the primary drawing | A mistaken pair can make the control permanently closed or never operate. | Accept existing placements: actual used pads span the two independent contact pairs. |
| 10 other semiconductor placements | Actual net-to-pad function, primary package pin order, polarity where applicable, supplier geometry and CPL | Incorrect power/reset parts can prevent boot, misoperate monitoring or damage a rail. | Nine accepted on actual evidence. Confirm exact Holtek SOT23-5 variant drawing for the remaining regulator. |

## Why leaving an accepted placement is reasonable

For the accepted rows the evidence agrees about the physical pads, electrical
functions and intended placement. Moving or rotating those footprints has no
identified defect to repair. The remaining risk is the manufacturer loading
or interpreting the assembly data incorrectly; its actual production preview
and inspection of delivered samples address that risk. No percentage failure
probability can be justified from these files.

For the unresolved rows, the issue is an incomplete independent cross-check,
not an observed wrong board. Their consequences can still be serious, so a
blanket acceptance is unwarranted when the missing exact drawing or CAD can
be retrieved. These checks primarily concern assembly data and part identity;
none currently establishes a need to reroute Main.

## Specific semiconductor consequences

Main D1 reversed can clamp VBUS and prevent power-up. D7 has a particular
common-anode diode topology used by monitoring/reset logic. U6 affects reset;
U16 affects power enable; U17 supplies the monitoring reference; U18/U20
monitor rails; U19 distributes card reset. IO U5 controls keyboard VBUS and
current limiting. Wrong orientation of these parts could therefore stop the
machine or defeat protection. Those consequences explain careful checking;
they are not claims that the inspected current placements are wrong.

## Current engineering action

Keep physically matched placements. Close the exact buffer origin/side and
connector/regulator drawing gaps using genuine sources; correct only a
confirmed mismatch. Generate the final hash-bound engineering review against
the final native/BOM/CPL files, then inspect the actual supplier preview before
production approval. Do not substitute a forged human signoff or erase old
failed checks.
