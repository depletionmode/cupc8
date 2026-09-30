#!/usr/bin/env python3
"""Physical pad-launch mutations must open off-centre fanout without a halo."""
import tempfile
import unittest
from pathlib import Path

import pcbnew
from cosim_mutate import open_pad, parse, dump, find1


class PadLaunchTest(unittest.TestCase):
    def test_off_centre_contact_layer_net_and_no_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.kicad_pcb'
            target = Path(directory) / 'opened.kicad_pcb'
            board = pcbnew.BOARD()
            signals = []
            for code, name in enumerate(('/SIGNAL', '/OTHER'), 1):
                net = pcbnew.NETINFO_ITEM(board, name, code)
                board.Add(net)
                signals.append(net)
            footprint = pcbnew.FOOTPRINT(board)
            footprint.SetReference('U1')
            board.Add(footprint)
            pad = pcbnew.PAD(footprint)
            pad.SetNumber('9')
            pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(.875), pcbnew.FromMM(.2)))
            pad.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(20), pcbnew.FromMM(20)))
            layers = pcbnew.LSET()
            layers.AddLayer(pcbnew.F_Cu)
            pad.SetLayerSet(layers)
            pad.SetNet(signals[0])
            footprint.Add(pad)
            other_pad = pcbnew.PAD(footprint)
            other_pad.SetNumber('10')
            other_pad.SetSize(pcbnew.VECTOR2I(pcbnew.FromMM(1), pcbnew.FromMM(1)))
            other_pad.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(40), pcbnew.FromMM(40)))
            other_pad.SetNet(signals[1])
            footprint.Add(other_pad)
            def track(start, end, net=0, layer=pcbnew.F_Cu):
                item = pcbnew.PCB_TRACK(board)
                item.SetStart(pcbnew.VECTOR2I(*(pcbnew.FromMM(v) for v in start)))
                item.SetEnd(pcbnew.VECTOR2I(*(pcbnew.FromMM(v) for v in end)))
                item.SetWidth(pcbnew.FromMM(.1))
                item.SetLayer(layer)
                board.Add(item)
                item.SetNet(signals[net])
                return item.m_Uuid.AsString()
            track((20, 20), (19.94, 19.94))  # Centre stub.
            track((19.94, 19.94), (18, 19.94))  # Still inside the actual pad.
            track((19.94, 19.94), (18, 19.94), layer=pcbnew.B_Cu)
            wrong_net_uuid = track((19.94, 19.94), (18, 19.94), net=1)
            track((20, 20.12), (18, 20.12))  # Stroke touches despite outside endpoint.
            track((19, 20), (21, 20))  # Crosses pad with both endpoints outside.
            track((20, 20.2), (18, 20.2))  # Outside pad: no arbitrary halo.
            pcbnew.SaveBoard(str(source), board)
            # SaveBoard's connectivity update reassigns physically overlapping
            # synthetic tracks. Preserve the explicitly wrong net annotation to
            # test that the mutator never removes another net's copper.
            tree = parse(source.read_text())
            wrong = next(item for item in tree[1:] if isinstance(item, list)
                         and item and item[0] == 'segment'
                         and find1(item, 'uuid')[1] == wrong_net_uuid)
            find1(wrong, 'net')[1] = '/OTHER'
            source.write_text(dump(tree) + '\n')
            self.assertEqual(open_pad(source, target, 'U1', '9', '/SIGNAL'), 4)
            opened = pcbnew.LoadBoard(str(target))
            self.assertEqual(len(opened.Tracks()), 3)
            with self.assertRaisesRegex(AssertionError, 'no launch track'):
                open_pad(target, Path(directory) / 'again.kicad_pcb', 'U1', '9', '/SIGNAL')


if __name__ == '__main__':
    unittest.main()
