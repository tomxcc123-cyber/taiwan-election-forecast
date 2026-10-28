import copy
import unittest
from scripts.evaluate_turnout_two_cycle_towns import evaluate

def fixture():
    counties14=[]
    counties18=[]
    hist=[]
    for i in range(22):
        county='測試縣'+str(i)
        for year,cast in [(2014,60),(2018,70),(2022,55)]:
            hist.append({'year':year,'county':county,
                'electorate':100,'ballots_cast':cast,'valid_votes':cast-2,
                'invalid_votes':2})
        a={'electorate':40,'ballots_cast':24,'valid_votes':23,'invalid_votes':1}
        b={'electorate':40,'ballots_cast':28,'valid_votes':27,'invalid_votes':1}
        c={'electorate':40,'ballots_cast':22,'valid_votes':21,'invalid_votes':1}
        counties14.append({'county':county,'status':'matched_original_code_name',
            'districts':[{'district':'甲區','years':{'2014':copy.deepcopy(a),'2018':copy.deepcopy(b)}}]})
        counties18.append({'county':county,'status':'matched_code_name_only',
            'districts':[{'district':'甲區','years':{'2018':copy.deepcopy(b),'2022':copy.deepcopy(c)}}]})
    p14={'kind':'observed_cec_2014_to_2018_town_turnout_holdout_input',
        'no_cross_year_precinct_join':True,'official_2026_forecast_unchanged':True,
        'counties':counties14,'matched_towns':22}
    p18={'kind':'observed_turnout_district_panel_not_an_individual_turnout_model',
        'official_forecast_unchanged':True,'counties':counties18,'matched_districts':22}
    return p14,p18,{'races':hist}

class TwoCycleTests(unittest.TestCase):
    def test_independent_holdouts_and_no_promotion(self):
        p14,p18,history=fixture()
        r=evaluate(p14,p18,history)
        self.assertEqual(set(r['cycles']),{'2014_to_2018','2018_to_2022'})
        self.assertEqual(r['cycles']['2014_to_2018']['matched_towns'],22)
        self.assertEqual(r['cycles']['2018_to_2022']['matched_towns'],22)
        self.assertEqual(r['promotion_gate']['status'],'blocked')
        self.assertFalse(r['candidate_vote_data_used'])
        self.assertTrue(r['no_future_outcome_predictors'])
        for key in ('persistence','county_shrink_75','county_shrink_50'):
            self.assertIn(key,r['cycles']['2014_to_2018']['scores'])
            self.assertIn(key,r['cycles']['2018_to_2022']['scores'])
        self.assertAlmostEqual(
            r['cycles']['2014_to_2018']['scores']['persistence']['electorate_weighted_mae_pp'],10)
        self.assertAlmostEqual(
            r['cycles']['2018_to_2022']['scores']['persistence']['electorate_weighted_mae_pp'],15)
    def test_2018_outcomes_not_2018_predictors(self):
        p14,p18,history=fixture()
        a=evaluate(p14,p18,history)
        for county in p14['counties']:
            town=county['districts'][0]
            town['years']['2018'].update({
                'ballots_cast':32,'valid_votes':31,'invalid_votes':1})
        b=evaluate(p14,p18,history)
        forecasts=lambda r:[x['forecast_pct'] for x in r['cycles']['2014_to_2018']['towns']]
        self.assertEqual(forecasts(a),forecasts(b))
        self.assertNotEqual(a['cycles']['2014_to_2018']['scores'],
                            b['cycles']['2014_to_2018']['scores'])
    def test_2022_outcomes_not_2022_predictors(self):
        p14,p18,history=fixture()
        a=evaluate(p14,p18,history)
        for county in p18['counties']:
            county['districts'][0]['years']['2022'].update({
                'ballots_cast':30,'valid_votes':29,'invalid_votes':1})
        b=evaluate(p14,p18,history)
        forecasts=lambda r:[x['forecast_pct'] for x in r['cycles']['2018_to_2022']['towns']]
        self.assertEqual(forecasts(a),forecasts(b))
        self.assertNotEqual(a['cycles']['2018_to_2022']['scores'],
                            b['cycles']['2018_to_2022']['scores'])
    def test_broken_2014_provenance_rejected(self):
        p14,p18,history=fixture()
        p14['no_cross_year_precinct_join']=False
        with self.assertRaisesRegex(ValueError,'Unverified'):
            evaluate(p14,p18,history)
    def test_bad_historical_source_rejected(self):
        p14,p18,h=fixture()
        h['races'].pop()
        with self.assertRaisesRegex(ValueError,'66'):
            evaluate(p14,p18,h)
    def test_consistency_with_existing_2022_shadow(self):
        p14,p18,h=fixture()
        old=evaluate(p14,p18,h)
        shadow={'kind':'turnout_forecast_shadow_ablation_2022_exploratory',
            'training_cutoff_election':2018,
            'scores':{k:{'mae_pp':v['electorate_weighted_mae_pp']}
                for k,v in old['cycles']['2018_to_2022']['scores'].items()}}
        evaluate(p14,p18,h,shadow)
        shadow['scores']['persistence']['mae_pp']+=1
        with self.assertRaisesRegex(ValueError,'cannot reproduce'):
            evaluate(p14,p18,h,shadow)

if __name__=='__main__':unittest.main()
