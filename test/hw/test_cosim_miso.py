"""Pin-exact MISO network recognition and wiring fault counterexamples."""
import copy
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'hw/cosim'))
from gen_top import card_miso_network
from netlist import Circuit, Resistor


def network(ahc=True, wifi=False):
    ref = 'U3' if wifi else 'U4'
    internal = '/MISO_INT' if wifi else '/MISO_OUT'
    pins = {(ref,'1'):'/CS_n', (ref,'2'):internal, (ref,'3'):'/GND',
            (ref,'4'):'/MISO_SRC' if ahc else '/MISO', (ref,'5'):'/3V3',
            ('J1','B16'):'/MISO', ('R60','1'):'/MISO_SRC', ('R60','2'):'/MISO',
            ('R61','1'):'/MISO', ('R61','2'):'/GND'}
    resistors = (Resistor('R60','270',('/MISO_SRC','/MISO')),
                 Resistor('R61','10k',('/MISO','/GND'))) if ahc else ()
    return Circuit({ref:('SN74AHC1G125DCKR' if ahc else '74LVC1G125GW',None)}, {}, pins, resistors)

class MisoNetwork(unittest.TestCase):
    def test_supported_networks(self):
        for wifi in (False,True):
            card = 'wifi' if wifi else 'gpu'
            self.assertTrue(card_miso_network(network(True,wifi),card))
            self.assertFalse(card_miso_network(network(False,wifi),card))
    def test_faults(self):
        mutations = [
            lambda c:c.pins.__setitem__(('U4','1'),'/GND'),
            lambda c:c.pins.__setitem__(('U4','4'),'/MISO'),
            lambda c:c.pins.__setitem__(('R61','2'),'/+3V3'),
            lambda c:c.components.__setitem__('U4',('unknown125',None)),
            lambda c:setattr(c,'resistors',(Resistor('R60','33',('/MISO_SRC','/MISO')),c.resistors[1])),
            lambda c:setattr(c,'resistors',(c.resistors[0],)),
            lambda c:setattr(c,'resistors',c.resistors+(Resistor('R99','270',('/MISO_SRC','/MISO')),)),
        ]
        for i,mutate in enumerate(mutations):
            with self.subTest(fault=i):
                c=network();mutate(c)
                with self.assertRaises(ValueError):card_miso_network(c,'gpu')

if __name__ == '__main__': unittest.main()
