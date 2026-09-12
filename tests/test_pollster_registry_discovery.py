import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.discover_poll_sources import (
    discover_from_html,
    discovery_pollsters,
    merge_discovery,
    registry_map,
)


class PollsterRegistryDiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.registry = json.loads((ROOT / 'data/pollster-registry.json').read_text(encoding='utf-8'))
        cls.config = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
        cls.pollsters = registry_map(cls.registry)

    def test_registry_has_unique_governed_pollsters(self):
        self.assertEqual(self.registry['schema_version'], 1)
        self.assertIn('tvbs', self.pollsters)
        self.assertIn('ettoday', self.pollsters)
        self.assertIn('shanshui', self.pollsters)
        self.assertIn('pearson-data', self.pollsters)
        self.assertEqual(self.pollsters['shanshui']['discovery']['mode'], 'html_index_queue')
        self.assertEqual(self.pollsters['pearson-data']['discovery']['mode'], 'html_index_queue')
        self.assertEqual(self.pollsters['apollo']['model_uncertainty'], 'not_admitted')

    def test_zmedia_discovery_finds_mayoral_pages_not_issue_noise(self):
        pollster = self.pollsters['shanshui']
        raw = '''<html><head><meta charset="utf-8"></head><body>
          <a href="/Document/Detail/41952">震傳媒民調（一）／李四川絕對優勢不再？ 新北5％內決勝負！</a>
          <a href="/Document/Detail/50001">震傳媒民調（二）／55.2%北市民支持蔣萬安連任 45.3%綠支持者不看好沈伯洋</a>
          <a href="/Document/Detail/50002">震傳媒民調（三）／54.5%高市民對賴總統施政表示滿意</a>
        </body></html>'''.encode('utf-8')
        rows = discover_from_html(raw, pollster['discovery']['index_urls'][0], pollster, self.config['matchups'])
        self.assertEqual({r['county'] for r in rows}, {'新北市', '台北市'})
        self.assertTrue(any(r['url'].endswith('/50001') for r in rows))
        self.assertFalse(any(r['url'].endswith('/50002') for r in rows))

    def test_bigmedia_discovery_requires_vote_intention_signal(self):
        pollster = self.pollsters['pearson-data']
        raw = '''<html><head><meta charset="utf-8"></head><body>
          <a href="/article/1786278801544">2026《鉅聞民調》高雄市長選舉／選情膠著！柯志恩46.14%緊咬賴瑞隆47.78%</a>
          <a href="/article/9990000000001">2026《鉅聞民調》台北市長選舉／蔣萬安52%對沈伯洋39%　選情進入決勝期</a>
          <a href="/article/9990000000002">2026《鉅聞民調》高雄市長選舉／賴清德滿意度未過半　成賴瑞隆困局</a>
        </body></html>'''.encode('utf-8')
        rows = discover_from_html(raw, pollster['discovery']['index_urls'][0], pollster, self.config['matchups'])
        self.assertEqual({r['url'].rsplit('/', 1)[-1] for r in rows}, {'1786278801544', '9990000000001'})

    def base_feed(self):
        return {
            'schema_version': 1,
            'status': 'ok',
            'coverage_note': 'existing coverage',
            'sources': [
                {'name': '震傳媒／山水民調', 'url': 'https://www.zmedia.com.tw/Document/PoolDetail/41952', 'reviewed_reports': 2, 'validated_reports': 0, 'status': 'reviewed_seed_only'},
                {'name': '鉅聞天下／皮爾森數據', 'url': 'https://www.bigmedia.com.tw/article/1786278801544', 'reviewed_reports': 2, 'validated_reports': 0, 'status': 'reviewed_seed_only'},
            ],
            'records': [
                {
                    'id': 'known-z', 'county': '新北市', 'source': '震傳媒／山水民調', 'pollster_id': 'shanshui',
                    'source_url': 'https://www.zmedia.com.tw/Document/PoolDetail/41952',
                    'verification_urls': ['https://www.zmedia.com.tw/Document/Detail/41952'],
                },
                {'id': 'known-b', 'county': '高雄市', 'source': '鉅聞天下／皮爾森數據', 'pollster_id': 'pearson-data', 'source_url': 'https://www.bigmedia.com.tw/article/1786278801544'},
            ],
            'polls': [],
            'source_review': [],
            'discovery_queue': [
                {'source': 'ETtoday', 'title': 'keep me', 'url': 'https://www.ettoday.net/news/1', 'status': 'discovered_unverified'}
            ],
            'failures': [],
            'history': [],
        }

    def test_merge_discovery_queues_unknown_and_never_changes_records(self):
        feed = self.base_feed()
        before_records = copy.deepcopy(feed['records'])
        shanshui = self.pollsters['shanshui']
        pearson = self.pollsters['pearson-data']
        pages = {
            shanshui['discovery']['index_urls'][0]: '''<html><head><meta charset="utf-8"></head><body><a href="/Document/Detail/41952">震傳媒民調（一）／李四川絕對優勢不再？ 新北5％內決勝負！</a></body></html>'''.encode('utf-8'),
            shanshui['discovery']['index_urls'][1]: '''<html><head><meta charset="utf-8"></head><body><a href="/Document/Detail/50001">震傳媒民調（二）／55.2%北市民支持蔣萬安連任 45.3%綠支持者不看好沈伯洋</a></body></html>'''.encode('utf-8'),
            pearson['discovery']['index_urls'][0]: '''<html><head><meta charset="utf-8"></head><body><a href="/article/1786278801544">2026《鉅聞民調》高雄市長選舉／選情膠著！柯志恩46.14%緊咬賴瑞隆47.78%</a>
              <a href="/article/9990000000001">2026《鉅聞民調》台北市長選舉／蔣萬安52%對沈伯洋39%　選情進入決勝期</a></body></html>'''.encode('utf-8'),
        }
        out = merge_discovery(feed, self.registry, self.config, pages, '2026-09-12T10:30:00+00:00')
        self.assertEqual(out['records'], before_records)
        queued = {q['url']: q for q in out['discovery_queue']}
        self.assertIn('https://www.ettoday.net/news/1', queued)
        self.assertIn('https://www.zmedia.com.tw/Document/Detail/50001', queued)
        self.assertIn('https://www.bigmedia.com.tw/article/9990000000001', queued)
        self.assertNotIn('https://www.zmedia.com.tw/Document/Detail/41952', queued)
        self.assertNotIn('https://www.bigmedia.com.tw/article/1786278801544', queued)
        self.assertEqual(queued['https://www.zmedia.com.tw/Document/Detail/50001']['status'], 'discovered_unverified')
        sources = {s['name']: s for s in out['sources']}
        self.assertTrue(sources['震傳媒／山水民調']['auto_discovery'])
        self.assertEqual(sources['震傳媒／山水民調']['auto_pending'], 1)
        self.assertEqual(sources['鉅聞天下／皮爾森數據']['auto_pending'], 1)
        self.assertEqual(out['pollster_registry']['registered_pollsters'], 7)
        self.assertIn('未通過完整校驗前不入模', out['coverage_note'])

    def test_discovery_failure_preserves_records_and_degrades_source(self):
        feed = self.base_feed()
        shanshui = self.pollsters['shanshui']
        pearson = self.pollsters['pearson-data']
        pages = {
            shanshui['discovery']['index_urls'][0]: b'',
            shanshui['discovery']['index_urls'][1]: b'',
            pearson['discovery']['index_urls'][0]: '''<html><head><meta charset="utf-8"></head><body><a href="/article/1786278801544">2026《鉅聞民調》高雄市長選舉／選情膠著！柯志恩46.14%緊咬賴瑞隆47.78%</a></body></html>'''.encode('utf-8'),
        }
        out = merge_discovery(feed, self.registry, self.config, pages, '2026-09-12T10:30:00+00:00')
        self.assertEqual(out['records'], feed['records'])
        source = next(s for s in out['sources'] if s['name'] == '震傳媒／山水民調')
        self.assertEqual(source['auto_discovery_status'], 'degraded')
        self.assertEqual(out['status'], 'degraded')
        self.assertTrue(any(f['source'] == '震傳媒／山水民調 discovery' for f in out['failures']))


if __name__ == '__main__':
    unittest.main()
