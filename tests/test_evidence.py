import copy
import json
import tempfile
import unittest
from pathlib import Path
from model.evidence import attach_evidence, compact_snapshot, retain_snapshots

ROOT = Path(__file__).resolve().parents[1]


class EvidenceTests(unittest.TestCase):
    def make_product(self):
        roster = json.loads((ROOT/'data/registration-roster-2026.json').read_text(encoding='utf-8'))
        return {'generated_at': '2026-09-09T06:00:00+00:00', 'fingerprint': 'test',
                'model_version': 'test', 'poll_audit': [],
                'counties': [{'name': r['county'], 'race_id': r['race_id'], 'quality': {},
                    'candidates': [{**c, 'mean': 100/len(r['candidates']), 'probability': 1/len(r['candidates'])}
                                   for c in r['candidates']]} for r in roster['races']]}

    def test_evidence_does_not_modify_votes_or_party(self):
        product = self.make_product()
        before = copy.deepcopy([r['candidates'] for r in product['counties']])
        attach_evidence(product, {'records': []}, ROOT)
        self.assertEqual(before, [r['candidates'] for r in product['counties']])
        risks = {r['name'] for r in product['counties'] if r['quality']['evidence']['grade'] == 'D'}
        self.assertEqual(risks, {'新竹市', '嘉義縣', '嘉義市'})

    def test_distinguishes_reports_questions_and_eligible_dates(self):
        product = self.make_product()
        records = [{'id': 'p1', 'county': '台北市', 'source': 'a', 'pollster_id': 'same', 'source_url': 'https://a.example/report', 'date': '2026-09-01'},
                   {'id': 'p2', 'county': '台北市', 'source': 'b', 'pollster_id': 'same', 'source_url': 'https://a.example/report', 'date': '2026-09-02'},
                   {'id': 'p3', 'county': '台北市', 'source': 'a', 'source_url': 'https://b.example/report', 'date': '2026-09-08'}]
        product['poll_audit'] = [{'id': p['id'], 'included': i<2, 'reason': '' if i<2 else '民調人選與登記名單不符'} for i,p in enumerate(records)]
        attach_evidence(product, {'records': records}, ROOT)
        self.assertEqual(product['poll_counts'], {'reports': 2, 'questions': 3, 'included_questions': 2,
                         'covered_counties': 1, 'roster_exclusions': 1, 'latest_eligible_fieldwork': '2026-09-02'})
        self.assertEqual(next(r for r in product['counties'] if r['name']=='台北市')['quality']['evidence']['grade'], 'B')
        records[1]['pollster_id']='independent'
        attach_evidence(product, {'records': records}, ROOT)
        self.assertEqual(next(r for r in product['counties'] if r['name']=='台北市')['quality']['evidence']['grade'], 'A')

    def test_no_future_evidence(self):
        product=self.make_product()
        product['generated_at']='2026-09-08T00:00:00+00:00'
        attach_evidence(product, {'records': []}, ROOT)
        self.assertEqual(product['evidence']['events'], [])

    def test_compact_and_deduplicate_by_taipei_day_and_version(self):
        first=compact_snapshot(self.make_product())
        second={**first, 'generated_at': '2026-09-09T07:00:00+00:00', 'fingerprint': 'later'}
        version={**second, 'model_version': 'new'}
        self.assertEqual(retain_snapshots([second, first, version]), [second, version])
        self.assertNotIn('draws', first['counties'][0])
        nextday={**second, 'generated_at': '2026-09-09T16:01:00+00:00'}
        self.assertEqual(len(retain_snapshots([first,nextday])),2)

    def test_invalid_or_mismatched_sources_fail_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'data').mkdir()
            context=json.loads((ROOT/'data/candidate-context.json').read_text(encoding='utf-8'))
            for field,value in [('source_url','javascript:alert(1)'),('candidate','unknown')]:
                bad=copy.deepcopy(context);bad['events'][0][field]=value
                (root/'data/candidate-context.json').write_text(json.dumps(bad),encoding='utf-8')
                with self.assertRaises(ValueError):attach_evidence(self.make_product(),{'records':[]},root)
