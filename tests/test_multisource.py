"""Synthetic parser fixtures; not actual polling observations."""
import copy
import json
from datetime import date
from pathlib import Path
import unittest
from scripts import formosa, update_polls as updater
from model.polling import match_records
from model.roster import load_roster
from model.data import load_dataset

ROOT=Path(__file__).resolve().parents[1]
HTML='''<h1>2026新北市長選情民調</h1><p>戴立安，畢肯，年滿20歲；95%，±3.0%，電話訪問。
調查範圍：新北市。調查時間：2026年4月8日至4月10日。成功完訪1000人。
1、請問兩位適合擔任市長嗎？(1)甲甲70%(2)乙乙60%
2、甲甲和乙乙競選新北市長，您會投給誰？(1)國民黨甲甲40%(2)民進黨乙乙30%(3)不投票/投廢票10%(4)未明確回答20%
3、是否滿意？(1)滿意80%(2)未明確回答20%</p>'''
ENTRY={'url':'https://www.my-formosa.com.tw/DOC_100000.htm','title':'美麗島民調：2026新北市長選情民調'}


class MultisourceTests(unittest.TestCase):
    def test_original_question_only_with_distinct_nonvote(self):
        rows=formosa.parse(HTML.encode(),ENTRY,date(2026,9,8))
        self.assertEqual(len(rows),1)
        self.assertEqual([c['support'] for c in rows[0]['candidates']],[40,30])
        self.assertEqual((rows[0]['undecided'],rows[0]['nonvote']),(20,10))
        self.assertFalse(rows[0]['multiple_matchups'])

    def test_metadata_and_mass_fail_closed(self):
        for text in [HTML.replace('1000人','未知'),HTML.replace('乙乙30%','乙乙80%'),HTML.replace('畢肯','其他公司'),HTML.replace('2026年4','2027年4')]:
            with self.assertRaises(ValueError):formosa.parse(text.encode(),ENTRY,date(2026,9,8))

    def test_url_normalization_and_discovery(self):
        raw=f'<a href="/DOC_100000.htm">{ENTRY["title"]}</a><a href="/DOC_2.htm">國政滿意度</a>'.encode()
        self.assertEqual(len(formosa.discover(raw)),1)
        self.assertEqual(formosa.canonical_url(ENTRY['url']),'https://my-formosa.com.tw/DOC_100000.htm')
        with self.assertRaises(ValueError):formosa.canonical_url('https://my-formosa.com.tw.evil.test/DOC_1.htm')

    def test_reviewed_facts_survive_failed_fetch_without_fake_success(self):
        def fail(url):raise OSError('Source unavailable')
        cfg=json.loads((ROOT/'config.json').read_text(encoding='utf-8'))
        a=updater.update(cfg,{},get=fail,now='2026-09-08T20:00:00+00:00',include_formosa=True)
        self.assertEqual(len(a['records']),8)
        self.assertEqual(a['sources'][1]['validated_reports'],0)
        self.assertFalse(a['sources'][1]['index_ok'])
        self.assertEqual(a['status'],'degraded')
        b=updater.update(cfg,a,get=fail,now='2026-09-09T20:00:00+00:00',include_formosa=True)
        self.assertEqual(a['records'],b['records'])
        self.assertEqual(a['updated_at'],b['updated_at'])

    def test_nonvote_validation_and_reprinted_pollster_dedup(self):
        history=load_dataset(ROOT/'data/candidate-history-cec.json')
        roster=load_roster(ROOT/'data/registration-roster-2026.json',history)
        row=formosa.parse(HTML.encode(),ENTRY,date(2026,9,8))[0]
        race=next(r for r in roster['races'] if r['county']=='新北市')
        for c,target in zip(row['candidates'],race['candidates']):c['name']=target['name']
        accepted,_=match_records({'records':[row]},roster,'2026-09-08')
        self.assertEqual(len(accepted),1)
        self.assertEqual(accepted[0]['undecided'],20)
        self.assertEqual(accepted[0]['nonvote'],10)
        other={**copy.deepcopy(row),'id':'reprint','source':'Another publisher','source_url':'https://example.com/reprint'}
        self.assertEqual(len(match_records({'records':[row,other]},roster,'2026-09-08')[0]),1)
        row['nonvote']=90
        self.assertEqual(match_records({'records':[row]},roster,'2026-09-08')[0],[])


if __name__=='__main__':unittest.main()
