import copy
import json
import unittest
from pathlib import Path
import numpy as np
from model.data import eligible_cec_transitions, load_dataset
from model.fundamentals import features, organization_parties
from model.refinement import select_fit, support_roster

ROOT=Path(__file__).resolve().parents[1]


class RefinementTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.history=load_dataset(ROOT/'data/candidate-history-cec.json')['races']
        cls.roster=json.loads((ROOT/'data/registration-roster-2026.json').read_text(encoding='utf-8'))

    def test_selection_is_training_only_and_reproducible(self):
        train=[r for r in eligible_cec_transitions(self.history) if r['year']==2018]
        a=select_fit(train,self.history)
        changed=copy.deepcopy(self.history)
        for r in changed:
            if r['year']==2022:
                for c in r['candidates']:c['share_pct']=100/len(r['candidates'])
        b=select_fit(train,changed)
        self.assertEqual(a,b)
        self.assertEqual(a['selection']['training_years'],[2018])
        self.assertEqual(a['selection']['selected_alpha'],.1)
        self.assertFalse(a['selection']['proposal_adopted'])

    def test_support_inputs_do_not_change_official_identity(self):
        before=copy.deepcopy(self.roster)
        after,applied=support_roster(self.roster,ROOT,'2026-09-09T08:00:00Z')
        self.assertEqual(self.roster,before)
        self.assertEqual(len(applied),3)
        for old,new in zip(before['races'],after['races']):
            for a,b in zip(old['candidates'],new['candidates']):
                self.assertEqual(a['party'],b['party'])
                self.assertEqual(a['candidate_id'],b['candidate_id'])
        hsinchu=next(r for r in after['races'] if r['county']=='新竹市')
        gao=next(c for c in hsinchu['candidates'] if c['name']=='高虹安')
        self.assertIsNone(gao['party'])
        self.assertEqual(organization_parties(gao),['KMT'])
        original=next(r for r in before['races'] if r['county']=='新竹市')
        self.assertFalse(np.array_equal(features(original,self.history),features(hsinchu,self.history)))

    def test_future_review_does_not_enter_prediction(self):
        roster,applied=support_roster(self.roster,ROOT,'2026-09-08T08:00:00Z')
        self.assertEqual(applied,[])
        self.assertEqual(roster,self.roster)

    def test_organization_links_deduplicate(self):
        candidate={'party':'KMT','organization_parties':['KMT','TPP','TPP','not-a-party']}
        self.assertEqual(organization_parties(candidate),['KMT','TPP'])

    def test_selection_requires_county_groups(self):
        train=[r for r in eligible_cec_transitions(self.history) if r['year']==2018][:2]
        with self.assertRaises(ValueError):select_fit(train,self.history)
