# Fitted slot SPI functional model — 2026-09-30

`hw/cosim/slot_spi.py` requires the actual numeric pin, reference, library,
value and net identities. Four RP cards have their three fitted 220Ω/10pF
receiver filters and a separate raw-CS 220Ω/10pF TI125 OE filter. WiFi has
three fitted non-inverting TI125 stages with both input/output resistors,
input/output capacitors, bypass capacitors, OE grounds and supply returns.
All five MISO branches require TI SN74LVC1G125DCKR, R60 220Ω and R61 47kΩ.
Main requires the six exact R37–R42 68Ω CS branches, R107 100kΩ pullup and
R109 4.7kΩ pulldown; the powered functional idle level is low.

Every physical leg is checked with native same-net copper connectivity,
including actual filled supply/ground polygons and holes. No plane transit
is assigned a signal propagation length. Missing topology fails source
validation; missing copper fails strict route/coverage. An OE launch open
removes the MISO drive while preserving an independently connected MCU CS
input. A capacitor stub open fails strict completeness without inventing a
DC logic failure on the still-connected signal. The functional abstraction
preserves DC through fitted resistors and non-inverting enabled TI stages.
It does not qualify analogue slew, stress, timing, load, leakage, transient
rails, capacitor ESR/ESL, or package/connector bounds. Those remain separate
power and SI gates; card RUN reaction remains the existing scoped boundary.

`test/hw/test_cosim_slot_spi.py ACTUAL_BOARD_ROOT` reads real emitted netlists
and all five actual native boards. Counterexamples change resistor values
or numeric pins, remove/wrong-value filter capacitors, substitute wrong TI
parts/OE/ground pins, alter actual main bias/source pins, and physically move
native launch/cap pads. It is registered in E2E-001's binding test chain.
The original 50 boundary entries are unchanged: the six electrical slot
reset nets remain modeled, leaving the 44 accepted boundary waivers.

The historical v138 mechanical check found storage R65 violated the mandatory
5mm tab clearance. The genuine R65-v4 normal build and affected all8 mechanical
check subsequently pass; the changed six-slot CS/OE screen passes192/192
cases, with full mixed SPI/timing qualification still open.

The independently qualified staged output-damping extension requires actual
WiFi R69/R70=10Ω on the private C61/C64 capacitor nets. Both numeric resistor
launches, the private capacitor signal leg and GND remain strict requirements.
All eight fresh normal development packages and strict topology pass:992
physical paths,535 runtime nets and44 unchanged boundary waivers. Seven
permanent source/native test groups also pass, including eight branch-source
mutations and eight real resistor/capacitor pin opens. The extension remains
staged until coordinated source adoption. Its physical source/analogue and
mechanical qualification remains separate; no manufacturing approval follows
from the functional proof. See
`build/spi-development-output-damping-round2-20260930/strict-top-qualification.json`.
