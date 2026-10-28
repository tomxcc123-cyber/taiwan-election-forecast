"""Synthetic unit tests only. Distinguish exploratory 2022 scores from future predictive evidence."""
import copy
import unittest
from scripts.evaluate_turnout_shadows import (
    shadow_predictions,compare,paired_bootstrap_by_county
)

def fixture():
    hist=[]
    counties=[]
    for i in range(22):
        name='縣'+str(i)
        for year,cast in [(2014,60),(2018,70),(2022,50)]:
            hist.append({'year':year,'county':name,
                         'electorate':100,'ballots_cast':cast})
        districts=[]
        if i<21:
            districts=[{'district':'區甲','district_code':str(i)+'/01',
                        'years':{'2018':{'electorate':100,'ballots_cast':65},
                                 '2022':{'electorate':100,'ballots_cast':52}}}]
        counties.append({'county':name,
            'status':'matched_code_name_only' if districts else 'excluded',
            'districts':districts})
    return ({'schema_version':1,
             'kind':'observed_turnout_district_panel_not_an_individual_turnout_model',
             'official_forecast_unchanged':True,
             'matched_districts':21,'counties':counties},
            {'races':hist})

class ShadowTurnoutTests(unittest.TestCase):
    def test_formula_and_shrinkage(self):
        info={'t14':.6,'t18':.7,'county_drift':.1}
        result=shadow_predictions(.65,info,.04)
        self.assertAlmostEqual(result['persistence'],.65)
        self.assertAlmostEqual(result['county_shrink_75'],.6625)
        self.assertAlmostEqual(result['county_shrink_50'],.675)
        self.assertAlmostEqual(result['county_drift_25'],.675)
        self.assertAlmostEqual(result['national_drift_25'],.66)
        self.assertAlmostEqual(result['shrink_75_drift_25'],.6875)
        self.assertAlmostEqual(result['county_drift_100'],.75)
    def test_readonly_shadow_evaluation(self):
        panel,hist=fixture()
        report=compare(panel,hist)
        self.assertEqual(report['coverage']['towns'],21)
        self.assertEqual(report['coverage']['counties'],21)
        self.assertEqual(report['promotion_gate']['status'],'blocked')
        self.assertFalse(report['candidate_party_votes_used_in_predictors'])
        self.assertTrue(report['uses_2022_outcomes_only_for_scoring'])
        self.assertAlmostEqual(report['scores']['persistence']['mae_pp'],13)
        self.assertEqual(report['scores']['persistence']['county_bootstrap'],None)
        self.assertEqual(report['scores']['persistence']['delta_mae_vs_persistence_pp'],0)
        self.assertEqual(len(report['scores']['county_shrink_75']['county_bootstrap']
                             ['difference_vs_persistence_mae_pp_90pct_county_bootstrap']),2)
    def test_future_label_is_not_a_predictor(self):
        p,h=fixture()
        first=compare(p,h)
        changed=copy.deepcopy(p)
        for c in changed['counties']:
            for town in c['districts']:
                town['years']['2022']['ballots_cast']=30
        second=compare(changed,h)
        self.assertEqual(
          [r['forecast_pct'] for r in first['holdout_rows']],
          [r['forecast_pct'] for r in second['holdout_rows']])
        self.assertNotEqual(first['scores']['persistence']['mae_pp'],
                            second['scores']['persistence']['mae_pp'])
    def test_prior_2022_not_used(self):
        p,h=fixture()
        a=compare(p,h)
        for r in h['races']:
            if r['year']==2022:r['ballots_cast']=10
        b=compare(p,h)
        self.assertEqual(a['scores'],b['scores'])
    def test_bad_provenance_rejected(self):
        p,h=fixture()
        p['official_forecast_unchanged']=False
        with self.assertRaisesRegex(ValueError,'verified historical'):compare(p,h)
    def test_check_reproduce_original_holdout(self):
        p,h=fixture()
        old={'kind':'cec_historical_time_ordered_turnout_holdout',
             'held_out_election':2022,'training_information_cutoff_election':2018,
             'coverage':{'districts':21},
             'turnout_forecast_score':{'2018_persistence':{
                 'electorate_weighted_mae_pp':13,
                 'electorate_weighted_rmse_pp':13}}}
        compare(p,h,old)
        old['turnout_forecast_score']['2018_persistence']['electorate_weighted_mae_pp']=12
        with self.assertRaisesRegex(ValueError,'does not reproduce'):compare(p,h,old)
    def test_resampled_counties_deterministic(self):
        rows=[{'county':'甲','weight':1,'errors_pp':{'x':2,'persistence':1}},
              {'county':'乙','weight':2,'errors_pp':{'x':3,'persistence':1}},
              {'county':'丙','weight':4,'errors_pp':{'x':4,'persistence':2}}]
        self.assertEqual(paired_bootstrap_by_county(rows,'x'),
                         paired_bootstrap_by_county(rows,'x'))

if __name__=='__main__':unittest.main()
