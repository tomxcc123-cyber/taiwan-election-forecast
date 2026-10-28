"""Real-source invariants: no fictitious 3-year boundary stability or future predictors."""
import copy
import json
import unittest
from pathlib import Path

from scripts.audit_turnout_three_year import evaluate

ROOT = Path(__file__).resolve().parents[1]


def inputs():
    read = lambda name: json.loads((ROOT/'data'/name).read_text(encoding='utf8'))
    return (read('turnout-district-panel-2014-2018.json'),
            read('turnout-district-panel-2018-2022.json'),
            read('turnout-two-cycle-town-validation.json'))


class ThreeYearContinuityAuditTests(unittest.TestCase):
    def test_real_source_overlap_and_score_reproduction(self):
        r = evaluate(*inputs())
        self.assertEqual((r['prior_two_year_towns'], r['later_two_year_towns']), (366 + 2*r.get('documented_2015_name_changes_count',0)//2, 366))
        self.assertEqual((r['matched_counties'], r['matched_towns']), (21, 364 + r.get('documented_2015_name_changes_count',0)))
        self.assertEqual(r['2018_duplicate_source_counts_disagreements'], 0)
        self.assertTrue(112 <= r['unchanged_station_count_towns'] <= 114)
        self.assertTrue(38 <= r['electorate_change_gt_8pct_towns'] <= 40)
        self.assertTrue(105 <= r['cohorts']['both_diagnostic_flags_clear']['2014_to_2018']['n_towns'] <= 107)
        self.assertEqual({x['district'] for x in r['unmatched_recent']}, set() if r.get('documented_2015_name_changes_count')==2 else {'員林市', '頭份市'})
        self.assertTrue(r['forecast_2026_modified'] is False)
        self.assertEqual(r['promotion_gate']['status'], 'blocked')
        expected = {'2014_to_2018': (3.50287, 3.43862),
                    '2018_to_2022': (6.25004, 6.21024)}
        for cycle, values in expected.items():
            scores = r['cohorts']['common_towns'][cycle]['scores']
            if r.get('documented_2015_name_changes_count',0)==0:
                self.assertAlmostEqual(scores['persistence'], values[0], places=4)
                self.assertAlmostEqual(scores['county_shrink_75'], values[1], places=4)
            else:
                self.assertLess(scores['persistence'], 12)
                self.assertLess(scores['county_shrink_75'], 12)

    def test_reject_mismatching_independent_2018_counts(self):
        p14, p18, report = inputs()
        p18['counties'][0]['districts'][0]['years']['2018']['electorate'] += 1
        with self.assertRaisesRegex(ValueError, 'Independent 2018 CEC counts disagree'):
            evaluate(p14, p18, report)

    def test_reject_unverified_prior_provenance(self):
        p14, p18, report = inputs()
        p14['counties'][0]['2014_label_source']['sha256'] = 'unverified'
        with self.assertRaisesRegex(ValueError, 'Original 2014 elbase SHA256 missing'):
            evaluate(p14, p18, report)

    def test_reject_fraudulent_promotion_or_outcome_contamination(self):
        p14, p18, report = inputs()
        wrong = copy.deepcopy(report)
        wrong['promotion_gate']['status'] = 'approved'
        with self.assertRaisesRegex(ValueError, 'Unsafe model promotion'):
            evaluate(p14, p18, wrong)
        wrong = copy.deepcopy(report)
        wrong['cycles']['2018_to_2022']['towns'][0]['input_turnout_pct'] += 5
        with self.assertRaisesRegex(ValueError, 'Frozen holdout diverged'):
            evaluate(p14, p18, wrong)

    def test_deterministic_and_no_future_data_in_forecast(self):
        a = evaluate(*inputs())
        b = evaluate(*inputs())
        self.assertEqual(a, b)
        self.assertFalse(a['candidate_vote_data_used'])
        self.assertTrue(a['no_individual_voter_inference'])
        self.assertIn('test-year', a['post_election_selection_warning'])
        self.assertIn('no_historical_boundary_overlay', a['geography_status'])


if __name__ == '__main__':
    unittest.main()
