import copy
import unittest
from scripts.evaluate_turnout_county_cycles import county_cycles

def history():
    rows=[]
    for i in range(22):
        name='合成縣'+str(i)
        for year,cast in [(2014,50+i),(2018,53+i),(2022,45+i)]:
            rows.append({'year':year,'county':name,
                'electorate':100,'ballots_cast':cast,
                'valid_votes':cast-1,'invalid_votes':1})
    return {'races':rows}

class CountyTwoCycleTests(unittest.TestCase):
    def test_pre_outcome_inputs_and_22_counties(self):
        r=county_cycles(history())
        self.assertEqual(r['cycle_count'],2)
        self.assertEqual(r['county_count_each_cycle'],22)
        self.assertEqual(len(r['cycles']['2014_to_2018']['rows']),22)
        self.assertEqual(len(r['cycles']['2018_to_2022']['rows']),22)
        self.assertEqual(r['promotion_gate']['status'],'blocked')
        self.assertEqual(r['cycles']['2014_to_2018']['scores']['persistence']['weighted_mae_pp'],3.)
        self.assertEqual(r['cycles']['2018_to_2022']['scores']['persistence']['weighted_mae_pp'],8.)
    def test_future_outcome_not_used_to_predict_itself(self):
        source=history()
        a=county_cycles(source)
        b=copy.deepcopy(source)
        for row in b['races']:
            if row['year']==2022:
                row['ballots_cast']-=10
                row['valid_votes']-=10
        v=county_cycles(b)
        self.assertEqual(
            [r['predicted_turnout_pct'] for r in a['cycles']['2018_to_2022']['rows']],
            [r['predicted_turnout_pct'] for r in v['cycles']['2018_to_2022']['rows']])
        self.assertNotEqual(
            a['cycles']['2018_to_2022']['scores'],
            v['cycles']['2018_to_2022']['scores'])
    def test_missing_race_rejected(self):
        a=history();a['races'].pop()
        with self.assertRaisesRegex(ValueError,'66'):
            county_cycles(a)
    def test_invalid_vote_conservation_rejected(self):
        a=history();a['races'][0]['invalid_votes']=2
        with self.assertRaisesRegex(ValueError,'accounting'):
            county_cycles(a)
    def test_distinct_experiment_parameters(self):
        r=county_cycles(history())
        self.assertEqual(r['model_weights']['persistence'],1)
        self.assertEqual(r['model_weights']['national_shrink_75'],.75)
        self.assertEqual(r['model_weights']['national_shrink_50'],.5)

if __name__=='__main__':unittest.main()
