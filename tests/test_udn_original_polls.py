"""The UDN in-house polling center is a separate survey origin, not a repost.

Only the two reported major-candidate support percentages enter the joint
candidate likelihood. Do not invent a support split among unnamed candidates,
do not treat the 1pp unclassified remainder as undecided, and do not count
party/poll outcome expectations as voter support.
"""
import copy
import json
import sys
import unittest
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from enrich_reviewed_polls import enrich, reviewed_record
from model.polling import match_records
from model.roster import load_roster
from model.data import load_dataset

def read(path):
    return json.loads((ROOT/path).read_text(encoding='utf8'))


class UdnOriginalPollsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reviewed=read('data/reviewed-additional-polls.json')
        cls.config=read('config.json')
        cls.udn=[r for r in cls.reviewed['reports'] if r.get('pollster_id')=='udn-poll-center']
        cls.roster=load_roster(ROOT/'data/registration-roster-2026.json',
                                load_dataset(ROOT/'data/candidate-history-cec.json'))

    def test_two_original_udn_surveys_and_exact_source_identity(self):
        self.assertEqual(len(self.udn),2)
        verified={(r['county'],r['date']):(r['names'],r['supports'],r['undecided'],r['sample_n'],r['published_at'],r['source_url'])
                  for r in self.udn}
        self.assertEqual(verified[('台北市','2026-10-25')],
            (['蔣萬安','沈伯洋'],[41,45],13,1115,'2026-10-28',
             'https://udn.com/news/story/124652/9840910'))
        self.assertEqual(verified[('高雄市','2026-10-31')],
            (['柯志恩','賴瑞隆'],[33,40],26,1101,'2026-11-02',
             'https://udn.com/news/story/124652/9850777'))
        self.assertEqual({r['pollster'] for r in self.udn},{'聯合報系民意調查中心'})
        self.assertEqual({r['method_class'] for r in self.udn},{'dual_frame_cati'})
        self.assertTrue(all(r['response_mass_unreported']==1 for r in self.udn))
        self.assertTrue(all('未分類' in r['response_mass_note'] for r in self.udn))

    def test_reviewed_records_preserve_unknown_and_match_candidate_likelihood(self):
        rows=[reviewed_record(r,self.reviewed['reviewed_at'],date(2026,11,2)) for r in self.udn]
        self.assertTrue(all(r['response_mass_unreported']==1 for r in rows))
        self.assertTrue(all(r['undecided'] in (13,26) for r in rows))
        self.assertTrue(all(r['model_eligible'] is not True for r in rows if 'model_eligible' in r))
        accepted,audit=match_records({'records':rows},self.roster,'2026-11-02')
        self.assertEqual(len(accepted),2,audit)
        self.assertTrue(all(r['partial_ballot'] for r in accepted))
        self.assertEqual({r['county'] for r in accepted},{'台北市','高雄市'})
        self.assertEqual({r['pollster_id'] for r in accepted},{'udn-poll-center'})

    def test_future_udn_publication_cannot_contaminate_september_fixed_asof(self):
        feed={'schema_version':1,'checked_at':'2026-09-12T11:05:00+00:00',
              'updated_at':'2026-09-12T00:00:00+00:00',
              'records':[],'polls':[],'sources':[],'history':[]}
        earlier=enrich(feed,self.config,self.reviewed,date(2026,9,12))
        self.assertEqual(len([r for r in earlier['records'] if r.get('pollster_id')=='udn-poll-center']),0)
        self.assertEqual(len([r for r in earlier['records'] if r.get('pollster_id')=='shanshui']),3)
        self.assertEqual(len([r for r in earlier['records'] if r.get('pollster_id')=='pearson-data']),2)
        self.assertFalse(any(r.get('date','') > '2026-09-12' for r in earlier['records']))
        self.assertFalse(any(s['name']=='聯合報系民意調查中心' for s in earlier['sources']))

    def test_no_imputed_undecided_and_reject_bad_response_total(self):
        src=self.udn[0]
        broken=copy.deepcopy(src)
        broken['supports']=[41,57]
        with self.assertRaisesRegex(ValueError,'response mass'):
            reviewed_record(broken,self.reviewed['reviewed_at'],date(2026,11,2))
        broken=copy.deepcopy(src)
        broken.pop('response_mass_note')
        with self.assertRaisesRegex(ValueError,'unclassified'):
            reviewed_record(broken,self.reviewed['reviewed_at'],date(2026,11,2))

    def test_original_udn_and_media_reprint_are_not_duplicate_independent_polls(self):
        a=reviewed_record(self.udn[0],self.reviewed['reviewed_at'],date(2026,11,2))
        b=copy.deepcopy(a)
        b['id']='reprinted-article'
        b['source']='UDN story syndicated by another publication'
        b['source_url']='https://news.example.test/reprint'
        a,b=match_records({'records':[a,b]},self.roster,'2026-11-02')
        self.assertEqual(len(a),1)
        self.assertTrue(b[0]['included'])
        self.assertFalse(b[1]['included'])
        self.assertIn('重複',b[1]['reason'])

    def test_seed_enrichment_removes_old_udn_exclusion_and_is_idempotent(self):
        feed={'schema_version':1,'checked_at':'2026-11-02T00:00:00+00:00',
              'updated_at':'2026-10-31T00:00:00+00:00','records':[],
              'sources':[],'source_review':[{'name':'聯合報','status':'publisher_not_pollster',
              'note':'old exclusion','url':'https://udn.com/'}],
              'polls':[],'history':[],'coverage_note':'existing'}
        out=enrich(feed,self.config,self.reviewed,date(2026,11,2))
        rows=[r for r in out['records'] if r.get('pollster_id')=='udn-poll-center']
        self.assertEqual(len(rows),2)
        self.assertEqual({r['response_mass_unreported'] for r in rows},{1})
        self.assertFalse(any(r.get('model_eligible') for r in rows))
        self.assertEqual(sum(s['name']=='聯合報系民意調查中心' for s in out['sources']),1)
        self.assertFalse(any(s['name']=='聯合報' for s in out['source_review']))
        after=enrich(out,self.config,self.reviewed,date(2026,11,2))
        self.assertEqual(out['records'],after['records'])
        self.assertEqual(out['source_review'],after['source_review'])


if __name__=='__main__':unittest.main()
