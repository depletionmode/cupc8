"""Counterexamples for connector contacts in exported KiCad netlists."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "hw/tools"))
import connectorcheck as cc
import kicadgen as kg


def fixture(path, board, changes=None):
    want = cc.expected(board)
    changes = changes or {}
    comps = ["components"]
    nets = {}
    for ref, pins in want.items():
        pin_list = ["pins"] + [["pin", ["num", kg.Q(pin)]] for pin in pins]
        comps.append(["comp", ["ref", kg.Q(ref)], ["units", ["unit", pin_list]]])
        for pin, original in pins.items():
            net = changes.get((ref, pin), original)
            if net is None:
                net = f"unconnected-({ref}-NC-Pad{pin})"
            nets.setdefault(net, []).append(["node", ["ref", kg.Q(ref)], ["pin", kg.Q(pin)]])
    root = ["export", comps, ["nets"] + [["net", ["name", kg.Q(name)]] + nodes
                                       for name, nodes in nets.items()]]
    path.write_text(kg.dump(root))


class ConnectorTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.path = Path(self.scratch.name) / "board.net"

    def test_all_boards_cover_every_contact(self):
        for board in ("main", "cpu", "gpu", "io", "wifi", "storage", "eink", "system"):
            with self.subTest(board=board):
                fixture(self.path, board)
                self.assertEqual(cc.check(board, self.path), sum(map(len, cc.expected(board).values())))

    def test_swapped_main_slot_chip_selects(self):
        fixture(self.path, "main", {("J11", "A14"): "SLOT2_CS_n",
                                    ("J12", "A14"): "SLOT1_CS_n"})
        with self.assertRaisesRegex(ValueError, r"J11.A14: expected SLOT1_CS_n, found SLOT2_CS_n"):
            cc.check("main", self.path)

    def test_missing_cpu_bus_wire(self):
        fixture(self.path, "cpu", {("J1", "B13"): None})
        with self.assertRaisesRegex(ValueError, r"J1.B13: expected CPU_CLK, found NC"):
            cc.check("cpu", self.path)

    def test_reserved_finger_wired(self):
        fixture(self.path, "wifi", {("J1", "A6"): "SCK"})
        with self.assertRaisesRegex(ValueError, r"J1.A6: expected NC, found SCK"):
            cc.check("wifi", self.path)

    def test_external_connector_swapped(self):
        fixture(self.path, "gpu", {("J2", "1"): "HD_D2N", ("J2", "3"): "HD_D2P"})
        with self.assertRaisesRegex(ValueError, r"J2.1: expected HD_D2P, found HD_D2N"):
            cc.check("gpu", self.path)


if __name__ == "__main__":
    unittest.main()
