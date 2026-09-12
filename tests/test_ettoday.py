import json
import unittest
from datetime import date
from pathlib import Path

from scripts import ettoday, update_polls as updater

ROOT = Path(__file__).resolve().parents[1]
ARTICLE = '''
<html><body>
<h1>民調出爐！柯志恩43.8％領先賴瑞隆</h1>
<p>2026高雄市長選舉持續受到關注。若明天就是高雄市長選舉，在國民黨柯志恩與民進黨賴瑞隆兩人對決情境下，柯志恩獲得43.8%支持、賴瑞隆43.5%，另有12.5%民眾尚未決定、表示不知道或沒有意見。</p>
<p>本次調查由東森民調雲股份有限公司執行，主持人謝惠玲。調查辦理時間為2026年8月22日至30日，調查範圍高雄市38個行政區，調查對象為設籍於高雄市且年滿20歲以上民眾。</p>
<p>以EDM及手機簡訊方式通知，進行封閉式網路問卷調查，樣本抽樣方法採分層比例抽樣。母體數為406,434。回收有效樣本數1,283份，在95%信心水準下，抽樣誤差為±2.74%。採用比例估計法（raking ratio estimation）。</p>
</body></html>
'''.encode()
ENTRY = {'url':'https://www.ettoday.net/news/20260911/9999999.htm','title':'民調出爐！柯志恩43.8％領先賴瑞隆','county':'高雄市'}
RSS = '''<?xml version="1.0"?><rss><channel>
<item><title>民調出爐！柯志恩43.8％領先賴瑞隆</title><link>https://www.ettoday.net/news/20260911/9999999.htm</link><description>2026高雄市長民調</description></item>
<item><title>一般政治新聞</title><link>https://www.ettoday.net/news/20260911/9999998.htm</link><description>非民調</description></item>
</channel></rss>'''.encode()


class ETtodayTests(unittest.TestCase):
    def test_feed_discovers_only_mayoral_poll(self):
        rows = ettoday.discover(RSS)
        self.assertEqual(rows, [ENTRY])
        with self.assertRaises(ettoday.InvalidETtodayReport):
            ettoday.canonical_url('https://www.ettoday.net.evil.example/news/1.htm')

    def test_article_parser_requires_complete_methodology(self):
        matchups = {'高雄市': {'柯志恩':'blue','賴瑞隆':'dpp'}}
        row = ettoday.parse(ARTICLE, ENTRY, date(2026,9,12), matchups)[0]
        self.assertEqual(row['pollster_id'], 'ettoday')
        self.assertEqual(row['method_class'], 'closed_online_panel')
        self.assertEqual(row['sample_n'], 1283)
        self.assertEqual(row['population_size'], 406434)
        self.assertEqual([c['support'] for c in row['candidates']], [43.8,43.5])
        self.assertEqual(row['undecided'], 12.5)
        bad = ARTICLE.replace(b'1,283', b'unknown')
        with self.assertRaises(ettoday.InvalidETtodayReport):
            ettoday.parse(bad, ENTRY, date(2026,9,12), matchups)

    def test_reviewed_seed_contains_latest_kaohsiung_wave(self):
        reviewed = json.loads((ROOT/'data/reviewed-ettoday-polls.json').read_text(encoding='utf-8'))
        rows = [ettoday.reviewed_record(x, date(2026,9,12)) for x in reviewed['reports']]
        self.assertEqual(len(rows), 2)
        latest = max(rows, key=lambda r:r['date'])
        self.assertEqual(latest['date'], '2026-08-30')
        self.assertEqual(latest['sample_n'], 1283)
        self.assertEqual(latest['verification_status'], 'reviewed_multi_source_methodology')

    def test_update_admits_latest_reviewed_ettoday_poll(self):
        cfg = json.loads((ROOT/'config.json').read_text(encoding='utf-8'))
        # Fail all network sources: reviewed ETtoday rows must survive and the August wave
        # must still be classifiable for the registered Kaohsiung matchup.
        def fail(url):
            raise OSError('offline source')
        result = updater.update(cfg, {}, get=fail, now='2026-09-12T06:00:00+00:00', include_ettoday=True)
        et = [r for r in result['records'] if r.get('pollster_id') == 'ettoday']
        self.assertEqual(len(et), 2)
        latest = max(et, key=lambda r:r['date'])
        self.assertTrue(latest['model_eligible'])
        self.assertEqual(result['latest_fieldwork_date'], '2026-08-30')
        self.assertTrue(any(s['name'] == 'ETtoday 民調雲' for s in result['sources']))
        self.assertEqual(next(x for x in result['source_review'] if x['name']=='ETtoday')['status'],
                         'integrated_with_reviewed_seed_and_live_discovery')

    def test_model_rows_deduplicate_by_pollster_id(self):
        cfg = {'baseline_cutoff':'2026-06-27','matchups':{'高雄市':{'柯志恩':'blue','賴瑞隆':'dpp'}}}
        base = ettoday.parse(ARTICLE, ENTRY, date(2026,9,12), cfg['matchups'])[0]
        base = updater.classify(base, cfg)
        reprint = dict(base, id='reprint', source='Syndicated publisher', source_url='https://example.com/reprint')
        rows = updater.model_rows([base, reprint])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['pollster_id'], 'ettoday')


if __name__ == '__main__':
    unittest.main()
