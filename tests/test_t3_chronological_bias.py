import copy
import json
import unittest
from pathlib import Path

import numpy as np

from model.v4_product import T3_ALPHA, T3_CARRY_WEIGHT, T3_FEATURES, T3_MODEL_WEIGHT
from scripts.evaluate_t3_chronological_bias import REPORT_KIND, evaluate, _metric, _bootstrap_cycle
from scripts.validate_release_candidate import build_third_rows

ROOT=Path(__file__).resolve().parents[1]


class T3ChronologicalBiasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report=evaluate(ROOT)

    def test_frozen_public_config_and_two_time_ordered_cycles(self):
        v=self.report
        self.assertEqual(v['kind'],REPORT_KIND)
        self.assertEqual(v['frozen_t3']['features'],T3_FEATURES)
        self.assertEqual(v['frozen_t3']['alpha'],T3_ALPHA)
        self.assertEqual(v['frozen_t3']['model_weight'],T3_MODEL_WEIGHT)
        self.assertEqual(v['frozen_t3']['carry_weight'],T3_CARRY_WEIGHT)
        self.assertEqual(set(v['cycles']),{'2018','2022'})
        self.assertEqual(v['cycles']['2018']['training_years'],[2014])
        self.assertEqual(v['cycles']['2022']['training_years'],[2014,2018])
        for y,c in v['cycles'].items():
            self.assertEqual(c['target_rows'],22)
            self.assertEqual(c['fit_rows'],22 if y=='2018' else 44)
            self.assertTrue(all(int(y)>a for a in c['training_years']))
            self.assertEqual(len({x['county'] for x in c['rows']}),22)
            self.assertEqual({int(x['target_year']) for x in c['rows']},{int(y)})
            self.assertTrue(all(x['training_years']==c['training_years'] for x in c['rows']))
        self.assertEqual(v['original_training_inventory'],{'2014':22,'2018':22,'2022':22})

    def test_2018_used_for_original_selection_2022_seen_before_not_blind(self):
        g=self.report['governance']
        self.assertFalse(g['independent_blind_holdout'])
        self.assertFalse(g['strict_historical_candidate_ballot_roster_vintage_proven'])
        self.assertFalse(g['official_forecast_modified'])
        self.assertFalse(g['nonmajor_2026_candidate_vote_share_tuned_using_2022_errors'])
        self.assertEqual(g['release_gate'],'blocked_until_independent_roster_and_probability_validation')

    def test_recompute_mean_error_directly_from_each_county_row(self):
        for y,c in self.report['cycles'].items():
            a=np.array([r['target_nonmajor_pct'] for r in c['rows']])/100
            p=np.array([r['t3_blend_nonmajor_pct'] for r in c['rows']])/100
            carry=np.array([r['prior_cycle_nonmajor_pct'] for r in c['rows']])/100
            d=_metric(p,a);b=_metric(carry,a)
            self.assertAlmostEqual(d['mae_pp'],c['metrics']['deployed_t3_70_30_roster_aware']['mae_pp'],places=4)
            self.assertAlmostEqual(d['signed_bias_pp'],c['metrics']['deployed_t3_70_30_roster_aware']['signed_bias_pp'],places=4)
            self.assertAlmostEqual(b['mae_pp'],c['metrics']['prior_cycle_carry_roster_aware']['mae_pp'],places=4)
            self.assertEqual(c['metrics']['deployed_t3_70_30_roster_aware']['overestimated_count']+
                             c['metrics']['deployed_t3_70_30_roster_aware']['underestimated_count'],
                             sum(abs(r['t3_blend_signed_error_pp'])>1e-8 for r in c['rows']))

    def test_zero_on_no_minor_candidate_roster_not_unbounded_prior(self):
        for cycle in self.report['cycles'].values():
            for row in cycle['rows']:
                if row['nonmajor_candidate_count']==0:
                    self.assertEqual(row['t3_blend_nonmajor_pct'],0)
                    self.assertEqual(row['prior_cycle_nonmajor_pct'],0)
                    self.assertAlmostEqual(row['target_nonmajor_pct'],0,places=7)

    def test_county_bootstrap_reproducible_and_paired(self):
        first=_bootstrap_cycle(np.array([.2,.3,.4]),np.array([.15,.2,.35]),np.array([.12,.34,.3]),seed=42,repetitions=250)
        second=_bootstrap_cycle(np.array([.2,.3,.4]),np.array([.15,.2,.35]),np.array([.12,.34,.3]),seed=42,repetitions=250)
        self.assertEqual(first,second)
        self.assertEqual(first['resample_unit'],'county')
        self.assertEqual(first['interval_level'],.9)
        self.assertLessEqual(*first['t3_signed_bias_pp_90pct_interval'])
        self.assertLessEqual(*first['t3_minus_carry_mae_pp_90pct_interval'])

    def test_original_prepared_features_not_mutated_and_json_finite(self):
        rows,_,_=build_third_rows(ROOT)
        before=json.dumps(rows,sort_keys=True,allow_nan=False)
        output=evaluate(ROOT)
        after,_,_=build_third_rows(ROOT)
        self.assertEqual(before,json.dumps(after,sort_keys=True,allow_nan=False))
        self.assertEqual(json.dumps(output,sort_keys=True),json.dumps(self.report,sort_keys=True))
        self.assertNotIn('target_nonmajor_share',T3_FEATURES)
        json.dumps(output,allow_nan=False)


if __name__=='__main__':
    unittest.main()
