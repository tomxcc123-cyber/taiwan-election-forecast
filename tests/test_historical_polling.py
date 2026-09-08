import copy
import unittest
from pathlib import Path
import numpy as np
from model.data import load_dataset
from model.historical_polling import load_polls, fit_error, eligible_at, build_research
from model.polling import observation_matrices
from model.joint import SETTINGS

ROOT=Path(__file__).resolve().parents[1]


class HistoricalPollingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.history=load_dataset(ROOT/'data/candidate-history-cec.json')
        cls.polls=load_polls(ROOT,cls.history['data_hash'])
        cls.research=build_research(ROOT,cls.history)

    def test_unique_facts_and_conservative_eligibility(self):
        rows=self.polls['records']
        self.assertEqual(len(rows),100)
        self.assertEqual(len({r['id'] for r in rows}),100)
        self.assertEqual(sum(r['eligible'] for r in rows),35)
        for r in rows:
            if r['eligible']:
                self.assertEqual(r['provenance'],'document_current')
                self.assertEqual(r['matchup_type'],'listed_field')
                self.assertGreaterEqual(r['sample_n'],100)
                self.assertTrue(all(r['candidate_ids']))
                self.assertEqual(len(r['source_sha256']),64)
            self.assertIsNone(r['published_at'])

    def test_2022_labels_and_polls_cannot_change_fit(self):
        history=copy.deepcopy(self.history['races'])
        polls=copy.deepcopy(self.polls['records'])
        for r in history:
            if r['year']==2022:
                for c in r['candidates']:c['share_pct']=999
        for r in polls:
            if r['year']==2022:r['supports']=[999]*len(r['supports'])
        self.assertEqual(fit_error(polls,history),self.research['fit'])
        self.assertEqual(self.research['fit']['training_waves'],29)
        self.assertEqual(self.research['fit']['training_races'],20)

    def test_no_error_floor_tightening(self):
        fitted=self.research['fit']
        self.assertGreaterEqual(fitted['applied_value'],SETTINGS['poll_extra_sd'])
        self.assertTrue(fitted['boundary_solution'])

    def test_cutoffs_exclude_future_and_postponed_poll(self):
        rows=eligible_at(self.polls['records'],2022,'2022-10-27')
        self.assertEqual(len(rows),5)
        self.assertTrue(all(r['date']<='2022-10-27' for r in rows))
        self.assertFalse(any(r['county']=='嘉義市' for r in rows))

    def test_tvbs_scale_not_transferred_to_other_pollsters(self):
        r=copy.deepcopy(next(r for r in self.polls['records'] if r['eligible']))
        race=next(x for x in self.history['races'] if x['race_id']==r['race_id'])
        candidates=race['candidates']
        base=observation_matrices([r],candidates,SETTINGS)[2]
        changed=observation_matrices([r],candidates,{**SETTINGS,'tvbs_poll_extra_sd':.7})[2]
        self.assertTrue(np.all(np.diag(changed)>np.diag(base)))
        r.update(source='Other',pollster_id='other')
        np.testing.assert_allclose(base,observation_matrices([r],candidates,{**SETTINGS,'tvbs_poll_extra_sd':.7})[2])

    def test_polled_subset_preserves_simulation_candidate_order(self):
        for report in self.research['validation']['reports']:
            counties={r['county'] for r in self.polls['records'] if r['id'] in report['poll_ids']}
            errors=[]
            for county in counties:
                details=[d for d in report['details'] if d['county']==county]
                errors.append(np.mean([abs(d['predicted_pct']-d['actual_closed_pct']) for d in details]))
            self.assertAlmostEqual(report['polled_subset']['mae_pp'],np.mean(errors),places=10)
            self.assertEqual(report['metrics']['races'],22)
            self.assertEqual(report['metrics']['candidate_rows'],94)
            self.assertTrue(np.isfinite(list(report['metrics'].values())).all())

    def test_poll_history_cannot_enter_current_model(self):
        from model.polling import match_records
        from model.roster import load_roster
        roster=load_roster(ROOT/'data/registration-roster-2026.json',self.history)
        self.assertFalse(match_records({'records':self.polls['records']},roster,'2026-09-08')[0])
