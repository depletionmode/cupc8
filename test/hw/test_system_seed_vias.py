#!/usr/bin/env python3
"""Regression for historical System seed vias replacing corrected fanout."""
from pathlib import Path
import sys,unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'hw/tools'));sys.path.insert(0,str(ROOT/'hw/boards'))
import pcbnew,kicadgen as kg,route_seed,system


def fixture():
    board=pcbnew.BOARD();board.SetCopperLayerCount(4)
    gnd=pcbnew.NETINFO_ITEM(board,'/GND');signal=pcbnew.NETINFO_ITEM(board,'/USB_DP');board.Add(gnd);board.Add(signal)
    footprints={}
    pads=[('U2','4',(8912500,14905000),(1625000,650000),(8029296,15373990)),
          ('Y1','2',(20100000,25850000),(1400000,1200000),(20891285,26461447)),
          ('Y1','4',(17900000,24150000),(1400000,1200000),(17108714,23538552))]
    for ref,pin,position,size,via_position in pads:
        if ref not in footprints:
            fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);board.Add(fp);footprints[ref]=fp
        fp=footprints[ref];pad=pcbnew.PAD(fp);pad.SetNumber(pin);pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu);layers.AddLayer(pcbnew.F_Mask);pad.SetLayerSet(layers)
        pad.SetSize(pcbnew.VECTOR2I(*size));fp.Add(pad);pad.SetPosition(pcbnew.VECTOR2I(*position));pad.SetNet(gnd)
        track=pcbnew.PCB_TRACK(board);track.SetLayer(pcbnew.F_Cu);track.SetWidth(300000);track.SetStart(pad.GetPosition());track.SetEnd(pcbnew.VECTOR2I(*via_position));track.SetNet(gnd);board.Add(track)
        via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I(*via_position));via.SetWidth(600000);via.SetDrill(300000);via.SetNet(gnd);board.Add(via)
    track=pcbnew.PCB_TRACK(board);track.SetLayer(pcbnew.In2_Cu);track.SetWidth(200000);track.SetStart(pcbnew.VECTOR2I(30000000,30000000));track.SetEnd(pcbnew.VECTOR2I(35000000,35000000));track.SetNet(signal);board.Add(track)
    return board


class SystemVias(unittest.TestCase):
    def test_old_seed_has_pad_holes_and_repair_preserves_all_usb_copper(self):
        board=fixture();before=kg.vias_in_pad_openings(board)
        self.assertEqual({s.split(' via')[0] for s in before},{'U2.4','Y1.2','Y1.4'})
        signals=[r for r in route_seed.copper(board) if r[1]!='/GND']
        system._repair_seed_ground_vias(board)
        self.assertEqual(kg.vias_in_pad_openings(board),[])
        self.assertEqual([r for r in route_seed.copper(board) if r[1]!='/GND'],signals)
    def test_changed_old_drill_does_not_silently_migrate(self):
        board=fixture();via=next(t for t in route_seed.items(board) if t.GetClass()=='PCB_VIA');via.SetDrill(250000)
        with self.assertRaisesRegex(ValueError,'width/drill/layer changed'):system._repair_seed_ground_vias(board)
    def test_reapplying_physical_move_is_rejected(self):
        board=fixture();system._repair_seed_ground_vias(board)
        with self.assertRaisesRegex(ValueError,'historical copper changed'):system._repair_seed_ground_vias(board)

if __name__=='__main__':unittest.main()
