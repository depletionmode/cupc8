"""kicadgen's Freerouting command line: the fan-out switch reaches it."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'hw/tools'))
import kicadgen as kg


class FreeroutingCommand(unittest.TestCase):
    def test_default_keeps_the_fanout_stage(self):
        cmd = kg._freerouting_cmd('a.dsn', 'a.ses', 30)
        self.assertEqual(cmd[:7], ['freerouting', '-de', 'a.dsn', '-do', 'a.ses', '-mp', '30'])
        self.assertIn('-mt', cmd)
        self.assertNotIn('--router.fanout.enabled=false', cmd)

    def test_fanout_false_switches_it_off(self):
        self.assertIn('--router.fanout.enabled=false', kg._freerouting_cmd('a.dsn', 'a.ses', 30, fanout=False))

    def test_main_board_turns_it_off_and_others_do_not(self):
        import inspect
        sys.path.insert(0, str(ROOT / 'hw/boards'))
        self.assertIn('route_fanout=False', (ROOT / 'hw/boards/main.py').read_text())
        for other in ('cpu', 'gpu', 'io', 'system', 'storage', 'eink', 'wifi'):
            self.assertNotIn('route_fanout', (ROOT / 'hw/boards' / (other + '.py')).read_text())
        self.assertTrue(inspect.signature(kg.pipeline).parameters['route_fanout'].default)

    def test_the_flag_reaches_both_route_paths(self):
        import inspect
        for fn in (kg.autoroute, kg._route_parallel):
            self.assertIn('fanout', inspect.signature(fn).parameters)
        src = inspect.getsource(kg)
        self.assertEqual(src.count('_freerouting_cmd('), 3)      # its definition + the two runs


if __name__ == '__main__':
    unittest.main()
