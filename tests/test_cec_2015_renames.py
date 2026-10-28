"""Official-name crosswalk tests use immutable original CEC station JSON."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.recover_cec_2015_town_renames import RENAMES, recover, read
from scripts.evaluate_turnout_two_cycle_towns import evaluate as evaluate_cycles
from scripts.audit_turnout_three_year import evaluate as audit_common

ROOT=Path(__file__).resolve().parents[1]
D=ROOT/'data'


def inputs():
    return (read(D/'turnout-district-panel-2014-2018.json'),
            read(D/'turnout-district-panel-2018-2022.json'),
            read(D/'candidate-history-cec.json'))


class Official2015RenameTests(unittest.TestCase):
    def test_two_recovered_original_cec_pairs_and_holdout(self):
        prior,recent,h=inputs()
        amended,detail=recover(prior,recent)
        self.assertEqual(amended['matched_towns'],368)
        self.assertEqual(len(detail),2)
        self.assertEqual(amended['documented_2015_name_changes_count'],2)
        self.assertTrue(amended['no_historical_polygon_comparison'])
        for (county,code),rule in RENAMES.items():
            d=next(x for x in next(c for c in amended['counties'] if c['county']==county)['districts']
                   if x['town_code']==code)
            self.assertEqual(d['district'],rule['after'])
            self.assertEqual(d['documented_name_change']['2014_original_name'],rule['before'])
            self.assertFalse(d['documented_name_change']['spatial_boundary_verified'])
            for year in ('2014','2018'):
                x=d['years'][year]
                self.assertEqual(x['valid_votes']+x['invalid_votes'],x['ballots_cast'])
        report=evaluate_cycles(amended,recent,h)
        self.assertEqual(report['cycles']['2014_to_2018']['matched_towns'],368)
        self.assertEqual(report['cycles']['2018_to_2022']['matched_towns'],366)
        self.assertAlmostEqual(
            report['cycles']['2014_to_2018']['scores']['persistence']['electorate_weighted_mae_pp'],
            3.48121, places=4)
        self.assertAlmostEqual(
            report['cycles']['2014_to_2018']['scores']['county_shrink_75']['electorate_weighted_mae_pp'],
            3.42915, places=4)
        common=audit_common(amended,recent,report)
        self.assertEqual(common['matched_towns'],366)
        self.assertAlmostEqual(common['cohorts']['common_towns']['2014_to_2018']['scores']['persistence'],
                               3.48595, places=4)
        self.assertAlmostEqual(common['cohorts']['common_towns']['2014_to_2018']['scores']['county_shrink_75'],
                               3.43334, places=4)
        self.assertAlmostEqual(common['cohorts']['common_towns']['2018_to_2022']['scores']['persistence'],
                               6.22726, places=4)
        self.assertEqual(common['documented_2015_name_changes_count'],2)
        self.assertEqual(len(common['unmatched_recent']),0)
        self.assertEqual(len(common['unmatched_prior']),2) # 2022 Chiayi City has no matched townships

    def test_idempotent_recovery_avoids_duplicate_town_or_verification_note(self):
        p,r,_=inputs()
        a,_=recover(p,r)
        b,items=recover(copy.deepcopy(a),r)
        self.assertEqual(a,b)
        self.assertEqual(len([x for x in items if x['already_reconciled']]),2)

    def test_original_name_tampering_fails_closed(self):
        p,r,_=inputs()
        county=next(c for c in p['counties'] if c['county']=='彰化縣')
        if county['unmatched_2014_names']:
            county['unmatched_2014_names']=['杜撰鎮']
            with self.assertRaisesRegex(ValueError,'official 2014/2018 names'):
                recover(p,r)
        else:
            row=next(x for x in county['districts'] if x['town_code']=='100')
            row['documented_name_change']['2014_original_name']='杜撰鎮'
            with self.assertRaisesRegex(ValueError,'unverified provenance'):
                recover(p,r)

    def test_unverified_2018_vote_accounting_rejected(self):
        p,r,_=inputs()
        if p['matched_towns']==368:
            # Recreate recovery scenario using tests of an already restored CEC panel
            county=next(c for c in p['counties'] if c['county']=='苗栗縣')
            county['districts']=[x for x in county['districts'] if x['town_code']!='050']
            county['unmatched_2014_names']=['頭份鎮']
            county['unmatched_2018_names']=['頭份市']
            county['2014_original_district_count']=len(county['districts'])+1
            county['2018_original_district_count']=len(county['districts'])+1
        district=next(x for x in next(c for c in r['counties'] if c['county']=='苗栗縣')['districts']
                      if x['district_code'].endswith('/050'))
        district['years']['2018']['valid_votes']+=1
        with self.assertRaisesRegex(ValueError,'2018 CEC historical town totals disagree'):
            recover(p,r)


if __name__=='__main__':
    unittest.main()
