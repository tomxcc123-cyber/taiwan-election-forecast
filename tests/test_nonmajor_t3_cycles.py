"""Historical 2018/2022 third-party-mass audit and governance regressions."""
import json
import unittest
from pathlib import Path

from scripts.audit_nonmajor_t3_cycles import build_t3_cycle_audit, _bootstrap_mae_delta, _metrics

ROOT=Path(__file__).resolve().parents[1]


class T3ThreeCycleAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out=build_t3_cycle_audit(ROOT)

    def test_exact_cec_coverage_and_out_of_time_splits(self):
        v=self.out
        self.assertEqual(v['rows_by_target_year'],{'2014':22,'2018':22,'2022':22})
        self.assertEqual(v['historical_years_available'],[2014,2018,2022])
        self.assertEqual(v['training_year_only'],2014)
        self.assertEqual(v['selection_year'],2018)
        self.assertEqual(v['chronological_test_year'],2022)
        self.assertEqual([(c['year'],c['training_years']) for c in v['cycles']],
                         [(2018,[2014]),(2022,[2014,2018])])
        self.assertEqual([len(c['county_rows']) for c in v['cycles']],[22,22])
        self.assertEqual(len(set(r['county'] for r in v['cycles'][1]['county_rows'])),22)

    def test_real_cec_vote_mass_and_absence_of_future_leakage(self):
        for cycle in self.out['cycles']:
            for row in cycle['county_rows']:
                self.assertEqual(row['year'],cycle['year'])
                self.assertTrue(row['source_verified_county_results'])
                self.assertGreaterEqual(row['actual_pct'],0)
                self.assertLessEqual(row['actual_pct'],100)
                self.assertLessEqual(abs(row['t3_blended_error_pp']-
                                         (row['production_blended_pct']-row['actual_pct'])),.000002)
                self.assertAlmostEqual(row['production_blended_pct'],
                                       .7*row['production_t3_raw_pct']+.3*row['lagged_carry_pct'],places=4)
                self.assertGreaterEqual(row['nonmajor_candidate_count'],0)
                if row['nonmajor_candidate_count']==0:
                    self.assertEqual(row['actual_pct'],0)
                    self.assertEqual(row['production_t3_raw_pct'],0)
                    self.assertEqual(row['production_blended_pct'],0)
                    self.assertEqual(row['lagged_carry_pct'],0)

    def test_group_counts_and_bias_reproduction(self):
        for cycle in self.out['cycles']:
            groups=cycle['groups']
            self.assertEqual(sum(groups[k]['n'] for k in (
                'nonmajor_candidates_0','nonmajor_candidates_1','nonmajor_candidates_2plus')),22)
            self.assertEqual(groups['has_tpp']['n']+groups['no_tpp']['n'],22)
            actual_metrics=_metrics(cycle['county_rows'],'production_blended_pct')
            self.assertEqual(actual_metrics,cycle['metrics']['production_spec_70_30'])
            for metric in cycle['metrics'].values():
                self.assertEqual(metric['n'],22)
                self.assertGreaterEqual(metric['mae_pp'],0)
            self.assertEqual(len(cycle['largest_absolute_errors']),8)

    def test_bootstrap_is_deterministic_and_no_false_significance(self):
        items=self.out['cycles'][1]['county_rows']
        a=_bootstrap_mae_delta(items,'production_blended_pct','lagged_carry_pct',draws=500,seed=14)
        b=_bootstrap_mae_delta(items,'production_blended_pct','lagged_carry_pct',draws=500,seed=14)
        self.assertEqual(a,b)
        self.assertEqual(a['unit'],'county_paired_resample')
        self.assertLessEqual(a['percentile_95_low_pp'],a['percentile_95_high_pp'])

    def test_2026_forecast_promotion_is_explicitly_blocked(self):
        v=self.out
        self.assertEqual(v['promotion_gate']['status'],'blocked')
        self.assertFalse(v['forecast_2026_modified'])
        self.assertFalse(v['probability_calibrated'])
        self.assertIn('not_project_blind',v['cycles'][1]['role'])
        self.assertEqual(v['kind'],'t3_chronological_nonmajor_mass_bias_audit_not_forecast_calibration')
        self.assertEqual(len(v['primary_source_sha256']),3)
        self.assertTrue(all(len(value)==64 for value in v['primary_source_sha256'].values()))


if __name__=='__main__':
    unittest.main()
