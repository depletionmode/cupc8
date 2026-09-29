#!/usr/bin/env python3
"""Receipt-bound ngspice signal integrity for the slow buses (row 4.6).

    python3 hw/si/slowbus_si.py --row MB-007|CC-007|SC-007|EC-007 [--board-dir build/hw]

Each case is assembled from the *routed* boards: every copper piece, via and
plated barrel of every net the signal reaches (through series resistors and
resistor packs, slot/socket contacts into the mated card, and onto every pin
the KiCad netlist puts on those nets). A pin whose part has no model here
fails the run; nothing on a net is silently dropped.

Checks per receiver pin and edge (`evaluate`):
  * overshoot/undershoot inside the receiving part's absolute maximum;
  * monotonic through the VIL..VIH band, and no ring-back into the band
    before the next edge;
  * the edge completes within the half period of the bus clock;
  * timing: arrival (last threshold crossing) feeds the row's setup/hold
    budget (`timing_*`).
Cases sweep the IBIS corners, the bracketed-model bounds, the TQ144 package
envelope, +/-15 % line impedance and the connector bounds. The case with the
worst overshoot is re-run with half the RLGC section length and half the
time step; its metrics must agree (discretisation convergence).

Evidence binding: every board build must pass hw/tools/boardevidence.py's
`validate` (inputs and artifacts). `--artifacts-only` checks only the
artifact hashes (for work while sources are ahead of the builds); a report
made that way is marked `valid_for_row_4_6: false` and the run exits 1.
"""
import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / 'hw/cosim'))
import slowbus_models as models  # noqa: E402
import slowbus_route as route  # noqa: E402
from netlist import read as read_netlist  # noqa: E402

OUT_DIR = ROOT / 'build/si-slowbus'
PINOUT = ROOT / 'hw/datasheets/iCE40HX4K-TQ144-pinout.csv'
RAILS = {'/GND': 0.0, 'GND': 0.0, '/+3V3': 3.3, '/3V3': 3.3, '/3V3_STBY': 3.3,
         '/+5V': 5.0, '/5V': 5.0}
SLOTS = tuple(f'J{n}' for n in range(11, 17))
CARD_KINDS = ('gpu', 'io', 'storage', 'eink', 'wifi')


# --------------------------------------------------------------- part data
@dataclass(frozen=True)
class Part:
    """Receiver data of one part at a 3.3 V rail (vdd = the rail corner).

    abs_* are the DC absolute maximum; ac_* optionally allow a short
    excursion beyond it (the maker's own overshoot allowance), for at most
    ac_width seconds per edge."""
    vih: float
    vil: float
    abs_lo: float
    abs_hi_over_vdd: float | None
    abs_hi: float | None = None
    c_in: tuple = (1e-12, 10e-12)  # bracket (low, high) F
    l_pkg: float = 1e-9
    ac_hi_over_vdd: float | None = None
    ac_hi: float | None = None
    ac_lo: float | None = None
    ac_width: float = 0.0
    source: str = ''

    def abs_max(self, vdd):
        return self.abs_hi if self.abs_hi is not None else vdd + self.abs_hi_over_vdd

    def ac_max(self, vdd):
        if self.ac_hi is not None:
            return self.ac_hi
        return vdd + self.ac_hi_over_vdd if self.ac_hi_over_vdd is not None else None


SOURCES = {
    'rp2040': 'Raspberry Pi RP2040 Datasheet, build-date 2025-02-20 3184e62 '
              '(datasheets.raspberrypi.com/rp2040/rp2040-datasheet.pdf)',
    'ice40': 'Lattice FPGA-DS-02029-4.3 iCE40 LP/HX (Feb 2025) Tables 4.1, 4.5, 4.13',
    'lvc125': 'Nexperia 74LVC1G125 Rev. 17.1 (3 Sep 2024) Tables 5, 7, 8',
    'esp32c3': 'Espressif ESP32-C3-MINI-1 datasheet v2.2 Table 6-3',
    'sd': 'Kingston SDCIT microSDHC spec sheet 4900180-001.A00 Tables 6-1, 6-2, 6-6, 7-1 '
          '(the SD Association simplified spec leaves these blank)',
    'sram': 'ISSI IS62/65WV5128EALL/EBLL/ECLL Rev. A4 (Apr 2017) p4, p6',
    'rom': 'Microchip SST39LF/VF010/020/040 DS20005023E p7, Tables 6-1, 6-3',
    'txb': 'TI TXB0108 SCES643L sections 5.1, 5.3, 5.5, 7.3.3; IBIS scem518 rev 1.7',
    'uc8179': 'UltraChip UC8179c datasheet rev 0.6 p56-58',
}

PARTS = {
    # Table 622 VPIN -0.5 .. IOVDD+0.5; Table 625 VIH 2.0 / VIL 0.8 @ 3.3 V.
    # No pin capacitance, edge rate or IBIS is published: C and drive bracketed.
    'RP2040': Part(2.0, 0.8, -0.5, 0.5, c_in=(1e-12, 10e-12), source='rp2040'),
    # Table 4.1: I/O applied -0.5 .. 3.60 V; 200 mV above the recommended VCCIO
    # maximum (3.46 V) is allowed for <= 1.6 ns. Table 4.13 VIH 2.0 / VIL 0.8.
    # Receivers use the vendor IBIS input (C_comp, clamps), not c_in.
    'ICE40HX4K-TQ144': Part(2.0, 0.8, -0.5, None, abs_hi=3.6, ac_hi=3.66,
                            ac_lo=-0.5, ac_width=1.6e-9, source='ice40'),
    # Table 5 VI -0.5 .. 6.5 V; Table 7 C_I 5 pF typ (bracketed 1..6 pF)
    '74LVC1G125GW': Part(2.0, 0.8, -0.5, None, abs_hi=6.5, c_in=(1e-12, 6e-12),
                         source='lvc125'),
    # no IO-pin abs max is published: VIH max VDD+0.3 / VIL min -0.3 are used;
    # C_IN 2 pF typ (bracketed 1..10 pF)
    'ESP32-C3-MINI-1': Part(0.75 * 3.3, 0.25 * 3.3, -0.3, 0.3, c_in=(1e-12, 10e-12),
                            source='esp32c3'),
    # VIH 0.625 VDD, VIL 0.25 VDD; peak voltage on all lines -0.3 .. VDD+0.3;
    # CCARD <= 10 pF (bracket 1..10 pF, including the card's own contact)
    'microSD': Part(0.625 * 3.3, 0.25 * 3.3, -0.3, 0.3, c_in=(1e-12, 10e-12),
                    l_pkg=2e-9, source='sd'),
    # Vterm -0.5 .. VDD+0.5; AC overshoot VDD+2.0 / -2.0 V for < 10 ns;
    # VIH 2.0 / VIL 0.8; CIN 6 pF max, CI/O 8 pF max
    'IS62WV5128EBLL-45HLI': Part(2.0, 0.8, -0.5, 0.5, c_in=(1e-12, 8e-12),
                                 ac_hi_over_vdd=2.0, ac_lo=-2.0, ac_width=10e-9,
                                 source='sram'),
    # DC -0.5 .. VDD+0.5, transient (< 20 ns) -2.0 .. VDD+2.0; VIL 0.8,
    # VIH 0.7 VDD; CIN 6 pF, CI/O 12 pF
    'SST39VF040': Part(0.7 * 3.3, 0.8, -0.5, 0.5, c_in=(1e-12, 12e-12),
                       ac_hi_over_vdd=2.0, ac_lo=-2.0, ac_width=20e-9, source='rom'),
    # TXB0108 B port (on the Waveshare e-Paper Driver HAT): VI -0.5 .. 6.5 V,
    # VIH 0.65 VCCI, VIL 0.35 VCCI; receivers use the TI IBIS input
    'TXB0108': Part(0.65 * 3.3, 0.35 * 3.3, -0.5, None, abs_hi=6.5, source='txb'),
}

# Behavioural driver brackets for parts with no usable vendor IBIS:
# (fast/strong (R ohm, 10-90 % s), slow/weak (R, t)). The fast bound is
# deliberately faster and stronger than any 3.3 V CMOS pad of the part.
DRIVE = {
    # Every RP2040 pin here runs at the pad reset default, 4 mA and slow slew
    # (fw/rp2040: only slotspi.c sets drive, to 4 mA/slow). Figure 171's
    # typical 4 mA curves are ~32 ohm (sink) and ~45 ohm (source) near the
    # rails; the fast bound takes 20 ohm and a 0.5 ns 10-90 % edge
    # (edge rate unpublished: assumption). Slow bound: Table 625 VOH >=
    # 2.62 V at 4 mA -> (3.3-2.62)/4 mA = 170 ohm.
    'RP2040': ((20.0, .5e-9), (170.0, 5e-9)),
    # VOL <= 0.125 VDD at 2 mA -> <= 206 ohm; no rise-time bound for cards
    'microSD': ((15.0, .25e-9), (206.0, 10e-9)),
    # VOH >= 2.4 V at -1 mA -> <= 900 ohm is too loose to be useful for
    # timing; the slow bound keeps the 45 ns part's read path plausible
    'IS62WV5128EBLL-45HLI': ((10.0, .3e-9), (200.0, 5e-9)),
    'SST39VF040': ((10.0, .3e-9), (200.0, 5e-9)),
    # HSO321S 12 MHz CMOS oscillator: no datasheet in the repository;
    # bounds assumed
    'oscillator': ((10.0, .3e-9), (50.0, 6e-9)),
    # TXB0108 B-port output: trB/tfB 0.7..3.9 ns (5.21); ~4 kohm series
    # resistance outside the one-shot window
    'TXB0108': ((20.0, .5e-9), (4000.0, 3.9e-9)),
}

# What-if clamp for the fix studies only (not on any board): a generic
# BAT54-class small-signal Schottky fitted to Nexperia's typical Vf curve
# (0.32 V at 1 mA, 0.40 V at 10 mA, 0.5 V at 30 mA, ~1 V at 100 mA).
SCHOTTKY_MODEL = '.model DSCH D(IS=8e-9 N=1.05 RS=2.5 CJO=8p M=.4 VJ=.4 BV=30)'
# Slot/socket contact (per contact; card edge). No per-contact L/C is
# published for the fitted UMAX 3183 slot. A PCIe-CEM-class contact meeting
# return loss <= -12 dB to 1.3 GHz (FCI GS-12-233 Rev H 4.5-4.7, a
# representative part) is bounded by L <= 3.2 nH or C <= 1.3 pF in a 50 ohm
# system; the sweep brackets 1..5 nH and 0.3..1.5 pF.
LVC125_L_PKG = 1e-9          # TI IBIS LVC1G125_DCK (SC70-5, the GW's package) L_pkg typ

CONNECTOR = ({'l': 1e-9, 'c': .3e-12, 'r': .03}, {'l': 5e-9, 'c': 1.5e-12, 'r': .03})


# ------------------------------------------------------------- evidence
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_evidence(board_dir, kinds, artifacts_only):
    spec = importlib.util.spec_from_file_location('slowbus_evidence',
                                                  ROOT / 'hw/tools/boardevidence.py')
    ev = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ev)
    receipts, problems = {}, []
    for kind in kinds:
        build = Path(board_dir) / kind
        evidence = json.loads((build / 'evidence.json').read_text())
        try:
            ev.validate(kind, build, root=ROOT)
            state = 'valid'
        except ValueError as error:
            if not artifacts_only or evidence.get('artifacts') != ev.artifacts(build):
                raise ValueError(f'{kind}: {error}') from None
            problems.append(f'{kind}: {error}')
            state = 'artifacts-only'
        receipts[kind] = {'receipt_sha256': sha(build / 'evidence.json'),
                          'board_sha256': sha(build / f'{kind}.kicad_pcb'),
                          'netlist_sha256': sha(build / f'{kind}.net'), 'state': state}
    return receipts, problems


# ------------------------------------------------------------- assembly
@dataclass
class Probe:
    label: str
    node: str
    part: str
    role: str = 'rx'
    group: int = 0


@dataclass
class Deck:
    lines: list = field(default_factory=list)
    probes: list = field(default_factory=list)
    nets: dict = field(default_factory=dict)
    driver_node: str = ''
    notes: list = field(default_factory=list)


class Bench:
    """Board builds, netlists and cached copper graphs."""

    def __init__(self, board_dir):
        self.board_dir = Path(board_dir)
        self.circuits, self.graphs = {}, {}
        self.banks = None

    def circuit(self, kind):
        if kind not in self.circuits:
            self.circuits[kind] = read_netlist(self.board_dir / kind / f'{kind}.net')
        return self.circuits[kind]

    def pcb(self, kind):
        return self.board_dir / kind / f'{kind}.kicad_pcb'

    def pins(self, kind, net):
        return sorted(f'{r}.{p}' for r, p in self.circuit(kind).nets[net])

    def graph(self, kind, net):
        key = (kind, net)
        if key not in self.graphs:
            route.check_planes(self.pcb(kind), kind)
            self.graphs[key] = route.extract(self.pcb(kind), kind, net, self.pins(kind, net))
        return self.graphs[key]

    def ice40_model(self, pin):
        if self.banks is None:
            import ibis_source_audit as audit
            if sha(PINOUT) != audit.PINOUT_SHA256:
                raise ValueError('TQ144 pinout CSV differs from the reviewed source')
            self.banks = audit.pin_banks(PINOUT)
        import ibis_source_audit as audit
        return audit.model_for_pin(pin, self.banks)


def resistor_pins(circuit, ref, pin):
    """(other pin, value) of the resistor element that owns ref.pin."""
    value = circuit.components[ref][0]
    if ref.startswith('RN'):
        pairs = {'1': '8', '8': '1', '2': '7', '7': '2', '3': '6', '6': '3', '4': '5', '5': '4'}
        return pairs[pin], value
    return {'1': '2', '2': '1'}[pin], value


def ohms(value):
    m = re.fullmatch(r'([0-9.]+)([kmMR]?)', value.replace('R', '') if value.endswith('R') else value)
    if not m:
        raise ValueError(f'resistor value {value!r}')
    return float(m[1]) * {'': 1, 'R': 1, 'k': 1e3, 'M': 1e6, 'm': 1e-3}[m[2]]


def farads(value):
    m = re.fullmatch(r'([0-9.]+)([pnu])F?', value)
    if not m:
        raise ValueError(f'capacitor value {value!r}')
    return float(m[1]) * {'p': 1e-12, 'n': 1e-9, 'u': 1e-6}[m[2]]


@dataclass(frozen=True)
class Config:
    slots: tuple                   # card kind (or None) per J11..J16
    corner: str = 'typ'            # IBIS corner
    bracket: int = 0               # 0 fast/strong bound, 1 slow/weak bound
    rx_c: int = 1                  # receiver C bracket index
    package: int = 0               # TQ144 envelope row
    connector: int = 1
    zscale: float = 1.0
    section_mm: float = 2.0
    extra: tuple = ()              # row-specific (key, value) pairs

    def get(self, key, default=None):
        return dict(self.extra).get(key, default)


class Assembler:
    def __init__(self, bench, config, vdd):
        self.bench, self.cfg, self.vdd = bench, config, vdd
        self.deck = Deck()
        self.ladders = {}
        self.count = 0
        self.group = 0
        self.cables = {}

    def uid(self, stem):
        self.count += 1
        return f'{stem}{self.count}'

    def mate(self, inst, kind, ref, pin):
        """The contact on the other side of a connector, or None if open."""
        if kind == 'main' and ref in SLOTS:
            card = self.cfg.slots[SLOTS.index(ref)]
            return (f'{ref}:{card}', card, 'J1', pin) if card else None
        if kind == 'main' and ref == 'J2':
            return ('cpu', 'cpu', 'J1', pin)
        if kind in CARD_KINDS and ref == 'J1':
            return ('main', 'main', inst.split(':')[0], pin)
        if kind == 'cpu' and ref == 'J1':
            return ('main', 'main', 'J2', pin)
        return 'unmodelled'

    def ladder(self, inst, kind, net):
        key = (inst, net)
        if key not in self.ladders:
            graph = self.bench.graph(kind, net)
            ladder = route.Ladder(graph, f'{self.uid("w")}_', self.cfg.section_mm, self.cfg.zscale)
            self.deck.lines += ladder.emit()
            self.ladders[key] = ladder
            self.deck.nets[f'{inst}:{net}'] = route.summary(graph)
        return self.ladders[key]

    def assemble(self, start, driver, dry=False):
        """start = (inst, kind, ref, pin); driver(assembler, node) adds lines.

        dry: only walk the netlists and return the (kind, net) set reached."""
        inst0, kind0, ref0, pin0 = start
        reached = set()
        queue = [(inst0, kind0, self.bench.circuit(kind0).net(ref0, pin0))]
        done, links, pads = set(), [], {}
        while queue:
            inst, kind, net = queue.pop()
            if (inst, net) in done:
                continue
            done.add((inst, net))
            circuit = self.bench.circuit(kind)
            reached.add((kind, net))
            ladder = None if dry else self.ladder(inst, kind, net)
            for name in self.bench.pins(kind, net):
                ref, pin = name.split('.')
                node = 'dry' if dry else ladder.pad(name)
                pads[(inst, ref, pin)] = node
                value = circuit.components[ref][0]
                if (inst, ref, pin) == (inst0, ref0, pin0):
                    if not dry:
                        self.deck.driver_node = node
                        driver(self, node, kind, ref, pin, value)
                    continue
                if ref.startswith('R'):
                    other, rvalue = resistor_pins(circuit, ref, pin)
                    onet = circuit.net(ref, other)
                    if onet in RAILS:
                        if not dry:
                            self.deck.lines.append(f'R{self.uid("p")} {node} {self.rail(onet)} '
                                                   f'{ohms(rvalue):g}')
                    elif onet is None:
                        raise ValueError(f'{inst}:{ref}.{other} unconnected')
                    else:
                        links.append(('R', (inst, ref, pin), (inst, ref, other), ohms(rvalue)))
                        queue.append((inst, kind, onet))
                elif ref.startswith('C'):
                    other = {'1': '2', '2': '1'}[pin]
                    onet = circuit.net(ref, other)
                    if onet not in RAILS:
                        raise ValueError(f'{inst}:{ref} couples two signal nets')
                    if not dry:
                        self.deck.lines.append(f'C{self.uid("c")} {node} 0 {farads(value):g}')
                elif ref.startswith('J'):
                    mated = self.mate(inst, kind, ref, pin)
                    if dry and mated in ('unmodelled', None):
                        continue
                    if mated == 'unmodelled':
                        self.connector_load(inst, kind, ref, pin, value, node)
                    elif mated is None:
                        # empty slot: the contact itself stays as an open stub
                        c = CONNECTOR[self.cfg.connector]['c']
                        self.deck.lines.append(f'C{self.uid("k")} {node} 0 {c:g}')
                    else:
                        minst, mkind, mref, mpin = mated
                        mnet = self.bench.circuit(mkind).net(mref, mpin)
                        if mnet is None:
                            raise ValueError(f'{minst}:{mref}.{mpin} not connected')
                        links.append(('K', (inst, ref, pin), (minst, mref, mpin), None))
                        queue.append((minst, mkind, mnet))
                elif ref.startswith(('TP', 'H')):
                    continue                           # copper only, extracted
                elif ref.startswith('U'):
                    if not dry:
                        self.device(inst, kind, ref, pin, value, node)
                else:
                    raise ValueError(f'{inst}:{ref}.{pin} ({value}) on {net} has no model')
        if dry:
            return reached
        seen = set()
        for kind_, a, b, value in links:
            key = tuple(sorted((a, b))) + (kind_,)
            if key in seen:
                continue
            seen.add(key)
            if b not in pads:
                raise ValueError(f'{b} not reached')
            na, nb = pads[a], pads[b]
            if kind_ == 'R':
                self.deck.lines.append(f'R{self.uid("s")} {na} {nb} {value:g}')
                shunt = self.cfg.get('tx_shunt_c')
                if shunt and a[1].startswith('RN'):
                    # what-if: a capacitor on the line side (pads 5-8) of a series
                    # array, i.e. an RC edge filter beside the driver
                    line_side = na if a[2] in '5678' else nb
                    self.deck.lines.append(f'C{self.uid("tc")} {line_side} 0 {shunt:g}')
            else:
                k = CONNECTOR[self.cfg.connector]
                mid = self.uid('km')
                self.deck.lines += [f'C{self.uid("k")} {na} 0 {k["c"] / 2:g}',
                                    f'L{self.uid("k")} {na} {mid} {k["l"]:g}',
                                    f'R{self.uid("k")} {mid} {nb} {k["r"]:g}',
                                    f'C{self.uid("k")} {nb} 0 {k["c"] / 2:g}']
        return self.deck

    def rail(self, net):
        node = 'rail_' + re.sub(r'\W', '_', net)
        line = f'V{node} {node} 0 {RAILS[net] if RAILS[net] != 3.3 else self.vdd:g}'
        if line not in self.deck.lines:
            self.deck.lines.append(line)
        return node

    def device(self, inst, kind, ref, pin, value, node):
        label = f'{inst}:{ref}.{pin}'
        if value == 'ICE40HX4K-TQ144':
            model = self.ice40[self.bench.ice40_model(pin)]
            node = self.receiver_options(node)
            die = self.package(node, label)
            self.deck.lines += models.ibis_device_lines(self.uid('i'), model, self.cfg.corner,
                                                        die, 'vcc_ibis')
            # thresholds and stress at the die pad, behind the package, as
            # for every other receiver model here
            self.deck.probes.append(Probe(label, die, value, group=self.group))
            return
        if value == 'TPD4E05U06DQAR':
            if pin not in ('1', '2', '4', '5'):
                raise ValueError(f'{label}: TPD4E05U06 pin {pin} is not an I/O channel')
            # the file's power clamp is referred to its 5 V [Voltage range]
            # (the part has no supply pin): it models the positive breakdown
            if 'Vtpd5 tpd5 0 5' not in self.deck.lines:
                self.deck.lines.append('Vtpd5 tpd5 0 5')
            self.deck.lines += models.ibis_device_lines(self.uid('e'), self.tpd, self.cfg.corner
                                                        if self.cfg.corner in models.CORNERS else 'typ',
                                                        node, 'tpd5')
            return
        if value.startswith('ESP32-C3-MINI-1'):
            value = 'ESP32-C3-MINI-1'
        part = PARTS.get(value)
        if value == '74LVC1G125GW':
            # TI SN74LVC1G125 IBIS as the family proxy (models.load_lvc125):
            # pin 4 a de-selected 3-state output, pins 1 (OE) and 2 (A) inputs
            model = self.lvc[{'4': 'out', '1': 'oe', '2': 'in'}[pin]]
            die = self.uid('lv')
            corner = self.cfg.corner
            self.deck.lines.append(f'L{self.uid("ll")} {node} {die} {LVC125_L_PKG:g}')
            self.deck.lines += models.ibis_device_lines(self.uid('v'), model, corner, die, 'vcc_ibis')
            if pin != '4':
                self.deck.probes.append(Probe(label, die, value, group=self.group))
            return
        if part is None:
            raise ValueError(f'{label}: part {value} has no receiver model')
        die = self.uid('rx')
        self.deck.lines += [f'L{self.uid("l")} {node} {die} {part.l_pkg:g}',
                            f'C{self.uid("r")} {die} 0 {part.c_in[self.cfg.rx_c]:g}']
        self.deck.probes.append(Probe(label, die, value, group=self.group))

    def receiver_options(self, node):
        """What-if parts at an iCE40 receiver pad (fix studies, cfg.extra keys;
        absent keys leave the as-built board unchanged):
        rx_series ohm   resistor in series with the pad, then the package
        rx_shunt (ohm, F)  R+C from the pad to ground (AC termination)
        rx_diode        Schottky (BAT54-class) clamps from the pad to the rail
                        and to ground
        rx_extra_c F    added pad capacitance (the data sheet's 6 pF I/O C)"""
        cfg = self.cfg
        if cfg.get('rx_extra_c'):
            self.deck.lines.append(f'C{self.uid("xc")} {node} 0 {cfg.get("rx_extra_c"):g}')
        if cfg.get('rx_shunt'):
            r, c = cfg.get('rx_shunt')
            mid = self.uid('sh')
            self.deck.lines += [f'R{self.uid("sr")} {node} {mid} {r:g}',
                                f'C{self.uid("sc")} {mid} 0 {c:g}']
        if cfg.get('rx_diode'):
            if SCHOTTKY_MODEL not in self.deck.lines:
                self.deck.lines.append(SCHOTTKY_MODEL)
            self.deck.lines += [f'D{self.uid("du")} {node} vcc_ibis DSCH',
                                f'D{self.uid("dd")} 0 {node} DSCH']
        if cfg.get('rx_series'):
            after = self.uid('rs')
            self.deck.lines.append(f'R{self.uid("rs")} {node} {after} {cfg.get("rx_series"):g}')
            node = after
        return node

    def package(self, node, label):
        pkg = models.TQ144_ENVELOPE[self.cfg.package]
        die, mid = self.uid('d'), self.uid('pm')
        self.deck.lines += [f'C{self.uid("pc")} {node} 0 {pkg["c_pf"] * 1e-12:g}',
                            f'L{self.uid("pl")} {node} {mid} {pkg["l_nh"] * 1e-9:g}',
                            f'R{self.uid("pr")} {mid} {die} {pkg["r"]:g}']
        return die

    def cable_end(self, node, pin):
        """The e-ink card's J2 pin through the panel cable; returns far node."""
        if pin in self.cables:
            return self.cables[pin][-1]
        z0 = self.cfg.get('cable_z', 150.0)
        length = self.cfg.get('cable_m', .2)
        sections = max(4, math.ceil(length / .01))
        td = CABLE_S_PER_M * length / sections
        nodes, prev = [node], node
        for k in range(sections):
            nxt, mid = self.uid('cb'), self.uid('cm')
            self.deck.lines += [f'L{self.uid("cl")} {prev} {mid} {z0 * td:g}',
                                f'R{self.uid("cr")} {mid} {nxt} {CABLE_R_PER_M * length / sections:g}',
                                f'C{self.uid("cc")} {nxt} 0 {td / z0:g}']
            nodes.append(nxt)
            prev = nxt
        self.cables[pin] = nodes
        self.cable_inductors = getattr(self, 'cable_inductors', {})
        return nodes[-1]

    def connector_load(self, inst, kind, ref, pin, value, node):
        both_loads(self, inst, kind, ref, pin, value, node)


# ------------------------------------------------------------ drivers
def ibis_driver(edges, t_end, level=0.0):
    def attach(asm, node, kind, ref, pin, value):
        if value == 'ICE40HX4K-TQ144':
            name = asm.bench.ice40_model(pin)
            model = asm.ice40[name]
            die = asm.package(node, f'{ref}.{pin}')
        elif value == '74LVC1G125GW' and pin == '4':
            name, model = 'TI SN74LVC1G125 LVC1G125_OUT_33 (proxy)', asm.lvc['out']
            die = asm.uid('lvd')
            asm.deck.lines.append(f'L{asm.uid("ll")} {die} {node} {LVC125_L_PKG:g}')
        else:
            raise ValueError(f'{ref}.{pin}: no IBIS driver for {value}')
        ku, kd = models.ku_schedule(model, asm.cfg.corner, edges, t_end, level)
        nku, nkd = asm.uid('ku'), asm.uid('kd')
        asm.deck.lines += [models.pwl_source(nku, nku, ku), models.pwl_source(nkd, nkd, kd)]
        asm.deck.lines += models.ibis_device_lines(asm.uid('drv'), model, asm.cfg.corner, die,
                                                   'vcc_ibis', nku, nkd)
        asm.deck.probes.append(Probe(f'driver {ref}.{pin}', die, value, 'tx', asm.group))
        asm.deck.notes.append(f'driver {ref}.{pin} IBIS {name} {asm.cfg.corner}')
    return attach


def bracket_driver(part, edges, t_end, level=0.0):
    def attach(asm, node, kind, ref, pin, value):
        r_out, t_rise = DRIVE[part][asm.cfg.bracket]
        src, die = asm.uid('bs'), asm.uid('bd')
        pts = (models.ramp_points(edges, t_rise, asm.vdd, t_end) if edges else
               [(0.0, level * asm.vdd), (t_end, level * asm.vdd)])
        if kind == 'eink' and ref == 'J2':
            node = asm.cable_end(node, pin)       # the HAT drives from the cable's far end
        asm.deck.lines += [models.pwl_source(src, src, pts),
                           f'R{asm.uid("bo")} {src} {die} {r_out:g}',
                           f'C{asm.uid("bc")} {die} 0 {PARTS[part].c_in[0] if part in PARTS else 1e-12:g}',
                           f'L{asm.uid("bl")} {die} {node} {PARTS[part].l_pkg if part in PARTS else 1e-9:g}']
        asm.deck.probes.append(Probe(f'driver {ref}.{pin}', die, part, 'tx', asm.group))
        asm.deck.notes.append(f'driver {ref}.{pin} bracket {part} R={r_out} tr={t_rise}')
    return attach


# ----------------------------------------------------------- simulation
def run_deck(deck, vdd, t_end, step, workdir):
    probes = [p for p in deck.probes]
    lines = ['* CUPC8 slow-bus SI (hw/si/slowbus_si.py)',
             f'Vvcc_ibis vcc_ibis 0 {vdd:g}'] + deck.lines
    lines += ['.options method=gear reltol=1e-4 abstol=1e-10 vntol=1e-5 itl4=200',
              '.control', 'set noaskquit', f'tran {step:g} {t_end:g} 0 {step:g}',
              'wrdata wave.dat ' + ' '.join(f'v({p.node})' for p in probes),
              'quit', '.endc', '.end']
    work = Path(workdir)
    (work / 'deck.cir').write_text('\n'.join(lines) + '\n')
    run = subprocess.run(['ngspice', '-b', 'deck.cir'], cwd=work, capture_output=True,
                         text=True, timeout=3600)
    data_path = work / 'wave.dat'
    if run.returncode or not data_path.is_file():
        raise RuntimeError(f'ngspice failed: {run.stdout[-800:]} {run.stderr[-800:]}')
    if re.search(r'timestep too small|singular matrix|no convergence', run.stdout + run.stderr, re.I):
        raise RuntimeError('ngspice convergence failure: ' + (run.stdout + run.stderr)[-800:])
    data = np.loadtxt(data_path)
    if data.ndim != 2 or data.shape[1] != 2 * len(probes) or not np.all(np.isfinite(data)):
        raise RuntimeError('incomplete ngspice output')
    return data[:, 0], data[:, 1::2]


def evaluate(t, v, part_name, edges, t_end, vdd, driver_t=None):
    """Per-edge checks at one receiver; returns (metrics, failures)."""
    part = PARTS[part_name]
    vih, vil = part.vih, part.vil
    fails = []
    vmax, vmin = float(np.max(v)), float(np.min(v))
    hi = part.abs_max(vdd)
    for label, sign, dc, ac in (('overshoot', 1, hi, part.ac_max(vdd)),
                                ('undershoot', -1, part.abs_lo, part.ac_lo)):
        beyond = sign * (v - dc) > 0
        if not beyond.any():
            continue
        peak = vmax if sign > 0 else vmin
        if ac is None:
            fails.append(f'{label} {peak:.3f} V beyond abs max {dc:.3f} V')
            continue
        edges_ = np.flatnonzero(np.diff(beyond.astype(int)))
        starts = [0] if beyond[0] else []
        starts += [e + 1 for e in edges_ if not beyond[e]]
        longest = 0.0
        for a in starts:
            b = a
            while b + 1 < len(v) and beyond[b + 1]:
                b += 1
            longest = max(longest, t[b] - t[a])
        if sign * (peak - ac) > 0 or longest > part.ac_width:
            fails.append(f'{label} {peak:.3f} V for {longest * 1e9:.2f} ns beyond abs max '
                         f'{dc:.3f} V (AC allowance {ac:.3f} V for {part.ac_width * 1e9:.1f} ns)')
    arrivals = []
    for i, (t0, edge) in enumerate(edges):
        t1 = edges[i + 1][0] if i + 1 < len(edges) else t_end
        w = (t >= t0) & (t < t1)
        tw, vw = t[w], v[w]
        if edge == 'fall':
            vw = -vw
            lo, hi_ = -vih, -vil
        else:
            lo, hi_ = vil, vih
        enter = np.flatnonzero(vw >= lo)
        done = np.flatnonzero(vw >= hi_)
        if not len(done):
            fails.append(f'{edge} at {t0 * 1e9:.1f} ns never crosses {"VIH" if edge == "rise" else "VIL"}')
            arrivals.append(None)
            continue
        a, b = (enter[0] if len(enter) else done[0]), done[0]
        band = vw[a:b + 1]
        drop = float(np.max(np.maximum.accumulate(band) - band)) if len(band) else 0.0
        if drop > 1e-3:
            fails.append(f'{edge} at {t0 * 1e9:.1f} ns non-monotonic in threshold band ({drop * 1e3:.1f} mV)')
        after = vw[b:]
        back = float(hi_ - np.min(after))
        if back > 0:
            fails.append(f'{edge} at {t0 * 1e9:.1f} ns rings back {back * 1e3:.0f} mV into the band')
        # arrival: last time the threshold is crossed (== first when clean)
        below = np.flatnonzero(after < hi_)
        crossing = tw[b + int(below[-1]) + 1] if len(below) and b + below[-1] + 1 < len(tw) \
            else tw[b] if not len(below) else tw[-1]
        t_vil = tw[a]
        arrivals.append({'edge': edge, 't_launch_ns': round(t0 * 1e9, 4),
                         'first_band_ns': round((t_vil - t0) * 1e9, 4),
                         'settled_ns': round((crossing - t0) * 1e9, 4),
                         'ringback_margin_v': round(-back, 4),
                         'monotonic_drop_mv': round(drop * 1e3, 3)})
    return {'vmax': round(vmax, 4), 'vmin': round(vmin, 4),
            'overshoot_margin_v': round(hi - vmax, 4),
            'undershoot_margin_v': round(vmin - part.abs_lo, 4),
            'edges': arrivals}, fails


# ------------------------------------------------------ off-board loads
# The e-ink panel's Waveshare e-Paper Driver HAT (Rev 2.3) plugs into J2 by
# its ~20 cm GH1.25-to-Dupont 9-wire cable (doc/hardware/eink-card.md). No
# maker data exists for the loose-wire cable: its impedance, length and
# wire-to-wire coupling are swept. The HAT's J2-side logic inputs are a
# TXB0108 B port (TI IBIS input model); PWR drives the HAT's S8050 base
# through 10 kohm with 100 kohm to ground.
CABLE_S_PER_M = 5e-9          # insulated wire in air, eff. Dk ~2.25
CABLE_R_PER_M = .2            # 28 AWG copper
EPD_TXB_PINS = {'3': 'DIN', '4': 'CLK', '5': 'CS', '6': 'DC', '7': 'RST'}


def epd_load(asm, inst, kind, ref, pin, value, node):
    if kind != 'eink' or ref != 'J2':
        raise ValueError(f'{inst}:{ref}.{pin} ({value}) connector has no model')
    if pin in ('1', '2'):
        raise ValueError(f'J2.{pin} is a supply pin')
    far = asm.cable_end(node, pin)
    label = f'{inst}:HAT {EPD_TXB_PINS.get(pin, "J2." + pin)} (TXB0108 B)'
    if pin in EPD_TXB_PINS:
        asm.deck.lines += models.ibis_device_lines(asm.uid('t'), asm.txb, asm.cfg.corner
                                                   if asm.cfg.corner in models.CORNERS else 'typ',
                                                   far, 'vcc_ibis')
        asm.deck.probes.append(Probe(label, far, 'TXB0108', group=asm.group))
    elif pin == '9':
        base = asm.uid('qb')
        asm.deck.lines += [f'R{asm.uid("q")} {far} {base} 10k', f'R{asm.uid("q")} {base} 0 100k',
                           f'D{asm.uid("q")} {base} 0 dbe']
        if '.model dbe D(IS=1e-14 N=1)' not in asm.deck.lines:
            asm.deck.lines.append('.model dbe D(IS=1e-14 N=1)')
    elif pin != '8':
        raise ValueError(f'eink J2.{pin}: no HAT model')


def microsd_load(asm, inst, kind, ref, pin, value, node):
    """A microSD card in the TF-01A socket: contact L and CCARD bracket."""
    if kind != 'storage' or ref != 'J2':
        raise ValueError(f'{inst}:{ref}.{pin} ({value}) connector has no model')
    if pin not in ('1', '2', '3', '5', '7', '8'):
        raise ValueError(f'storage J2.{pin} is not a card signal contact')
    part = PARTS['microSD']
    die = asm.uid('sd')
    asm.deck.lines += [f'L{asm.uid("sl")} {node} {die} {part.l_pkg:g}',
                       f'C{asm.uid("sc")} {die} 0 {part.c_in[asm.cfg.rx_c]:g}']
    asm.deck.probes.append(Probe(f'{inst}:card {asm.bench.circuit(kind).pin_names.get((ref, pin), pin)}',
                                 die, 'microSD', group=asm.group))


def both_loads(asm, inst, kind, ref, pin, value, node):
    if kind == 'eink':
        return epd_load(asm, inst, kind, ref, pin, value, node)
    if kind == 'storage':
        return microsd_load(asm, inst, kind, ref, pin, value, node)
    if kind == 'main' and ref == 'J4':
        return                                          # AUX SPI header, unfitted
    raise ValueError(f'{inst}:{ref}.{pin} ({value}) connector has no model')


# ------------------------------------------------------------ run helpers
@dataclass(frozen=True)
class Drive:
    start: tuple                  # (inst, kind, ref, pin)
    model: str                    # 'ibis' or a DRIVE key
    edges: tuple = ()
    level: float = 0.0            # quiet level when edges == ()


@dataclass(frozen=True)
class Case:
    group: str
    name: str
    drives: tuple
    config: Config
    t_end: float
    step: float = 10e-12
    couple: tuple = ()            # (pin a, pin b, k) cable wire coupling


def simulate(case, bench_dir, dump=None):
    bench = Bench(bench_dir)
    ice40 = models.load_ice40()
    corner = case.config.corner
    lvc = models.load_lvc125(OUT_DIR / 'cache/scem270.zip')
    first = case.drives[0]
    if first.model == 'ibis':
        value = bench.circuit(first.start[1]).components[first.start[2]][0]
        vdd = (lvc['out'] if value == '74LVC1G125GW' else ice40['lvc330io']).vcc[corner]
    else:
        vdd = 3.3
    asm = Assembler(bench, case.config, vdd)
    asm.ice40, asm.lvc = ice40, lvc
    asm.tpd = models.load_tpd(OUT_DIR / 'cache/slvm741a.zip')
    asm.txb = models.load_txb(OUT_DIR / 'cache/scem518.zip')
    for index, drive in enumerate(case.drives):
        asm.group = index
        driver = (ibis_driver(list(drive.edges), case.t_end, drive.level) if drive.model == 'ibis'
                  else bracket_driver(drive.model, list(drive.edges), case.t_end, drive.level))
        asm.assemble(drive.start, driver)
    for pin_a, pin_b, k in case.couple:
        a, b = asm.cables[pin_a], asm.cables[pin_b]
        # per section: capacitive coupling C_m = k C, inductive K = k
        la = [l for l in asm.deck.lines if l.startswith('L') and l.split()[1] in a[:-1]]
        lb = [l for l in asm.deck.lines if l.startswith('L') and l.split()[1] in b[:-1]]
        for x, y in zip(la, lb):
            asm.deck.lines.append(f'K{asm.uid("x")} {x.split()[0]} {y.split()[0]} {k:g}')
        c_sec = float([l for l in asm.deck.lines if l.startswith('C') and l.split()[1] == a[1]][0].split()[3])
        for na, nb in zip(a[1:], b[1:]):
            asm.deck.lines.append(f'C{asm.uid("xc")} {na} {nb} {k * c_sec:g}')
    deck = asm.deck
    with tempfile.TemporaryDirectory(prefix='cupc8-slowbus-') as work:
        t, waves = run_deck(deck, vdd, case.t_end, case.step, work)
    if dump:
        np.savez_compressed(dump, t=t, waves=waves,
                            labels=np.array([p.label for p in deck.probes]))
    result = {'group': case.group, 'case': case.name, 'config': _cfg_json(case.config),
              'vdd': vdd, 'notes': deck.notes, 'receivers': {}, 'drivers': {}, 'failures': []}
    for probe, v in zip(deck.probes, waves.T):
        drive = case.drives[probe.group]
        if probe.role == 'tx':
            info = {'vmax': round(float(v.max()), 4), 'vmin': round(float(v.min()), 4)}
            part = PARTS.get(probe.part)
            if part is not None:        # reflections back into the driving pad
                hi = part.abs_max(vdd)
                if v.max() > (part.ac_max(vdd) or hi) or v.min() < (part.ac_lo or part.abs_lo):
                    result['failures'].append(f'{probe.label}: driver pad {v.min():.3f}..'
                                              f'{v.max():.3f} V beyond its limits')
            result['drivers'][probe.label] = info
            continue
        if drive.edges:
            metrics, fails = evaluate(t, v, probe.part, drive.edges, case.t_end, vdd)
        else:
            metrics, fails = quiet(t, v, probe.part, drive.level, vdd)
        metrics['part'] = probe.part
        result['receivers'][probe.label] = metrics
        result['failures'] += [f'{probe.label}: {f}' for f in fails]
    result['nets'] = deck.nets
    return result


def quiet(t, v, part_name, level, vdd):
    """A victim held at `level` must stay out of its receiver's threshold band."""
    part = PARTS[part_name]
    fails = []
    if level == 0:
        peak = float(np.max(v))
        margin = part.vil - peak
        if margin <= 0:
            fails.append(f'quiet-low victim reaches {peak:.3f} V >= VIL {part.vil:.3f} V')
    else:
        peak = float(np.min(v))
        margin = peak - part.vih
        if margin <= 0:
            fails.append(f'quiet-high victim falls to {peak:.3f} V <= VIH {part.vih:.3f} V')
    if np.max(v) > part.abs_max(vdd) or np.min(v) < part.abs_lo:
        fails.append('quiet victim beyond abs max')
    return {'vmax': round(float(np.max(v)), 4), 'vmin': round(float(np.min(v)), 4),
            'noise_margin_v': round(margin, 4)}, fails


def _cfg_json(config):
    out = {k: getattr(config, k) for k in ('slots', 'corner', 'bracket', 'rx_c', 'package',
                                           'connector', 'zscale', 'section_mm')}
    out['slots'] = list(out['slots'])
    out.update({k: v for k, v in config.extra if isinstance(v, (int, float, str))})
    return out


def _run_one(args):
    case, bench_dir = args
    try:
        return simulate(case, bench_dir)
    except Exception as error:  # a crashed case is a failed case
        return {'group': case.group, 'case': case.name, 'config': _cfg_json(case.config),
                'failures': [f'simulation error: {type(error).__name__}: {error}'],
                'receivers': {}, 'drivers': {}}


def run_cases(cases, bench_dir, jobs, progress=None):
    results = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=jobs) as pool:
        for n, result in enumerate(pool.map(_run_one, [(c, bench_dir) for c in cases],
                                            chunksize=1), 1):
            results.append(result)
            if progress and n % 50 == 0:
                progress(f'{n}/{len(cases)} cases')
    return results


def convergence(case, bench_dir, reference):
    """Re-run with half the section length and half the time step; compare."""
    config = Config(**{**case.config.__dict__, 'section_mm': case.config.section_mm / 2})
    fine = Case(case.group, case.name + ' [refined]', case.drives, config, case.t_end,
                case.step / 2, case.couple)
    refined = simulate(fine, bench_dir)
    worst = {'v': 0.0, 'ns': 0.0}
    for label, metrics in reference['receivers'].items():
        other = refined['receivers'].get(label)
        if other is None:
            return {'ok': False, 'reason': f'{label} missing in refined run'}
        worst['v'] = max(worst['v'], abs(metrics['vmax'] - other['vmax']),
                         abs(metrics['vmin'] - other['vmin']))
        for a, b in zip(metrics.get('edges', []), other.get('edges', [])):
            if a and b:
                worst['ns'] = max(worst['ns'], abs(a['settled_ns'] - b['settled_ns']))
    def kinds(failures):
        return sorted({re.sub(r'-?[\d.]+', '#', f) for f in failures})
    same = kinds(refined['failures']) == kinds(reference['failures'])
    ok = worst['v'] <= .03 and worst['ns'] <= .05 and same
    return {'case': case.name, 'ok': ok, 'max_delta_v': round(worst['v'], 5),
            'max_delta_ns': round(worst['ns'], 5),
            'same_verdict': same,
            'criterion': 'half section length and half time step: peaks within 30 mV, '
                         'arrivals within 50 ps, identical failures'}


def clock_edges(freq, cycles=1, start=2e-9):
    half = .5 / freq
    edges = []
    for k in range(cycles):
        edges += [(start + 2 * k * half, 'rise'), (start + (2 * k + 1) * half, 'fall')]
    return tuple(edges), start + 2 * cycles * half


def sweep(base, **axes):
    """Cartesian product of Config axes over a base Config."""
    configs = [base]
    for key, values in axes.items():
        configs = [Config(**{**c.__dict__, key: v}) for c in configs for v in values]
    return configs


# ------------------------------------------------------------------- rows
SPI_HZ, SD_HZ, EPD_HZ, BUS_HZ = 6e6, 12.5e6, 10e6, 12e6
IBIS_AXES = dict(corner=('min', 'max'), package=(0, 1), zscale=(.9, 1.1), rx_c=(0, 1),
                 connector=(0, 1))
LVC_AXES = dict(corner=('min', 'max'), zscale=(.9, 1.1), rx_c=(0, 1), connector=(0, 1))
BRACKET_AXES = dict(bracket=(0, 1), zscale=(.9, 1.1), rx_c=(0, 1), connector=(0, 1))
CABLE_AXES = dict(bracket=(0, 1), zscale=(.9, 1.1), rx_c=(0, 1))
CABLE_BOUNDS = dict(cable_z=(100.0, 300.0), cable_m=(.15, .3))
EMPTY = (None,) * 6


def slot_configs(kinds=CARD_KINDS, singles=('storage',)):
    configs = [(f'all {k}', (k,) * 6) for k in kinds]
    for k in singles:
        configs += [(f'{k} in J{11 + n} only', tuple(k if i == n else None for i in range(6)))
                    for n in range(6)]
    return configs


def driver_pin(bench, kind, net, part):
    pins = [(r, p) for r, p in bench.circuit(kind).nets[net]
            if bench.circuit(kind).components[r][0] == part]
    if len(pins) != 1:
        raise ValueError(f'{kind} {net}: expected one {part} pin, found {pins}')
    return pins[0]


def cases_for(group, name, drives, axes, base, t_end, couple=()):
    out = []
    for config in sweep(base, **axes):
        tag = ','.join(f'{k}={getattr(config, k) if hasattr(config, k) else config.get(k)}'
                       for k in axes)
        out.append(Case(group, f'{name} [{tag}]', drives, config, t_end, couple=couple))
    return out


def extra_sweep(base_cases, **bounds):
    out = []
    for case in base_cases:
        configs = [case.config]
        for key, values in bounds.items():
            configs = [Config(**{**c.__dict__, 'extra': tuple(dict(c.extra, **{key: v}).items())})
                       for c in configs for v in values]
        for c in configs:
            tag = ','.join(f'{k}={c.get(k)}' for k in bounds)
            out.append(Case(case.group, f'{case.name} [{tag}]', case.drives, c, case.t_end,
                            case.step, case.couple))
    return out


def mb_spi_cases(bench, kinds=CARD_KINDS, singles=('storage',)):
    cases = []
    clock, t_end = clock_edges(SPI_HZ)
    data, t_data = clock_edges(SPI_HZ / 2)
    for signal, net, edges, te in (('SCK', '/SPI_SCK_SRC', clock, t_end),
                                   ('MOSI', '/SPI_MOSI_SRC', data, t_data)):
        ref, pin = driver_pin(bench, 'main', net, 'ICE40HX4K-TQ144')
        for label, slots in slot_configs(kinds, singles):
            cases += cases_for(f'MB spi {signal}', f'{signal} {label}',
                               (Drive(('main', 'main', ref, pin), 'ibis', edges),),
                               IBIS_AXES, Config(slots), te)
    for n in range(6):
        ref, pin = driver_pin(bench, 'main', f'/SPI_nCS{n}_SRC', 'ICE40HX4K-TQ144')
        for kind in kinds:
            slots = tuple(kind if i == n else None for i in range(6))
            cases += cases_for('MB spi CS', f'SLOT{n + 1}_CS_n {kind}',
                               (Drive(('main', 'main', ref, pin), 'ibis', data),),
                               IBIS_AXES, Config(slots), t_data)
    for n in range(6):
        for kind in kinds:
            buf = driver_pin(bench, kind, '/MISO', '74LVC1G125GW')
            for label, slots in ((f'all {kind}', (kind,) * 6),
                                 (f'{kind} alone', tuple(kind if i == n else None for i in range(6)))):
                cases += cases_for('MB spi MISO', f'MISO J{11 + n} {label}',
                                   (Drive((f'J{11 + n}:{kind}', kind, *buf), 'ibis', data),),
                                   LVC_AXES, Config(slots), t_data)
    return cases


def mb_memory_cases(bench):
    cases = []
    data, t_data = clock_edges(BUS_HZ / 2)
    axes = {k: v for k, v in IBIS_AXES.items() if k != 'connector'}
    raxes = {k: v for k, v in BRACKET_AXES.items() if k != 'connector'}
    circuit = bench.circuit('main')
    nets = [n for n in circuit.nets if n.startswith('/MEM_')]
    for net in sorted(nets):
        ref, pin = driver_pin(bench, 'main', net, 'ICE40HX4K-TQ144')
        cases += cases_for('MB memory', f'{net[1:]} chipset drives',
                           (Drive(('main', 'main', ref, pin), 'ibis', data),), axes,
                           Config(EMPTY), t_data)
        if net.startswith('/MEM_D'):
            for part in ('IS62WV5128EBLL-45HLI', 'SST39VF040'):
                mref, mpin = driver_pin(bench, 'main', net, part)
                cases += cases_for('MB memory', f'{net[1:]} {part} drives',
                                   (Drive(('main', 'main', mref, mpin), part, data),), raxes,
                                   Config(EMPTY, corner='typ'), t_data)
    return cases


def mb_socket_cases(bench):
    """Chipset-driven CPU socket signals: U7 -> 56 ohm -> J2 -> CPU card."""
    cases = []
    data, t_data = clock_edges(BUS_HZ / 2)
    circuit = bench.circuit('main')
    for net in sorted(circuit.nets):
        if not net.startswith('/CPU_') or not net.endswith('_SRC'):
            continue
        ref, pin = driver_pin(bench, 'main', net, 'ICE40HX4K-TQ144')
        cases += cases_for('MB cpu socket', f'{net[1:-4]} chipset drives',
                           (Drive(('main', 'main', ref, pin), 'ibis', data),), IBIS_AXES,
                           Config(EMPTY), t_data)
    return cases


def clock_cases(bench):
    clock, t_end = clock_edges(BUS_HZ, cycles=2)
    ref, pin = [(r, p) for r, p in bench.circuit('main').nets['/OSC_OUT'] if r.startswith('Y')][0]
    return cases_for('clocks', 'OSC_OUT -> CLK12, CPU_CLK',
                     (Drive(('main', 'main', ref, pin), 'oscillator', clock),),
                     BRACKET_AXES, Config(EMPTY, corner='typ'), t_end)


def cc_bus_cases(bench):
    """The 31 CPU-FPGA outputs: U1 -> RN 68 ohm -> J1 finger -> socket -> U7."""
    cases = []
    data, t_data = clock_edges(BUS_HZ / 2)
    circuit = bench.circuit('cpu')
    for r in circuit.resistors:
        if not r.ref.startswith('RN'):
            continue
        ends = {}
        for net in r.ends:
            members = circuit.nets[net]
            if any(ref == 'U1' for ref, _ in members):
                ends['fpga'] = [(ref, p) for ref, p in members if ref == 'U1']
            if any(ref == 'J1' for ref, _ in members):
                ends['finger'] = net
        if set(ends) != {'fpga', 'finger'} or len(ends['fpga']) != 1:
            continue
        ref, pin = ends['fpga'][0]
        cases += cases_for('CC cpu bus', f'{ends["finger"][1:]} CPU FPGA drives',
                           (Drive(('cpu', 'cpu', ref, pin), 'ibis', data),), IBIS_AXES,
                           Config(EMPTY), t_data)
    return cases


def sc_cases(bench):
    cases = []
    clock, t_clock = clock_edges(SD_HZ, cycles=2)
    data, t_data = clock_edges(SD_HZ / 2)
    axes = {k: v for k, v in BRACKET_AXES.items() if k != 'connector'}
    for net, edges, te in (('/SD_SCK', clock, t_clock), ('/SD_MOSI', data, t_data),
                           ('/SD_nCS', data, t_data), ('/MISO_OUT', data, t_data)):
        ref, pin = driver_pin(bench, 'storage', net, 'RP2040')
        cases += cases_for('SC storage', f'{net[1:]} RP2040 drives',
                           (Drive(('storage', 'storage', ref, pin), 'RP2040', edges),), axes,
                           Config(EMPTY, corner='typ'), te)
    cases += cases_for('SC storage', 'SD_MISO card drives',
                       (Drive(('storage', 'storage', 'J2', '7'), 'microSD', data),), axes,
                       Config(EMPTY, corner='typ'), t_data)
    return cases


def ec_cases(bench):
    cases = []
    clock, t_clock = clock_edges(EPD_HZ, cycles=2)
    data, t_data = clock_edges(EPD_HZ / 2)
    for net, edges, te in (('/EPD_CLK', clock, t_clock), ('/EPD_DIN', data, t_data),
                           ('/EPD_nCS', data, t_data), ('/EPD_DC', data, t_data),
                           ('/EPD_nRST', data, t_data), ('/EPD_PWR', data, t_data),
                           ('/MISO_OUT', data, t_data)):
        ref, pin = driver_pin(bench, 'eink', net, 'RP2040')
        base = cases_for('EC eink', f'{net[1:]} RP2040 drives',
                         (Drive(('eink', 'eink', ref, pin), 'RP2040', edges),), CABLE_AXES,
                         Config(EMPTY, corner='typ'), te)
        cases += extra_sweep(base, **CABLE_BOUNDS) if net != '/MISO_OUT' else base
    base = cases_for('EC eink', 'EPD_BUSY HAT drives',
                     (Drive(('eink', 'eink', 'J2', '8'), 'TXB0108', data),), CABLE_AXES,
                     Config(EMPTY, corner='typ'), t_data)
    cases += extra_sweep(base, **CABLE_BOUNDS)
    # loose cable wire-to-wire coupling: CLK toggling next to quiet DIN / CS
    clk = driver_pin(bench, 'eink', '/EPD_CLK', 'RP2040')
    for victim, vnet in (('3', '/EPD_DIN'), ('5', '/EPD_nCS')):
        vref, vpin = driver_pin(bench, 'eink', vnet, 'RP2040')
        for level in (0.0, 1.0):
            for k in (.1, .3):
                base = cases_for('EC eink crosstalk',
                                 f'CLK -> {vnet[1:]} quiet {"high" if level else "low"} k={k}',
                                 (Drive(('eink', 'eink', vref, vpin), 'RP2040', (), level),
                                  Drive(('eink', 'eink', *clk), 'RP2040', clock)),
                                 {'bracket': (0,), 'zscale': (1.0,), 'rx_c': (0, 1)},
                                 Config(EMPTY, corner='typ'), t_clock, couple=((victim, '4', k),))
                cases += extra_sweep(base, **CABLE_BOUNDS)
    return cases


ROWS = {
    'MB-007': ('MB spi SCK', 'MB spi MOSI', 'MB spi CS', 'MB spi MISO', 'MB memory',
               'MB cpu socket', 'clocks'),
    'CC-007': ('CC cpu bus', 'clocks'),
    'SC-007': ('SC storage', 'MB spi SCK', 'MB spi MOSI', 'MB spi CS', 'MB spi MISO'),
    'EC-007': ('EC eink', 'EC eink crosstalk', 'MB spi SCK', 'MB spi MOSI', 'MB spi CS',
               'MB spi MISO'),
}


def build_cases(bench, row):
    groups = ROWS[row]
    cases = []
    if row == 'SC-007':
        cases += mb_spi_cases(bench, kinds=('storage',))
    elif row == 'EC-007':
        cases += mb_spi_cases(bench, kinds=('eink',), singles=('eink',))
    elif any(g.startswith('MB spi') for g in groups):
        cases += mb_spi_cases(bench)
    if 'MB memory' in groups:
        cases += mb_memory_cases(bench)
    if 'MB cpu socket' in groups:
        cases += mb_socket_cases(bench)
    if 'clocks' in groups:
        cases += clock_cases(bench)
    if 'CC cpu bus' in groups:
        cases += cc_bus_cases(bench)
    if 'SC storage' in groups:
        cases += sc_cases(bench)
    if 'EC eink' in groups:
        cases += ec_cases(bench)
    return cases


# ----------------------------------------------------------- assumptions
ASSUMPTIONS = [
    'RP2040: no IBIS, pin capacitance or edge rate is published; drivers swept 20 ohm/0.5 ns '
    '(fast, below Figure 171 typical 4 mA) to 170 ohm/5 ns (Table 625 VOH), inputs 1..10 pF, '
    '1 nH package, no clamp diodes (overstates overshoot)',
    'ESP32-C3 (wifi slot): no IBIS or IO abs max; VIH max VDD+0.3 / VIL min -0.3 used as limits; '
    'inputs 1..10 pF; no SPI-slave AC timing is published, so wifi-slot SPI timing is not verified',
    '74LVC1G125GW (card MISO buffer): TI SN74LVC1G125 IBIS used as a same-family proxy for the '
    'Nexperia part; Nexperia limits (VI -0.5..6.5 V, tpd <= 4.5 ns) apply',
    'SRAM/ROM/oscillator/SD card/TXB0108 outputs: behavioural bracket drivers (DRIVE)',
    'slot/socket contact: 1..5 nH, 0.3..1.5 pF, 30 mOhm (no per-contact data; bounded by a '
    'PCIe-CEM-class return-loss limit)',
    'line constants: 2D field solution (hw/si/slowbus_field.py) of every track piece\'s local '
    'cross-section: the JLCPCB stack, the plane and pour fill actually under/over it and the '
    'same-layer pour gap (solder mask ignored); Z0 swept +/-10 % (the fab\'s impedance '
    'tolerance); DC copper loss only (conservative for ringing); vias: Johnson/Graham barrel L '
    'and pad C with a 0.3 mm plane clearance; pieces over a plane clearance use the declared '
    'planes and are reported as unreferenced length',
    'iCE40 TQ144 package: the envelope of the two commented TQ144 [Package] rows',
    'e-ink panel cable: 100..300 ohm, 0.15..0.30 m, 5 ns/m, wire-to-wire coupling k 0.1..0.3',
    'microSD socket + card contact 2 nH; card input 1..10 pF (CCARD <= 10 pF)',
    'crosstalk: field-solved Kb/Kf bound per coupled piece (victim coplanar pour ignored), '
    'all aggressors switching together at 0.34 ns and 3.6 V; no terminations credited',
]

# RP2040 PIO slot slave (fw/rp2040/common/slotspi.pio): clk_sys 125 MHz
# (pico-sdk default; the GPU card runs faster). Table 630 pad-to-synchroniser
# delay 1.83..5.25 ns, Table 629 flop-to-pad 2.05..7.10 ns (both at IOVDD
# 1.8 V, the slower case).
T_SYS = 8e-9
RP_IN_MIN, RP_IN_MAX, RP_OUT_MIN, RP_OUT_MAX = 1.83e-9, 5.25e-9, 2.05e-9, 7.10e-9
PIO_RESPONSE_CYCLES = 6       # sync (2) + phase (1) + wait retire + jmp + out
LVC125_TPD_MAX = 4.5e-9       # Nexperia Table 8, VCC 3.0..3.6 V, -40..85 C
SD_TISU, SD_TIH, SD_TODLY, SD_TTLH = 5e-9, 5e-9, 14e-9, 10e-9
SD_CL_HOST_BUS, SD_L_MAX = 30e-12, 16e-9
UC_SDS, UC_SDH, UC_SHW, UC_CYC = 30e-9, 30e-9, 35e-9, 100e-9
TXB_SKEW = 5.4e-9 - .5e-9     # tpd B->A 0.5..5.4 ns (SCES643L 5.21)
CLOCK_NETS = ('SCK', 'CLK')


# ------------------------------------------------------------- row checks
def _edges(results, group, label_pred, edge):
    """All (first_band, settled) arrival pairs, ns, for matching receivers."""
    out = []
    for r in results:
        if r['group'] != group:
            continue
        for label, m in r['receivers'].items():
            if not label_pred(label):
                continue
            for e in m.get('edges') or []:
                if e and e['edge'] == edge:
                    out.append((e['first_band_ns'] * 1e-9, e['settled_ns'] * 1e-9))
    return out


def _span(pairs):
    if not pairs:
        return None
    return min(a for a, _ in pairs), max(b for _, b in pairs)


def timing_checks(row, results):
    items, ok = [], True

    def add(name, margin, detail, required=True):
        nonlocal ok
        good = margin is not None and margin >= 0
        if required and not good:
            ok = False
        items.append({'check': name, 'margin_ns': None if margin is None else round(margin * 1e9, 3),
                      'ok': good, 'required': required, 'detail': detail})

    groups = {r['group'] for r in results}

    def need(name, *spans):
        if all(spans):
            return True
        add(name, None, 'arrival data missing (a case failed to simulate)')
        return False

    if 'MB spi SCK' in groups:
        half = .5 / SPI_HZ
        rp = lambda pin: (lambda label: label.endswith(f':U1.{pin}') and 'wifi' not in label)
        sck_r = _span(_edges(results, 'MB spi SCK', rp(4), 'rise'))
        sck_f = _span(_edges(results, 'MB spi SCK', rp(4), 'fall'))
        mosi = [_span(_edges(results, 'MB spi MOSI', rp(5), e)) for e in ('rise', 'fall')]
        if need('slot MOSI setup/hold at RP2040 cards', sck_r, *mosi):
            first = min(m[0] for m in mosi)
            last = max(m[1] for m in mosi)
            skew = RP_IN_MAX - RP_IN_MIN
            add('slot MOSI setup at RP2040 cards (6 MHz)', half + sck_r[0] - last - skew,
                'T/2 + SCK rise earliest - MOSI settled latest - pad skew (Table 630)')
            add('slot MOSI hold at RP2040 cards (6 MHz)',
                2 * half + first - (half + sck_r[1]) - skew - 2 * T_SYS,
                'MOSI changes one period after it launched; PIO samples up to 2 clk_sys '
                '+ pad skew after SCK')
        miso = _span(_edges(results, 'MB spi MISO', lambda l: l.endswith('U7.48'), 'rise') +
                     _edges(results, 'MB spi MISO', lambda l: l.endswith('U7.48'), 'fall'))
        if need('slot MISO turnaround', sck_f, miso):
            sys.path.insert(0, str(ROOT / 'hw/timing'))
            from cpubus_budget import ALLOW
            for hz in (SPI_HZ, 3e6):
                half_ = .5 / hz
                used = (ALLOW['clk_insertion'] * 1e-9 + sck_f[1] + RP_IN_MAX +
                        PIO_RESPONSE_CYCLES * T_SYS + RP_OUT_MAX + LVC125_TPD_MAX + miso[1] +
                        (ALLOW['in_pad'] + ALLOW['setup']) * 1e-9)
                add(f'slot MISO turnaround, RP2040 cards at {hz / 1e6:g} MHz', half_ - used,
                    'clock insertion + SCK fall settled + pad in + PIO response '
                    f'({PIO_RESPONSE_CYCLES} clk_sys) + pad out + 74LVC1G125 tpd + MISO settled '
                    '+ iCE40 in-pad/setup <= T/2', required=(hz == SPI_HZ))
        add('slot SPI timing at the ESP32-C3 (wifi) card', None,
            'no ESP32-C3 SPI-slave AC timing is published', required=row == 'MB-007')
    if 'SC storage' in groups:
        half = .5 / SD_HZ
        card = lambda name: (lambda label: label.endswith(f'card {name}'))
        clk_r = _span(_edges(results, 'SC storage', card('CLK(SCLK)'), 'rise'))
        clk_f = _span(_edges(results, 'SC storage', card('CLK(SCLK)'), 'fall'))
        data = [_span(_edges(results, 'SC storage', card(n), e))
                for n in ('CMD(DI)', 'CDDAT3(CS)') for e in ('rise', 'fall')]
        skew = RP_OUT_MAX - RP_OUT_MIN
        if need('SD input setup/hold', clk_r, *data):
            last, first = max(d[1] for d in data), min(d[0] for d in data)
            add('SD input setup tISU at the card (12.5 MHz)', half + clk_r[0] - last - skew - SD_TISU,
                'T/2 + CLK rise earliest - data settled latest - RP2040 pad skew (Table 629) - tISU')
            add('SD input hold tIH at the card (12.5 MHz)', half + first - clk_r[1] - skew - SD_TIH,
                'data changes T/2 after CLK rises (mode 0)')
        miso = _span(_edges(results, 'SC storage', lambda l: l.endswith('U1.15'), 'rise') +
                     _edges(results, 'SC storage', lambda l: l.endswith('U1.15'), 'fall'))
        if need('SD read', clk_f, miso):
            add('SD read: tODLY + flight within T/2 at the RP2040 (12.5 MHz)',
                half - (clk_f[1] + SD_TODLY + miso[1] + RP_IN_MAX + T_SYS),
                'CLK fall settled + tODLY 14 ns + DO settled + pad in + 1 SSPCLK <= T/2')
        edge_times = [b - a for a, b in _edges(results, 'SC storage', card('CLK(SCLK)'), 'rise') +
                      _edges(results, 'SC storage', card('CLK(SCLK)'), 'fall')]
        if edge_times:
            add('SD CLK transition VIL..VIH <= tTLH/tTHL 10 ns', SD_TTLH - max(edge_times),
                'at the card contact')
    if 'EC eink' in groups:
        half = .5 / EPD_HZ
        hat = lambda n: (lambda label: label.endswith(f'HAT {n} (TXB0108 B)'))
        clk_r = _span(_edges(results, 'EC eink', hat('CLK'), 'rise'))
        clk_f = _span(_edges(results, 'EC eink', hat('CLK'), 'fall'))
        din = [_span(_edges(results, 'EC eink', hat('DIN'), e)) for e in ('rise', 'fall')]
        skew = RP_OUT_MAX - RP_OUT_MIN + TXB_SKEW
        if need('UC8179 DIN setup/hold', clk_r, *din):
            last, first = max(d[1] for d in din), min(d[0] for d in din)
            add('UC8179 DIN setup tSDS (10 MHz)', half + clk_r[0] - last - skew - UC_SDS,
                'T/2 + CLK rise earliest - DIN settled latest - RP2040 pad skew - TXB0108 '
                'tpd spread - 30 ns')
            add('UC8179 DIN hold tSDH (10 MHz)', half + first - clk_r[1] - skew - UC_SDH,
                'DIN changes T/2 after CLK rises')
        if need('UC8179 SCL high/low', clk_r, clk_f):
            add('UC8179 SCL high/low time tSHW/tSLW (10 MHz)',
                half - max(clk_r[1] - clk_f[0], clk_f[1] - clk_r[0]) - TXB_SKEW - UC_SHW,
                'half period less the edge-arrival spread and TXB0108 tpd spread')
        add('UC8179 SCL cycle tSCYCW >= 100 ns', 1 / EPD_HZ - UC_CYC,
            'fw EPD_SPI_HZ 10 MHz; spi_set_baudrate never exceeds the request')
    return {'ok': ok, 'checks': items,
            'summary': ', '.join(f'{i["check"]}: {i["margin_ns"]} ns' for i in items
                                 if i['required'] and not i['ok']) or 'all required checks met'}


def bus_allowance_checks(results):
    """SI arrival vs the flight allowance BUS-005/005B assumed (out_pad 4 ns +
    trace at 7 ps/mm + connector 0.1 ns + 68 ohm RC 2.24 ns for the CPU bus)."""
    sys.path.insert(0, str(ROOT / 'hw/timing'))
    from cpubus_budget import ALLOW, CONNECTOR_NS, PS_PER_MM, RC_NS
    lengths = json.loads((ROOT / 'build/hw/cpubus_lengths.json').read_text())
    worst, bad = {}, []
    for r in results:
        if r['group'] not in ('CC cpu bus', 'MB cpu socket', 'MB memory'):
            continue
        net = r['case'].split()[0]
        copper = sum(n['copper_mm'] for n in r.get('nets', {}).values())
        if r['group'] == 'MB memory':
            allowance = ALLOW['out_pad'] + copper * PS_PER_MM / 1000
        else:
            allowance = (ALLOW['out_pad'] + max(lengths['bus_mm'].values()) * PS_PER_MM / 1000 +
                         CONNECTOR_NS + RC_NS)
        for label, m in r['receivers'].items():
            for e in m.get('edges') or []:
                if not e:
                    continue
                slack = allowance - e['settled_ns']
                key = (r['group'], net)
                if key not in worst or slack < worst[key]['slack_ns']:
                    worst[key] = {'slack_ns': round(slack, 3), 'allowance_ns': round(allowance, 3),
                                  'receiver': label, 'case': r['case']}
                if slack < 0:
                    bad.append(key)
    return {'ok': not bad, 'nets': {f'{g}: {n}': v for (g, n), v in sorted(worst.items())},
            'over_allowance': sorted({f'{g}: {n}' for g, n in bad})}


def clock_skew_check(results):
    """BUS-005 hold: min_data 3.0 + connector 0.1 - (clk_mismatch 1.0 + skew) >= 0."""
    skews = []
    for r in results:
        if r['group'] != 'clocks':
            continue
        arrivals = {}
        for label, m in r['receivers'].items():
            key = 'CLK12' if label.endswith('main:U7.21') else 'CPU_CLK' if 'cpu:U1.21' in label else None
            if key:
                arrivals[key] = [e['settled_ns'] for e in m['edges'] if e and e['edge'] == 'rise']
        if set(arrivals) != {'CLK12', 'CPU_CLK'}:
            return {'ok': False, 'reason': f'clock arrivals missing in {r["case"]}'}
        # the same oscillator edge reaches both FPGAs in one case
        skews += [abs(a - b) for a, b in zip(arrivals['CLK12'], arrivals['CPU_CLK'])]
    if not skews:
        return {'ok': False, 'reason': 'no clock cases'}
    skew = max(skews)
    return {'ok': bool(skew <= 2.1), 'max_skew_ns': round(float(skew), 3), 'limit_ns': 2.1,
            'basis': 'BUS-005 hold: min_data 3.0 + connector 0.1 - clk_mismatch 1.0 >= skew'}


def crosstalk_checks(extracted):
    """Field-solved coupled noise on every extracted net against its budget:
    half the receiver's static low-side margin (VIL 0.8 V -> 0.4 V), or the
    RP2040/iCE40 input hysteresis (0.2 V) on clock nets."""
    items, ok = [], True
    for (kind, net), x in sorted(extracted.items()):
        budget = .2 if any(c in net.upper() for c in CLOCK_NETS) else .4
        good = bool(x['noise_v'] <= budget)
        ok = ok and good
        items.append({'board': kind, 'net': net, 'noise_v': x['noise_v'], 'budget_v': budget,
                      'ok': good, 'aggressors': x['aggressors'],
                      'unreferenced_mm': x['summary'].get('unreferenced_mm'),
                      'z0_range_ohm': x['summary'].get('z0_range_ohm')})
    items.sort(key=lambda i: i['noise_v'] - i['budget_v'], reverse=True)
    bad = [i for i in items if not i['ok']]
    return {'ok': ok, 'nets': items,
            'method': 'field-solved Kb/Kf per coupled piece; t_rise 0.34 ns, 3.6 V swing, '
                      'all aggressors together',
            'summary': (f'{len(bad)} of {len(items)} nets over budget; worst '
                        f'{bad[0]["board"]} {bad[0]["net"]} {bad[0]["noise_v"]} V'
                        if bad else f'{len(items)} nets within budget')}


def row_checks(row, extracted, results):
    timing = timing_checks(row, results)
    if row in ('MB-007', 'CC-007'):
        allowance = bus_allowance_checks(results)
        skew = clock_skew_check(results)
        timing['bus_flight_vs_budget'] = allowance
        timing['clock_skew'] = skew
        timing['ok'] = timing['ok'] and allowance['ok'] and skew['ok']
        if not allowance['ok']:
            timing['summary'] += f'; over BUS-005 flight allowance: {allowance["over_allowance"][:4]}'
        if not skew['ok']:
            timing['summary'] += f'; clock skew {skew}'
    return {'timing': timing, 'crosstalk': crosstalk_checks(extracted)}


# --------------------------------------------------------------- reporting
ROW_BOARDS = {'MB-007': ('main', 'cpu') + CARD_KINDS, 'CC-007': ('main', 'cpu'),
              'SC-007': ('main', 'storage'), 'EC-007': ('main', 'eink')}
# checks the row's catalogue text names that this tool does not simulate
UNCOVERED = {
    'MB-007': ['USB D+/D- 90 ohm +/-10 % differential impedance (a field-solver/openEMS '
               'check, not modelled here)'],
    'CC-007': [], 'SC-007': [], 'EC-007': [],
}


def fixture_report(ice40, lvc):
    out, ok = {}, True
    for name, model in (*ice40.items(), ('lvc125_proxy', lvc['out'])):
        for corner in models.CORNERS:
            for edge in ('rise', 'fall'):
                err = models.fixture_check(model, corner, edge)
                out[f'{name}/{corner}/{edge}'] = err
                ok &= err['ok']
    return ok, out


def summarise(results):
    groups = {}
    for r in results:
        g = groups.setdefault(r['group'], {'cases': 0, 'failing_cases': 0, 'errors': 0,
                                           'worst': {}, 'failures': {}})
        g['cases'] += 1
        if r['failures']:
            g['failing_cases'] += 1
        for f in r['failures']:
            if f.startswith('simulation error'):
                g['errors'] += 1
            key = re.sub(r'[-\d.]+ (V|mV|ns)', '# \\1', f)
            g['failures'].setdefault(key, {'count': 0, 'example': f'{r["case"]}: {f}'})
            g['failures'][key]['count'] += 1
        for label, m in r['receivers'].items():
            w = g['worst']
            for key, value in (('overshoot_margin_v', m.get('overshoot_margin_v')),
                               ('undershoot_margin_v', m.get('undershoot_margin_v')),
                               ('noise_margin_v', m.get('noise_margin_v'))):
                if value is not None and (key not in w or value < w[key]['value']):
                    w[key] = {'value': value, 'receiver': label, 'case': r['case']}
            for e in m.get('edges', []) or []:
                if not e:
                    continue
                for key, value, better in (('ringback_margin_v', e['ringback_margin_v'], min),
                                           ('monotonic_drop_mv', -e['monotonic_drop_mv'], min)):
                    if key not in w or value < w[key]['value']:
                        w[key] = {'value': value, 'receiver': label, 'case': r['case']}
    for g in groups.values():
        g['failures'] = dict(sorted(g['failures'].items(), key=lambda kv: -kv[1]['count'])[:25])
    return groups


XTALK_QUIET = set(RAILS) | {'/+1V2', '/1V2', '/VBUS', '/5V_SYS', '/VBUS_F'}
XTALK_T_RISE, XTALK_SWING = .34e-9, 3.6     # fastest modelled edge, highest rail


def _extract_one(args):
    board_dir, kind, net = args
    bench = Bench(board_dir)
    graph = bench.graph(kind, net)
    noise, worst = route.coupling_bound(graph, kind, XTALK_QUIET, XTALK_T_RISE, XTALK_SWING)
    return kind, net, dict(route._XSEC), route.summary(graph), (noise, worst)


def prepare(bench, cases, board_dir, jobs):
    """Extract every reached net once, in parallel, and cache the field-
    solved cross-sections for the case workers."""
    nets, seen = set(), set()
    for case in cases:
        for drive in case.drives:
            key = (drive.start, case.config.slots)
            if key in seen:
                continue
            seen.add(key)
            asm = Assembler(bench, case.config, 3.3)
            nets |= asm.assemble(drive.start, None, dry=True)
    route.load_xsec_cache()
    print(f'extracting {len(nets)} routed nets', flush=True)
    crosstalk = {}
    with concurrent.futures.ProcessPoolExecutor(max_workers=jobs) as pool:
        for kind, net, xsec, summary, xt in pool.map(
                _extract_one, [(board_dir, k, n) for k, n in sorted(nets)]):
            route._XSEC.update(xsec)
            crosstalk[(kind, net)] = {'summary': summary, 'noise_v': xt[0], 'aggressors': xt[1]}
    route.save_xsec_cache()
    return crosstalk


def _plain(value):
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(f'{type(value).__name__} is not JSON serialisable')


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--row', required=True, choices=sorted(ROWS))
    parser.add_argument('--board-dir', type=Path, default=ROOT / 'build/hw')
    parser.add_argument('--artifacts-only', action='store_true',
                        help='accept builds whose inputs are stale (diagnostic; the row stays red)')
    parser.add_argument('--jobs', type=int, default=max(1, (os.cpu_count() or 2) - 2))
    parser.add_argument('--group', action='append', help='only these case groups (diagnostic)')
    parser.add_argument('--limit', type=int, help='only the first N cases per group (diagnostic)')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    out = args.out or OUT_DIR / f'{args.row}.json'
    receipts, stale = load_evidence(args.board_dir, ROW_BOARDS[args.row], args.artifacts_only)
    ice40 = models.load_ice40()
    lvc = models.load_lvc125(OUT_DIR / 'cache/scem270.zip')
    models.load_tpd(OUT_DIR / 'cache/slvm741a.zip')
    models.load_txb(OUT_DIR / 'cache/scem518.zip')
    fixtures_ok, fixtures = fixture_report(ice40, lvc)
    bench = Bench(args.board_dir)
    cases = build_cases(bench, args.row)
    if args.group:
        cases = [c for c in cases if c.group in args.group]
    if args.limit:
        seen = {}
        cases = [c for c in cases if seen.setdefault(c.group, []).append(c) or
                 len(seen[c.group]) <= args.limit]
    extracted = prepare(bench, cases, args.board_dir, args.jobs)
    print(f'{args.row}: {len(cases)} ngspice cases on {args.jobs} workers', flush=True)
    results = run_cases(cases, args.board_dir, args.jobs,
                        progress=lambda m: print(m, flush=True))
    groups = summarise(results)
    # discretisation check on each group's worst-overshoot case
    by_name = {c.name: c for c in cases}
    checks = []
    for name, g in groups.items():
        worst = g['worst'].get('overshoot_margin_v')
        if worst:
            case = by_name[worst['case']]
            reference = next(r for r in results if r['case'] == case.name)
            checks.append(convergence(case, args.board_dir, reference))
    extra = row_checks(args.row, extracted, results)
    failing = sum(1 for r in results if r['failures'])
    verdict = {
        'evidence_valid': not stale,
        'ibis_fixtures_ok': fixtures_ok,
        'all_cases_pass': failing == 0,
        'converged': all(c['ok'] for c in checks),
        'timing_ok': extra['timing']['ok'],
        'coverage_complete': not UNCOVERED[args.row] and not args.group and not args.limit,
    }
    report = {
        'row': args.row, 'tool': 'hw/si/slowbus_si.py',
        'tool_sha256': {name: sha(HERE / name) for name in
                        ('slowbus_si.py', 'slowbus_models.py', 'slowbus_route.py')},
        'receipts': receipts, 'stale_evidence': stale,
        'models': {'ice40_ibis_sha256': models.ICE40_SHA256,
                   'ti_zip_sha256': {'slvm741a': models.TPD_ZIP_SHA256,
                                     'scem518': models.TXB_ZIP_SHA256,
                                     'scem270': models.LVC125_ZIP_SHA256},
                   'sources': SOURCES, 'fixture_replay': fixtures},
        'assumptions': ASSUMPTIONS,
        'uncovered': UNCOVERED[args.row],
        'verdict': verdict, 'valid_for_row_4_6': all(verdict.values()),
        'advisory': {'crosstalk_screen_ok': extra['crosstalk']['ok'],
                     'note': 'crosstalk is a conservative field-solved screen (no termination '
                             'credit, all aggressors at once); the catalogue checks do not '
                             'name it, so it is reported, not gated'},
        'groups': groups, 'convergence': checks, **extra,
        'cases': results,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=1, default=_plain) + '\n')
    for name, g in groups.items():
        print(f'  {name}: {g["cases"]} cases, {g["failing_cases"]} failing')
        for key, item in list(g['failures'].items())[:4]:
            print(f'      {item["count"]:5d}x {item["example"][:170]}')
    for c in checks:
        print(f'  convergence {c["case"][:60]}: {"ok" if c["ok"] else "FAIL"} '
              f'(dV {c.get("max_delta_v")}, dt {c.get("max_delta_ns")} ns)')
    print(f'  timing: {"ok" if extra["timing"]["ok"] else "FAIL"} - {extra["timing"]["summary"]}')
    print(f'  crosstalk screen (advisory): {"ok" if extra["crosstalk"]["ok"] else "over"} - '
          f'{extra["crosstalk"]["summary"]}')
    for item in UNCOVERED[args.row]:
        print(f'  NOT COVERED: {item}')
    for item in stale:
        print(f'  EVIDENCE: {item}')
    print(f'{args.row}: {"PASS" if report["valid_for_row_4_6"] else "FAIL"} '
          f'({failing}/{len(results)} cases failing) -> {out}')
    return 0 if report['valid_for_row_4_6'] else 1


if __name__ == '__main__':
    sys.exit(main())
