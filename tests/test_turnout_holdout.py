import unittest
from scripts.evaluate_turnout_holdout import evaluate,weighted_centered_corr,county_prior

def history():
    races=[]
    for county in ['甲縣','乙縣','丙縣']:
        for year,cast in [(2014,60),(2018,70),(2022,50)]:
            races.append({'county':county,'year':year,'electorate':100,
                          'ballots_cast':cast,'valid_votes':cast-2,'invalid_votes':2})
    # Add 19 more counties (22*3 full historical county races).
    for i in range(19):
        county='合成'+str(i)
        for year,cast in [(2014,60),(2018,70),(2022,50)]:
            races.append({'county':county,'year':year,'electorate':100,
                          'ballots_cast':cast,'valid_votes':cast-2,'invalid_votes':2})
    return {'races':races}

def panel():
    rows=[]
    for county in ['甲縣','乙縣','丙縣']:
        districts=[]
        for i,turnout in enumerate((.6,.7)):
            a,b={'electorate':100,'ballots_cast':int(turnout*100)},{
                   'electorate':100,'ballots_cast':int((turnout-.1)*100)}
            districts.append({'district':'區'+str(i),'district_code':county+'-'+str(i),
              'years':{'2018':a,'2022':b},
              'delta_turnout_pp':-10})
        rows.append({'county':county,'status':'matched_code_name_only','districts':districts})
    return {'schema_version':1,'matched_districts':6,
      'counties':rows+[{'county':'合成'+str(i),'status':'excluded','districts':[]} for i in range(19)]}

class TurnoutHoldoutTests(unittest.TestCase):
    def test_strict_pre_2022_baselines(self):
        p=panel();r=evaluate(p,history())
        self.assertEqual(r['training_information_cutoff_election'],2018)
        self.assertEqual(r['held_out_election'],2022)
        self.assertEqual(r['coverage']['districts'],6)
        self.assertEqual(r['turnout_forecast_score']['2018_persistence']['towns'],6)
        self.assertAlmostEqual(r['turnout_forecast_score']['2018_persistence']['electorate_weighted_mae_pp'],10)
        self.assertAlmostEqual(r['turnout_forecast_score']['2014_to_2018_county_drift']['electorate_weighted_mae_pp'],20)
        self.assertEqual(r['association']['status'],'no_audited_elctks_candidate_data')
    def test_no_future_leakage(self):
        p=panel();h=history()
        initial=evaluate(p,h)
        for row in h['races']:
            if row['year']==2022:row['ballots_cast']=10
        updated=evaluate(p,h)
        self.assertEqual(initial['turnout_forecast_score'],updated['turnout_forecast_score'])
    def test_descriptive_pairing(self):
        p=panel()
        c=[]
        for x in p['counties']:
            c.append({'county':x['county'],'districts':[{
              'district_code':d['district_code'],'party_comparison_eligible':True,
              'delta_turnout_pp':d['delta_turnout_pp'],
              'delta_KMT_two_party_share_pp':5}
              for d in x['districts']]})
        a={'kind':'historical_ecological_candidate_turnout_association_only',
           'official_forecast_unchanged':True,'matched_towns':6,'counties':c}
        r=evaluate(p,history(),a)
        self.assertEqual(r['association']['status'],'post_election_ecological_descriptive_only')
        self.assertEqual(r['association']['comparable_towns'],6)
        self.assertIsNone(r['association']['within_county_centered_weighted_pearson'])
        self.assertFalse(r['calibration_claim'])
    def test_missing_historical_prior(self):
        h=history();h['races'].pop()
        with self.assertRaises(ValueError):evaluate(panel(),h)

if __name__=='__main__':unittest.main()
