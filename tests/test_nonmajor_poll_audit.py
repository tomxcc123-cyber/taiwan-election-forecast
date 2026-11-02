"""Source-anchored, non-causal, non-promoting nonmajor poll response audit tests."""
import copy
import json
import unittest
from datetime import date
from pathlib import Path
from model.nonmajor_poll_audit import build_nonmajor_response_audit

ROOT=Path(__file__).resolve().parents[1]


class NonmajorResponseAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reviewed=json.loads((ROOT/'data/reviewed-additional-polls.json').read_text(encoding='utf8'))
        cls.entries=[x for x in reviewed['reports'] if x.get('pollster_id')=='udn-poll-center']
        cls.verified_at=reviewed['reviewed_at']

    def fixtures(self):
        row={
            'id':'original-source-1','county':'台北市','source':'聯合報系民意調查中心',
            'source_url':'https://udn.com/news/story/124652/9840910',
            'pollster_id':'udn-poll-center','field_start':'2026-10-20',
            'date':'2026-10-25','published_at':'2026-10-28','retrieved_at':'2026-11-02T00:00:00+00:00',
            'candidates':[{'name':'蔣萬安','support':41},{'name':'沈伯洋','support':45}],
            'undecided':13,'undecided_reported':True,'nonvote':0,
            'response_mass_unreported':1,'reported_nonmajor_support_upper_pct':1,
            'reported_nonmajor_upper_basis':'Original survey: other listed candidates collectively below 1%',
        }
        race={
            'name':'台北市',
            'candidates':[{'name':'蔣萬安','party':'KMT'},{'name':'沈伯洋','party':'DPP'},
                          {'name':'第三方甲','party':None},{'name':'第三方乙','party':'OTHER'}],
            'draws':[[410000,390000,100000,100000]]*19+[[400000,400000,90000,110000]],
        }
        return [race],[row]

    def test_real_source_has_explicit_undisclosed_minor_candidate_limit(self):
        self.assertEqual(len(self.entries),2)
        self.assertEqual({r['county'] for r in self.entries},{'台北市','高雄市'})
        for r in self.entries:
            self.assertEqual(r['reported_nonmajor_support_upper_pct'],1)
            self.assertEqual(r['response_mass_unreported'],1)
            self.assertTrue(r['reported_nonmajor_upper_basis'])
            self.assertEqual(r['pollster_id'],'udn-poll-center')

    def test_diagnostic_preserves_public_forecast_and_label_difference(self):
        countries,polls=self.fixtures()
        before=copy.deepcopy(countries)
        report=build_nonmajor_response_audit(countries,polls,'2026-11-02T09:00:00+08:00')
        self.assertEqual(countries,before)
        self.assertFalse(report['formal_forecast_modified'])
        self.assertFalse(report['probabilities_calibrated'])
        self.assertTrue(report['metrics_not_interchangeable'])
        self.assertEqual(report['source_rows'],1)
        a=report['rows'][0]
        self.assertEqual(a['model_nonmajor_candidate_count'],2)
        self.assertEqual(a['model_nonmajor_mean_ballot_pct'],20)
        self.assertEqual(a['poll_nonmajor_support_upper_pct'],1)
        self.assertEqual(a['poll_undecided_reported_pct'],13)
        self.assertEqual(a['illustrative_difference_of_incomparable_metrics_pp'],19)
        self.assertEqual(a['survey_nonmajor_plus_all_undecided_pct'],14)
        self.assertFalse(a['is_ballot_prediction_constraint'])

    def test_no_generic_unreported_mass_is_misinterpreted_as_other_candidate_support(self):
        c,p=self.fixtures()
        p[0].pop('reported_nonmajor_support_upper_pct')
        self.assertEqual(build_nonmajor_response_audit(c,p,'2026-11-02T09:00:00+08:00')['rows'],[])

    def test_provenance_candidate_mismatch_future_data_fail_closed(self):
        c,p=self.fixtures()
        for key,value,message in [
            ('date','2026-11-03','Future'),
            ('reported_nonmajor_support_upper_pct',9,'Missing primary'),
            ('reported_nonmajor_upper_basis','', 'Missing primary'),
        ]:
            item=copy.deepcopy(p[0]);item[key]=value
            with self.assertRaisesRegex(ValueError,message):
                build_nonmajor_response_audit(c,[item],'2026-11-02T09:00:00+08:00')
        z=copy.deepcopy(p[0]);z['candidates'][0]['name']='錯誤候選人'
        with self.assertRaisesRegex(ValueError,'different candidate'):
            build_nonmajor_response_audit(c,[z],'2026-11-02T09:00:00+08:00')
        d=copy.deepcopy(c);d[0]['draws'][0][0]=0
        with self.assertRaisesRegex(ValueError,'draws are invalid'):
            build_nonmajor_response_audit(d,p,'2026-11-02T09:00:00+08:00')

    def test_no_eligible_poll_no_audit(self):
        c,p=self.fixtures()
        self.assertEqual(build_nonmajor_response_audit(c,[], '2026-11-02T09:00:00+08:00')['source_rows'],0)


if __name__=='__main__':
    unittest.main()
