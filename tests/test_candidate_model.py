import copy
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from model.data import audit_dataset, audit_race, digest, load_dataset, previous_race
from model.fundamentals import features, fit, residual_scale, softmax, target_clr, utilities
from model.pipeline import run
from model.roster import convert_rows, load_roster
from model.simulation import condition_on_winner, simulate, summarize
from model.validation import evaluate

ROOT = Path(__file__).resolve().parents[1]


class CandidateModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = load_dataset(ROOT / 'data/candidate-history.json')
        cls.history = cls.data['races']
        cls.roster = load_roster(ROOT / 'data/registration-roster-2026.json', cls.data)
        good = [r for r in cls.history if audit_race(r)['research_eligible'] and previous_race(cls.history, r)]
        cls.train = [r for r in good if r['year'] == 2018]
        cls.test = [r for r in good if r['year'] == 2022]
        cls.fitted = fit(cls.train, cls.history)
        cls.sd = residual_scale(cls.train, cls.history)
        cls.sim = simulate(cls.fitted, cls.test, cls.history, cls.train, cls.sd,
                           draws=400, bootstrap_count=10)

    def test_audit_real_data(self):
        a = audit_dataset(self.data)
        self.assertEqual((a['race_count'], a['candidate_count'], a['research_eligible_count']), (66, 245, 54))
        tainan = next(r for r in a['races'] if r['county'] == '台南市' and r['year'] == 2018)
        self.assertIn('mass_outside_rounding_bound', tainan['errors'])
        self.assertEqual(a['verified_rosters'], 0)

    def test_tampered_dataset_rejected(self):
        changed = copy.deepcopy(self.data)
        changed['races'][0]['candidates'][0]['share_pct'] = 99
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'data.json'
            p.write_text(json.dumps(changed), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'hash'):
                load_dataset(p)

    def test_invalid_shares_and_duplicates(self):
        r = copy.deepcopy(self.test[0])
        r['candidates'][0]['share_pct'] = float('nan')
        self.assertIn('invalid_shares', audit_race(r)['errors'])
        r = copy.deepcopy(self.test[0])
        r['candidates'].append(copy.deepcopy(r['candidates'][0]))
        self.assertIn('duplicate_candidate', audit_race(r)['errors'])

    def test_no_future_labels_or_features(self):
        altered = copy.deepcopy(self.history)
        for r in altered:
            if r['year'] >= 2022:
                for c in r['candidates']:
                    c['share_pct'] = 0
                    c['winner'] = False
        self.assertEqual(fit(self.train, altered), self.fitted)
        for r in self.test:
            np.testing.assert_array_equal(features(r, altered), features(r, self.history))
        with self.assertRaisesRegex(ValueError, 'strictly later'):
            utilities(fit(self.test, self.history), self.test[0], self.history)

    def test_fits_learn_from_labels(self):
        changed = copy.deepcopy(self.train)
        for r in changed:
            vals = [c['share_pct'] for c in r['candidates']][::-1]
            for c, v in zip(r['candidates'], vals):
                c['share_pct'] = v
        self.assertFalse(np.allclose(fit(changed, self.history)['coefficients'], self.fitted['coefficients']))

    def test_reference_and_candidate_order_invariance(self):
        r = self.test[0]
        p = softmax(utilities(self.fitted, r, self.history))
        shifted = utilities(self.fitted, r, self.history) + 100
        np.testing.assert_allclose(p, softmax(shifted))
        reverse = {**r, 'candidates': list(reversed(r['candidates']))}
        np.testing.assert_allclose(p, softmax(utilities(self.fitted, reverse, self.history))[::-1])
        sim = simulate(self.fitted, [{**t, 'candidates': t['candidates'][::-1]} for t in self.test],
                       self.history, self.train, self.sd, draws=400, bootstrap_count=10)
        for key in self.sim['shares']:
            np.testing.assert_array_equal(sim['shares'][key], self.sim['shares'][key])

    def test_rounded_zero_is_finite_not_missing_candidate(self):
        r = copy.deepcopy(self.test[0])
        r['candidates'][0]['share_pct'] = 0
        self.assertTrue(np.isfinite(target_clr(r)).all())
        self.assertEqual(len(target_clr(r)), len(r['candidates']))

    def test_draw_and_seat_conservation(self):
        summary = summarize(self.sim)
        for race in summary['county_forecasts']:
            self.assertAlmostEqual(sum(c['share_mean'] for c in race['candidates']), 1)
            self.assertAlmostEqual(sum(c['win_probability'] for c in race['candidates']), 1)
            for c in race['candidates']:
                self.assertLessEqual(c['p05'], c['p95'])
        self.assertAlmostEqual(sum(v['mean'] for v in summary['joint_seats']['groups'].values()), len(self.test))
        for row in summary['joint_seats']['groups'].values():
            self.assertAlmostEqual(sum(row['histogram']), 1)
        self.assertIsNone(summary['joint_seats']['national_majority_probability'])

    def test_conditioning_filters_all_races(self):
        r = self.sim['races'][0]
        wins = self.sim['winners'][r['race_id']]
        j = int(np.argmax(np.bincount(wins)))
        conditioned = condition_on_winner(self.sim, r['race_id'], r['candidates'][j]['candidate_id'], 1)
        self.assertEqual(conditioned['draws'], int(np.sum(wins == j)))
        for k in self.sim['shares']:
            np.testing.assert_array_equal(conditioned['shares'][k], self.sim['shares'][k][wins == j])
        with self.assertRaisesRegex(ValueError, 'ESS'):
            condition_on_winner(self.sim, r['race_id'], r['candidates'][j]['candidate_id'], 401)

    def test_metrics_finite_and_same_sample(self):
        result = evaluate(self.sim, self.history)
        m = result['metrics']
        self.assertTrue(all(np.isfinite(v) for v in m.values()))
        self.assertEqual(m['races'], result['baselines']['carry_forward']['races'])
        self.assertLessEqual(m['coverage_90'], 1)
        self.assertGreaterEqual(m['rmse_pp'], m['mae_pp'])
        self.assertEqual(sum(b['candidate_rows'] for b in result['reliability_bins']), m['candidate_rows'])

    def test_roster_81_candidates_and_current_party(self):
        self.assertEqual(self.roster['candidate_count'], 81)
        self.assertEqual(len(self.roster['races']), 22)
        hsinchu = next(r for r in self.roster['races'] if r['county'] == '新竹市')
        self.assertEqual(sum(c['party'] is None for c in hsinchu['candidates']), 2)
        self.assertNotIn('KMT', [c['party'] for c in hsinchu['candidates']])
        self.assertTrue(all('share_pct' not in c for r in self.roster['races'] for c in r['candidates']))

    def test_current_candidates_are_separate_not_coalitions(self):
        trained = fit(self.train + self.test, self.history)
        sim = simulate(trained, self.roster['races'], self.history, self.train+self.test, self.sd,
                       draws=100, bootstrap_count=2)
        rows = summarize(sim)['county_forecasts']
        self.assertEqual(sum(len(r['candidates']) for r in rows), 81)
        taipei = next(r for r in rows if r['county'] == '台北市')
        self.assertEqual(len(taipei['candidates']), 6)

    def test_current_roster_never_auto_promotes(self):
        artifact = run(self.data, '2026-09-07T00:00:00+00:00', draws=100, bootstrap_count=2, roster=self.roster)
        self.assertFalse(artifact['release']['allowed'])
        self.assertEqual(artifact['county_forecasts'], [])
        self.assertIsNone(artifact['joint_seats'])
        self.assertIsNotNone(artifact['experimental_registration_forecast'])
        self.assertEqual(artifact['artifact_hash'], digest({k:v for k,v in artifact.items() if k != 'artifact_hash'}))

    def test_no_roster_from_the_future(self):
        with self.assertRaisesRegex(ValueError, 'snapshot'):
            run(self.data, '2026-09-06T00:00:00+00:00', draws=100, bootstrap_count=2, roster=self.roster)

    def test_workbook_import_fails_closed(self):
        r = {'县市': '台北市', '姓名': 'Test', '政党／身份': '無黨籍', '来源URL': 'javascript:alert(1)',
             '县市登记序号': 1, '登记状态': '已完成登记，待资格审查'}
        with self.assertRaisesRegex(ValueError, 'URL'):
            convert_rows([(5,r)], {'台北市': 1}, self.data, '2026-09-07', {})
        r['来源URL'] = 'https://example.com/roster'
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            convert_rows([(5,r),(6,r)], {'台北市': 2}, self.data, '2026-09-07', {})
        with self.assertRaisesRegex(ValueError, 'cover'):
            convert_rows([(5,r)], {'台北市': 1}, self.data, '2026-09-07', {})


if __name__ == '__main__':
    unittest.main()
