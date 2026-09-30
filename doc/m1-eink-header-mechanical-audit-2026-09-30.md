# eInk J2 mechanical importer correction

The working-M1 fresh mechanical fit rejected eInk J2 as having no 3D model.
The actual receipt-bound exported STEP contains the authentic connector solid:
HDR-TH_9P-P2.54-M-WI-1X9P, volume153.310085mm³, at
(36.5,39.6,1.595). STEP SHA256:
`796201291307e62b369bea3a20a735db9896ada007cae9960ee408be576bfd90`.

The error was footprint assignment. The silk legend G2 and connector J2 share
(36.5,-39.6). G2 has no model anchors; J2 has the declared anchor(36.5,39.6).
The importer selected the first equal-distance footprint and assigned the
connector solid to G2. An isolated replay of the frozen production functions
reproduces missingJ2; the corrected functions assign the same real solid toJ2.

The minimal correction in `hw/mech/fc_check.py` resolves equal-distance matches
in favor of a footprint with declared exported model anchors. It preserves
geometric distance ordering, the0.01mm matching limit, actual solid volume,
and the missing-model rejection. Four regressions cover the genuine coincident
J2/G2 origin in either list order, missing geometry, wrong origin, and distance
precedence. All four pass. No board, STEP or supplier model was changed.

Evidence is in `build/eink-j2-mechanical-import-audit-20260930/`: original/fixed
assignment JSON, actual imported nodes, source patch, before-input hashes,
and the isolated full eight-board geometric replay. The full fit outcome must
be read from its terminal qualification; the assignment correction alone is
not a full mechanical pass.

The isolated corrected full geometry replay genuinely completed exit0:
geometry696.2s plus render19.3s. Every emitted geometric check has zero
failures, including nine MECH-004 checks. J2's real mating face projects
5.650143mm beyond the top edge (required minimum-.3mm). The actual new plug
clearance is checked in the full geometry result. All bound source, nativePCB,
STEP and receipt hashes remained unchanged during replay; all eight STEP
provenance records also matched their current PCB, exporter and model files.

`terminal-qualification.json` binds the completed result and original/fixed
assignment evidence. This is an isolated geometric proof; production fit
metadata must still bind the corrected source normally. It does not rewrite
or adopt the earlier failed fit record. MECH-002's non-geometric checks remain
owned by the normal `fit.py` wrapper.
