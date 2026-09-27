"""Content and salt checks for a completed Freerouting session."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'hw' / 'tools'))
import sesreplay


class SessionValidationTests(unittest.TestCase):
    def check(self, body, salt=3):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'route.ses'
            path.write_text(body)
            sesreplay._check_session(path, salt)

    def test_quoted_freerouting_header(self):
        self.check('(session "route-3"\n  (base_design "route-3")\n  (placement))\n')

    def test_unquoted_header(self):
        self.check('(session route-3 (base_design route-3) (placement))')

    def test_wrong_salt_and_truncation_fail(self):
        body = '(session "route-3" (base_design "route-3") (placement))'
        with self.assertRaisesRegex(ValueError, 'salt'):
            self.check(body, salt=9)
        with self.assertRaisesRegex(ValueError, 'incomplete'):
            self.check(body[:-1])

    def test_preroute_fingerprint_ignores_only_worktree_noise(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = (Path(tmp) / name for name in ('a.kicad_pcb', 'b.kicad_pcb'))
            first = '(footprint "U1" (uuid "00000000-0000-0000-0000-000000000001") (at 10 20) (model "/one/hw/lib/chip.wrl"))'
            second = '(net 1 "/GND")'
            a.write_text('(kicad_pcb\n' + first + '\n' + second + '\n)')
            b.write_text('(kicad_pcb\n' + second + '\n' + first.replace('000000000001', '000000000002').replace('/one/', '/two/') + '\n)')
            self.assertEqual(sesreplay.preroute_digest(a), sesreplay.preroute_digest(b))
            b.write_text(b.read_text().replace('(at 10 20)', '(at 11 20)'))
            self.assertNotEqual(sesreplay.preroute_digest(a), sesreplay.preroute_digest(b))


if __name__ == '__main__':
    unittest.main()
