#!/usr/bin/env python3
"""Check CPU schematic outputs through their physical 33-ohm pack channels.

This checks generated KiCad connectivity. It is a prerequisite to CC-051,
not a substitute for BUS-001..003 running through a schematic-derived model.
"""
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/boards'))
sys.path.insert(0, str(ROOT / 'hw/tools'))
from netlist import read
import cpu
import kicadgen


def check(circuit):
    checked = 0
    for pin, (signal, direction) in cpu.PINS.items():
        if signal not in cpu.DRIVEN:
            continue
        socket_nodes = [node for node in circuit.nets.get('/' + signal, ()) if node[0] == 'J1']
        if len(socket_nodes) != 1:
            raise ValueError(f'{signal}: expected one CPU edge finger, got {socket_nodes}')
        fpga = ('U1', str(pin))
        resistor = circuit.series(fpga, socket_nodes[0])
        if resistor is None or resistor.value != '33':
            raise ValueError(f'{signal}: FPGA pin {pin} to {socket_nodes[0]} lacks a 33-ohm series resistor')
        if circuit.direct(fpga, socket_nodes[0]):
            raise ValueError(f'{signal}: series resistor was bypassed')
        checked += 1
    if checked != len(cpu.DRIVEN):
        raise ValueError(f'checked {checked} of {len(cpu.DRIVEN)} driven signals')
    return checked


def main():
    with tempfile.TemporaryDirectory(prefix='cupc8-cpu-netlist-') as directory:
        schematic = Path(directory) / 'cpu.kicad_sch'
        netlist = Path(directory) / 'cpu.net'
        cpu.schematic(str(schematic), ())
        kicadgen.export_netlist(str(schematic), str(netlist))
        count = check(read(netlist))
    print(f'CPU schematic: {count} driven FPGA signals pass through 33-ohm pack channels to the edge')


if __name__ == '__main__':
    main()
