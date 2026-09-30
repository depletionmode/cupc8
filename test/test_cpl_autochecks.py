"""CPL pack automatic checks (tools/cpl_autochecks.py): polarity from pin
names, pin-name matching, pad-for-pad geometry, numbering direction. No board
build needed."""
import os
import sys
import tempfile
import unittest

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))
import cpl_autochecks as auto  # noqa: E402
import cpl_codex  # noqa: E402


def easyeda(lcsc):
    with open(os.path.join(ROOT, 'hw', 'parts', 'easyeda', lcsc + '.yaml')) as handle:
        return yaml.safe_load(handle)


def polarity_of(lcsc, kicad_k_left=True, rotation=0.0):
    """Our LED footprint (K pad 1 on the left, A pad 2 on the right, as
    KiCad's LED_0603) against the EasyEDA record of `lcsc` placed at the origin."""
    record = easyeda(lcsc)
    ours = {'1': (-0.75, 0.0), '2': (0.75, 0.0)} if kicad_k_left else {'1': (0.75, 0.0), '2': (-0.75, 0.0)}
    theirs = auto.jlc_world([(str(n), x, y) for n, x, y in record['pads']], rotation, 0.0, 0.0)
    return auto.polarity(ours, {'1': 'K', '2': 'A'}, theirs, {str(k): str(v) for k, v in record['pins'].items()})


class PolarityTests(unittest.TestCase):
    def test_wifi_d1_and_d2_d4_both_have_k_on_the_left(self):
        # C2286: pin1 = A at +0.75, pin2 = K at -0.75; C12624: pin1 = K at -0.75
        for lcsc in ('C2286', 'C12624'):
            result = polarity_of(lcsc)
            self.assertEqual(result['status'], 'pass', (lcsc, result['detail']))
            self.assertIn('cathode: KiCad pad 1 (K) on the left', result['detail'])
        self.assertIn('JLC pad 2 (K) on the left', polarity_of('C2286')['detail'])
        self.assertIn('JLC pad 1 (K) on the left', polarity_of('C12624')['detail'])

    def test_k_on_the_wrong_side_fails(self):
        for lcsc in ('C2286', 'C12624'):
            self.assertEqual(polarity_of(lcsc, kicad_k_left=False)['status'], 'fail')

    def test_a_180_degree_cpl_turn_flips_the_verdict(self):
        self.assertEqual(polarity_of('C2286', rotation=180.0)['status'], 'fail')

    def test_no_pin_names_is_unknown_not_pass(self):
        ours = {'1': (-0.75, 0.0), '2': (0.75, 0.0)}
        result = auto.polarity(ours, {'1': 'K', '2': 'A'}, ours, {'1': '1', '2': '2'})
        self.assertEqual(result['status'], 'unknown')


class NameTests(unittest.TestCase):
    def test_same_function_spelled_differently(self):
        self.assertEqual(auto.name_relation('~{CS}', '/CS', '1'), 'match')
        self.assertEqual(auto.name_relation('~{WP}/IO_{2}', 'IO2', '3'), 'match')
        self.assertEqual(auto.name_relation('~{HOLD}/~{RESET}/IO_{3}', 'HOLD#orRESET#(IO3)', '7'), 'match')
        self.assertEqual(auto.name_relation('SWDIO', 'SWD', '25'), 'alias')
        self.assertEqual(auto.name_relation('ENABLE', 'EN', '3'), 'alias')
        self.assertEqual(auto.name_relation('EN', 'ENABLE', '3'), 'alias')

    def test_different_function_is_a_mismatch(self):
        self.assertEqual(auto.name_relation('IOL_2A', 'IOL_1A', '1'), 'mismatch')
        self.assertEqual(auto.name_relation('GND', 'VCC', '2'), 'mismatch')
        self.assertEqual(auto.name_relation('ENABLE', 'IN', '3'), 'mismatch')

    def test_pad_numbers_as_names_are_not_comparable(self):
        self.assertEqual(auto.name_relation('I/O1', '1', '1'), 'generic')
        self.assertEqual(auto.pin_names({'1': 'A', '2': 'GND'}, {'1': 'A', '2': 'VCC'})['status'], 'fail')


class GeometryTests(unittest.TestCase):
    def test_deviation_reported_and_limit_enforced(self):
        ours = {'1': (0.0, 0.0), '2': (1.0, 0.0)}
        result, worst = auto.geometry(ours, {'1': (0.0, 0.0), '2': (1.1, 0.0)})
        self.assertEqual(result['status'], 'pass')
        self.assertAlmostEqual(worst, 0.1)
        result, _ = auto.geometry(ours, {'1': (0.0, 0.0), '2': (1.3, 0.0)})
        self.assertEqual(result['status'], 'fail')

    def test_shared_pad_numbers_pair_with_the_nearest(self):
        ours = {'20': (0.0, 0.0), '20#2': (10.0, 0.0)}
        theirs = {'20': (10.0, 0.05), '20#2': (0.0, 0.05)}
        self.assertEqual(auto.geometry(ours, theirs)[0]['status'], 'pass')


class NumberingTests(unittest.TestCase):
    SOT23_5 = {'1': (-1.0, 0.95), '2': (0.0, 0.95), '3': (1.0, 0.95), '4': (1.0, -0.95), '5': (-1.0, -0.95)}

    def test_direction_seen_from_the_top(self):
        # y down: pins 1-3 along the bottom left to right, 4-5 back along the top = counterclockwise
        self.assertEqual(auto.numbering_direction(self.SOT23_5), 'ccw')
        mirrored = {n: (-x, y) for n, (x, y) in self.SOT23_5.items()}
        self.assertEqual(auto.numbering_direction(mirrored), 'cw')

    def test_datasheet_leg_fails_on_mirrored_footprint(self):
        record = {'numbering': 'ccw', 'pins': {1: 'A', 2: 'B', 3: 'C', 4: 'D', 5: 'E'}, 'seen': 'test'}
        names = {'1': 'A', '2': 'B', '3': 'C', '4': 'D', '5': 'E'}
        self.assertEqual(auto.datasheet_check(record, self.SOT23_5, names)['status'], 'pass')
        mirrored = {n: (-x, y) for n, (x, y) in self.SOT23_5.items()}
        self.assertEqual(auto.datasheet_check(record, mirrored, names)['status'], 'fail')
        names['3'] = 'Z'
        self.assertEqual(auto.datasheet_check(record, self.SOT23_5, names)['status'], 'fail')

    def test_could_not_determine_is_never_a_pass(self):
        self.assertEqual(auto.datasheet_check({'result': 'could not determine', 'why': 'x'}, {}, {})['status'], 'unknown')
        self.assertEqual(auto.datasheet_check(None, {}, {})['status'], 'unknown')


class CodexClassificationTests(unittest.TestCase):
    def test_parse_verdict_look_at_and_sources(self):
        got = cpl_codex.parse_answer('VERDICT: check\nLOOK AT: the cathode end in the preview\nReasoning [JLC](https://jlcpcb.com/help/x).')
        self.assertEqual(got['verdict'], 'check')
        self.assertEqual(got['look_at'], 'the cathode end in the preview')
        self.assertEqual(got['sources'], ['https://jlcpcb.com/help/x'])
        self.assertEqual(cpl_codex.parse_answer('**VERDICT: Problem**\nLOOK AT: x')['verdict'], 'problem')

    def test_no_verdict_line_or_empty_is_unanswered(self):
        self.assertEqual(cpl_codex.parse_answer('It looks okay to me.')['verdict'], 'unanswered')
        self.assertEqual(cpl_codex.parse_answer('')['verdict'], 'unanswered')

    def test_fine_and_check_verify_only_parts_the_tool_left_open(self):
        for verdict in ('fine', 'check'):
            self.assertEqual(cpl_codex.classify('human', {'verdict': verdict}), 'codex-verified')

    def test_problem_unanswered_or_missing_stay_with_the_human(self):
        for codex in ({'verdict': 'problem'}, {'verdict': 'unanswered'}, None):
            self.assertEqual(cpl_codex.classify('human', codex), 'human')

    def test_codex_never_overrules_a_tool_mismatch_or_touches_tool_verified(self):
        self.assertEqual(cpl_codex.classify('bad', {'verdict': 'fine'}), 'bad')
        self.assertEqual(cpl_codex.classify('verified', {'verdict': 'problem'}), 'verified')

    def test_types_are_per_lcsc_footprint_correction_not_per_designator(self):
        facts = {'fpid': 'fp', 'correction': 0}
        autos = {'a': {'D1': {'lcsc': 'C1', 'auto': 'human', 'facts': facts}, 'D2': {'lcsc': 'C1', 'auto': 'human', 'facts': facts},
                       'D3': {'lcsc': 'C1', 'auto': 'verified', 'facts': facts}}}
        types = cpl_codex.open_types(autos)
        self.assertEqual(list(types), ['C1|fp|0'])
        self.assertEqual(len(types['C1|fp|0']['parts']), 2)


class ResolutionTests(unittest.TestCase):
    RES = {'verdict': 'fine', 'justification': 'because', 'by': 'David', 'date': '2026-09-29'}

    def load(self, text):
        with tempfile.NamedTemporaryFile('w', suffix='.yaml') as handle:
            handle.write(text)
            handle.flush()
            return cpl_codex.load_resolutions(handle.name)

    def test_an_entry_resolves_even_a_tool_mismatch_and_a_codex_problem(self):
        for tool in ('human', 'bad', 'verified'):
            self.assertEqual(cpl_codex.classify(tool, {'verdict': 'problem'}, self.RES), 'resolved')

    def test_without_an_entry_nothing_becomes_resolved(self):
        for tool in ('human', 'bad', 'verified'):
            for codex in (None, {'verdict': 'fine'}, {'verdict': 'problem'}):
                self.assertNotEqual(cpl_codex.classify(tool, codex, None), 'resolved')
        self.assertEqual(cpl_codex.classify('bad', {'verdict': 'fine'}, None), 'bad')

    def test_empty_or_missing_justification_is_rejected(self):
        for body in ("justification: ''", 'justification: "   "', ''):
            with self.assertRaises(ValueError):
                self.load('main/J4:\n  verdict: fine\n  by: D\n  date: x\n  ' + body + '\n')

    def test_other_verdict_or_bad_key_is_rejected(self):
        with self.assertRaises(ValueError):
            self.load('main/J4: {verdict: check, justification: x, by: D, date: x}\n')
        with self.assertRaises(ValueError):
            self.load('J4: {verdict: fine, justification: x, by: D, date: x}\n')

    def test_the_shipped_file_carries_only_authorized_resolutions(self):
        got = cpl_codex.load_resolutions(os.path.join(ROOT, 'tools', 'cpl_resolutions.yaml'))
        self.assertEqual(set(got), {'main/J4', 'cpu/U1', 'main/U7'})
        self.assertTrue(got['main/J4']['justification'].startswith('J4 is a plain, unkeyed vertical pin header'))
        self.assertTrue(got['main/J4']['justification'].endswith('the part is marked interchangeable_pins.'))
        for key in ('cpu/U1', 'main/U7'):
            resolution = got[key]
            self.assertEqual(resolution['verdict'], 'fine')
            self.assertEqual(str(resolution['date']), '2026-09-29')
            self.assertTrue(resolution['by'].startswith('David Kaplan (instruction in Claude session'))
            self.assertIn('all 144 pin functions', resolution['justification'])
            self.assertIn('Still to confirm in JLC', resolution['justification'])


if __name__ == '__main__':
    unittest.main()
