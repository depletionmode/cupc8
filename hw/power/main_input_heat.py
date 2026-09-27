#!/usr/bin/env python3
"""MB-005 routed input copper loss at the eFuse current-limit corner.

Read a content-valid main-board receipt. The track/via extraction omits
positive-net pours and idealizes pads; the 115 C, 80%-width, 24.9/11.4 um
copper, 15 um via wall and 1.76 mm board corner is a sensitivity scenario,
not a fabricated minimum or a solved thermal field. Exit red even if the
scenario improves until ground, connector, fabrication and thermal bounds
are supplied by a later board qualification.
"""

import argparse
import json
from pathlib import Path
import sys

import pcbnew

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/tools'))
sys.path.insert(0, str(ROOT / 'hw'))

import boardevidence
from cosim.netlist import read
import design as d
from main_trial_corner import row
from spice import Checks


INPUT_PINS = {
    ('J1', 'A4B9'): '/VBUS', ('J1', 'B4A9'): '/VBUS',
    ('F1', '1'): '/VBUS', ('F1', '2'): '/VBUS_F',
    ('U2', '5'): '/VBUS_F',
}
COPPER_LIMIT_MOHM = 20.0
CORNER_C = 115.0


def losses(resistance_mohm, current_a):
    """Return modeled voltage drop (mV) and instantaneous I²R heat (mW)."""
    if resistance_mohm < 0 or current_a < 0:
        raise ValueError('nonnegative resistance and current required')
    return current_a * resistance_mohm, current_a ** 2 * resistance_mohm


def inspect(out):
    boardevidence.validate('main', out)
    order = json.loads((out / 'fab/order.json').read_text())
    required = {'layers': 6, 'thickness_mm': 1.6, 'finished_outer_copper_oz': 1,
                'finished_inner_copper_oz': 0.5, 'stackup': 'JLC06161H-3313'}
    for key, value in required.items():
        if order.get(key) != value:
            raise ValueError('input loss model requires %s=%s, got %s' %
                             (key, value, order.get(key)))
    netlist = read(out / 'main.net')
    board = pcbnew.LoadBoard(str(out / 'main.kicad_pcb'))
    for pin, net in INPUT_PINS.items():
        if netlist.net(*pin) != net:
            raise ValueError('%s netlist: expected %s, got %s' % (pin, net, netlist.net(*pin)))
        if (actual := board.FindFootprintByReference(pin[0])) is None:
            raise ValueError('%s: missing PCB footprint' % (pin,))
        contacts = [pad for pad in actual.Pads() if pad.GetNumber() == pin[1]]
        if len(contacts) != 1 or contacts[0].GetNetname() != net:
            raise ValueError('%s: PCB pad/net differs from exported netlist' % (pin,))
    _, _, _, j1_f1, f1_u2 = row(board, CORNER_C, 15)
    return j1_f1, f1_u2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('out', type=Path, help='completed main-board receipt')
    args = parser.parse_args()
    c = Checks('MB-005 main input copper and instantaneous eFuse-limit heating')
    try:
        j1_f1, f1_u2 = inspect(args.out.resolve())
    except (OSError, ValueError) as error:
        c.info('receipt/topology', str(error))
        c.check('I0', 'content-valid routed main board and input pin topology', 0, 1, '>=', '', fmt='%d')
        return c.done()
    positive = j1_f1 + f1_u2
    current = d.insw_ilim()[2]
    drop_mv, heat_mw = losses(positive, current)
    c.info('route', 'J1 VBUS to F1:1 %.3f mOhm; F1:2 to U2:5 %.3f mOhm; positive sum %.3f mOhm' %
           (j1_f1, f1_u2, positive))
    c.info('fault corner', '%.3f A eFuse maximum limit: %.1f mV modeled positive drop, %.0f mW '
           'instantaneous positive copper heat' % (current, drop_mv, heat_mw))
    c.info('thermal requirement', 'to hold a uniform 115 C copper assumption at 40 C ambient, '
           'aggregate heat would require <= %.1f C/W effective rise per watt; '
           'other heat sources and local necks are excluded' % ((CORNER_C - d.AMBIENT_C) / (heat_mw / 1000)))
    c.check('I1', 'positive copper scenario alone within 20 mOhm entire input-loop budget',
            positive, COPPER_LIMIT_MOHM, '<=', 'mOhm')
    c.check('I2', 'fabricated copper/via minima and positive-net pour extraction supplied',
            0, 1, '>=', '', fmt='%d')
    c.check('I3', 'GND, mated VBUS/GND contacts and pad transitions bounded',
            0, 1, '>=', '', fmt='%d')
    c.check('I4', 'fault-duration and board/connector thermal field bounded',
            0, 1, '>=', '', fmt='%d')
    return c.done()


if __name__ == '__main__':
    sys.exit(main())
