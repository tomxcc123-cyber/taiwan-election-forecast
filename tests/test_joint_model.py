import copy
import json
import unittest
from pathlib import Path
from datetime import datetime, timezone
import numpy as np
from model.data import load_dataset, audit_race, previous_race
from model.roster import load_roster
from model.fundamentals import fit, residual_scale
from model.simulation import simulate
from model.polling import match_records, observation_matrices
from model.joint import infer, SETTINGS
from model.product import build_product

ROOT=Path(__file__).resolve().parents[1]


class JointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.history=load_dataset(ROOT/'data/candidate-history.json')
        cls.roster=load_roster(ROOT/'data/registration-roster-2026.json',cls.history)
        cls.feed=json.loads((ROOT/'data/polls.json').read_text(encoding='utf-8'))
        h=cls.history['races']
        train=[r for r in h if audit_race(r)['research_eligible'] and previous_race(h,r)]
        cls.prior=simulate(fit(train,h),cls.roster['races'],h,train,residual_scale(train,h),draws=400,bootstrap_count=10)
        fixtures=[]
        for i,r in enumerate(cls.roster['races'][:2]):
            fixtures.append({'id':f'fixture-{i}','county':r['county'],'source':'Synthetic test institute',
                'source_url':f'https://example.com/report-{i}','field_start':'2026-09-01','date':'2026-09-03',
                'sample_n':1000,'undecided':10,'model_eligible':False,
                'candidates':[{'name':c['name'],'support':v,'bloc':'ignored'}
                              for c,v in zip(r['candidates'][:2],[60,30])]})
        cls.records,cls.audit=match_records({'records':fixtures},cls.roster,'2026-09-08')

    def test_matching_is_candidate_not_old_bloc(self):
        self.assertEqual(len(self.records),2)
        self.assertTrue(all(not r['model_eligible'] for r in self.records))
        self.assertTrue(all(len(r['candidate_ids'])>=2 for r in self.records))

    def test_future_and_mismatched_name_rejected(self):
        r=copy.deepcopy(self.feed['records'][0]);r['date']='2027-01-01'
        self.assertFalse(match_records({'records':[r]},self.roster,'2026-09-08')[0])
        r=copy.deepcopy(self.feed['records'][0]);r['candidates'][0]['name']='NOT A CANDIDATE'
        self.assertFalse(match_records({'records':[r]},self.roster,'2026-09-08')[0])

    def test_overlapping_samples_not_double_counted(self):
        r=copy.deepcopy(self.records[0]);other={**r,'id':'duplicate'}
        accepted,audit=match_records({'records':[r,other]},self.roster,'2026-09-08')
        self.assertEqual(len(accepted),1)
        self.assertEqual(sum(a['included'] for a in audit),1)

    def test_zero_poll_support_regularized_and_undecided_preserved(self):
        r=copy.deepcopy(self.records[0]);r['supports']=[0,80];r['undecided']=20
        candidates=[c for race in self.prior['races'] for c in race['candidates']]
        a,y,v,_,_=observation_matrices([r],candidates,SETTINGS)
        self.assertTrue(np.isfinite(y).all());self.assertTrue(np.isfinite(v).all())
        np.testing.assert_allclose(a.sum(axis=1),0,atol=1e-12)
        self.assertEqual(r['undecided'],20)

    def test_joint_covariance_positive_and_centered(self):
        p=infer(self.prior,self.records,'2026-09-08','2026-11-28',{'simulations':100})
        self.assertGreaterEqual(np.linalg.eigvalsh(p['covariance']).min(),-1e-8)
        offset=0
        for r in p['races']:
            k=len(r['candidates']);self.assertAlmostEqual(p['mean'][offset:offset+k].sum(),0,places=7);offset+=k

    def test_shared_information_updates_unpolled_county(self):
        before=infer(self.prior,[],'2026-09-08','2026-11-28',{'simulations':100})
        after=infer(self.prior,self.records[:1],'2026-09-08','2026-11-28',{'simulations':100})
        index=0;found=False
        for r in before['races']:
            k=len(r['candidates'])
            if r['race_id']!=self.records[0]['race_id'] and not np.allclose(before['mean'][index:index+k],after['mean'][index:index+k]):found=True
            index+=k
        self.assertTrue(found)

    def test_future_variance_monotonically_increases(self):
        near=infer(self.prior,self.records,'2026-09-08','2026-09-08',{'simulations':100})
        far=infer(self.prior,self.records,'2026-09-08','2026-11-28',{'simulations':100})
        self.assertGreater(np.trace(far['covariance']),np.trace(near['covariance']))

    def test_weak_first_poll_does_not_remove_variance(self):
        before=infer(self.prior,[],'2026-09-08','2026-11-28',{'simulations':100})
        after=infer(self.prior,self.records,'2026-09-08','2026-11-28',{'simulations':100,'poll_extra_sd':1e6})
        np.testing.assert_allclose(before['mean'],after['mean'],atol=1e-8)
        np.testing.assert_allclose(before['covariance'],after['covariance'],atol=1e-8)

    def test_increasing_undecided_widens_measurement(self):
        candidates=[c for race in self.prior['races'] for c in race['candidates']]
        a=copy.deepcopy(self.records[0]);b=copy.deepcopy(a)
        a['undecided']=0;b['undecided']=60
        va=observation_matrices([a],candidates,SETTINGS)[2];vb=observation_matrices([b],candidates,SETTINGS)[2]
        self.assertGreater(np.trace(vb),np.trace(va))

    def test_reproducible_product_not_claiming_calibration(self):
        now=datetime(2026,9,8,tzinfo=timezone.utc)
        a=build_product(ROOT,now,self.feed,{'simulations':100})
        b=build_product(ROOT,now,self.feed,{'simulations':100})
        self.assertEqual(a,b);self.assertFalse(a['release']['calibrated_forecast'])
        self.assertEqual(sum(len(r['candidates']) for r in a['counties']),81)


if __name__=='__main__':unittest.main()
