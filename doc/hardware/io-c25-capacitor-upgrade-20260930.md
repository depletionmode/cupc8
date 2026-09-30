# Same-pad IO C25 input-capacitor upgrade

## Selected practical repair

Replace C25's nominal 1 µF C52923 with **4.7 µF C23733**, Samsung
**CL05A475MP5NRNC**, 10 V, ±20%, X5R 0402. This is an isolated prepared
repair; shared board, route seed and manufacturing tools remain frozen.
It addresses a real modeled 7 V limit failure when the old 1 µF part's
operating capacitance falls to 0.7 µF. It requires no rerouting.

[Samsung's primary product page](https://product.samsungsem.com/mlcc/CL05A475MP5NRN.do)
and [component data sheet](https://weblib.samsungsem.com/mlcc/mlcc-ec-data-sheet.do?partNumber=CL05A475MP5NRN)
confirm 4.7 µF, ±20%, 10 V, X5R and 0402 dimensions. The data sheet has
no supported graphs and labels its characteristic data typical. **No
vendor-guaranteed DC-biased operating minimum was recovered.** The
higher-voltage 25 V CL05A475MA5NUNC also exists, but its supplier footprint
and BOM identity are not cached/qualified in this project. C23733 is
already a cached JLC basic part used on the CPU board; its live stock
still requires the real stock gate.

The proposed model uses **1.6 µF effective capacitance** as an engineering
qualification target to be confirmed on first articles. It is not a
supplier guarantee inferred from 4.7 µF nominal. Tolerance and a possible
15% X5R temperature decrease give 4.7 × 0.8 × 0.85 = 3.196 µF before DC
bias, aging and frequency effects. Meeting 1.6 µF would permit roughly
50% additional combined reduction, but that reduction is unbounded by the
available supplier information. No such bound is assumed proven.

## Actual isolated physical proof

Candidate: `build/io-c25-upgrade-20260930/io.kicad_pcb`, SHA256
`d33c4caf1c5292f04be249f0134aa73bb0d878cfc89a64e20ae0aa1511c133bb`.
It is derived from the actual completed round3 IO board with only C25's
value and LCSC metadata changed. The source receipt is validated before
and after creating it; the candidate carries no new completed receipt.

- Every pad's physical geometry, layer, placement and net is identical.
- Every routed track/via and every raw filled-zone coordinate is identical.
- Cached C23733 and C52923 supplier package, pins and pad coordinates are
  exactly identical: C0402, pads 1/2 at ±0.42 mm. No placement correction
  changes. C25 remains `Capacitor_SMD:C_0402_1005Metric` at the same angle.
- Actual candidate KiCad DRC: **0 violations, 0 opens, 0 schematic parity
  issues**. Full cached BOM/CPL check: **28 BOM lines pass**.
- Actual proposed generator produces exactly the candidate's net topology.
- Proposed binder validates actual schematic/PCB/BOM and all required
  supply, return and control copper; **16 source/model mutations pass**.
- New scratch strong seed uses honest `design-candidate` origin, complete
  non-pour guards and connectivity, no inherited manufacturing receipt.

Artifact directory includes `geometry-binding.json`, `drc.json`,
`candidate.log`, `generated-source.log`, proposed source files and guarded
`io-full-route-seed.json`. Adoption requires one coordinated source freeze
and a fresh normal pipeline; old receipts must not be rehashed.

## Circuit constraints and actual electrical probes

[TI TPS2553 data sheet §10.2.1.2.4](https://www.ti.com/lit/ds/symlink/tps2553.pdf)
recommends at least 0.1 µF at IN and additional input capacitance when
needed to suppress transient overshoot. It supplies no restrictive maximum
input capacitor for this change. C25 is upstream of the switch; the USB
port's switched capacitance and current limit are unchanged.

[TI TPS61023 data sheet §6.3/8.2.2.3](https://www.ti.com/lit/ds/symlink/tps61023.pdf)
permits 4–1000 µF effective output capacitance. Existing C23/C24 are 44 µF
nominal; adding this local capacitor remains well below the upper limit.
The model's existing C23/C24 derating assumption is separately unchanged.
The data sheet warns to account for DC bias, aging and AC effects; none
are replaced by a nominal-value assertion here.

The actual proposed full transient model (five behavioral plus eight TI
boost cases) passes at the 1.6 µF engineering target: **U5 IN max 6.273 V**
against 7 V; **boost VOUT max 5.431 V** against 6 V; typical-response U5 IN
minimum 2.959 V. All four engineering-stress cases retain the actual
647.444 mA bound. Three typical cases retain the previously approved,
explicitly logged 5/10 mA numerical current retries; these are not claimed
as guaranteed full-current results. The true-current first-100-µs diagnostic
also supports the lower peak but does not replace the full-window gate.

At 2 µF effective, the existing full-window suite peaks at 6.104 V. An
additional upper-capacitance probe at **6.486 µF** (4.7 × 1.2 × 1.15,
without a bias reduction) passes all eight cases: U5 IN max **5.501 V**,
boost max **5.441 V**. Seven cases run at the true current bound; one
cable case uses the logged existing numerical retry. There is no new
current-limit reduction or response/loop-inductance waiver.

Proposed model log: `build/io-c25-upgrade-20260930/proposed-power-binding.log`.
Sensitivity and upper probe data:
`build/io-switch-cap-sweep-20260930/{approved-retry,local-window,maximum-capacitance}/`.

## Unfinished physical qualification

IC-104 must confirm actual U5 IN <7 V and boost OUT <6 V during port
attachment, receptacle/cable shorts and recovery, including measurement
uncertainty. It also requires **C25 effective capacitance ≥1.6 µF** at the
relevant rail bias and temperature, with the actual fitted part and method
recorded. Use biased component/fixture measurements; an in-circuit reading
of C23+C24+C25 does not isolate C25. Record frequency dependence (at least
1 kHz, 100 kHz and 1 MHz where the calibrated fixture supports it), fixture
correction, component temperature and sample age. Test the loaded board
at the required 40°C ambient as well as nominal bench conditions. These
records support first articles in the stated scope; they do not establish
unmeasured production/lifetime temperature corners.

The actual ring waveform is the final circuit check because the engineering
20 nH loop and 20 µs response are not guaranteed physical maxima. If a
sample misses the capacitance target or voltage limit, stop that stress
and qualify a higher-capacitance/higher-voltage local part or protection.
No first article result, human review or manufacturing release is signed.
