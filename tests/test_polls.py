import copy
import importlib.util
import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('updater', ROOT / 'scripts/update_polls.py')
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)
spec2 = importlib.util.spec_from_file_location('builder', ROOT / 'scripts/build.py')
b = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(b)

URL = 'https://www-asset.tvbs.com.tw/poll_center/2026/report.pdf'
ENTRY = {'url': URL, 'title': '2026台北市長選情民調'}
INDEX = f'<html><a href="{URL}">2026台北市長選情民調</a><a href="https://evil.example/x.pdf">2026台北市長選情民調</a></html>'.encode()
# Synthetic fixture, not a reproduced report or real poll.
REPORT = '''2026 台北市長選情民調
訪問時間 | 115 年 8 月 21 日至 26 日晚間
調查方法 | 市內電話隨機抽樣
有效樣本 | 901 位 20 歲以上台北市民
抽樣誤差 | 95%信心水準下，抽樣誤差為±3.3 個百分點
經費來源 | TVBS
表 1、是否滿意現任市長？
全體
滿意 70
不滿意 30
表 2、台北市長選舉，國民黨的甲甲和民進黨的乙乙，請問比較可能投票給哪一位？
全體
（100%）
甲甲 58
乙乙 30
未決定 13
支持度差距 ±28
Base：有投票意願市民
表 2-1、交叉表
全體 年齡
甲甲 58 60 55
乙乙 30 30 35
'''
CONFIG = {'baseline_cutoff': '2026-06-27', 'matchups': {'台北市': {'甲甲': 'blue', '乙乙': 'dpp'}}}
NOW = '2026-09-06T12:00:00+00:00'


class PollTests(unittest.TestCase):
    def parsed(self, text=REPORT):
        return u.parse_report(text, ENTRY, now=date(2026, 9, 6))

    def test_discover_restricts_source(self):
        self.assertEqual(u.discover(INDEX), [ENTRY])
        self.assertFalse(u.allowed_url('http://www.tvbs.com.tw/poll-center'))
        self.assertFalse(u.allowed_url('https://www.tvbs.com.tw.evil.example/a.pdf'))
        self.assertFalse(u.allowed_url('https://user:secret@www.tvbs.com.tw/a.pdf'))

    def test_broken_index_is_failure_not_empty_success(self):
        with self.assertRaises(u.InvalidReport):
            u.discover(b'<html>Unexpected login</html>')

    def test_question_only_not_cross_tab_or_satisfaction(self):
        records = self.parsed()
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertEqual([c['support'] for c in r['candidates']], [58, 30])
        self.assertEqual([c['bloc'] for c in r['candidates']], ['blue', 'dpp'])
        self.assertEqual(r['sample_n'], 901)
        self.assertEqual(r['date'], '2026-08-26')
        self.assertEqual(r['field_start'], '2026-08-21')
        self.assertIsNone(r['supervisor'])
        self.assertIsNone(r['population_size'])

    def test_rounding_and_trailing_pdf_punctuation(self):
        r = self.parsed(REPORT.replace('甲甲 58\n', '甲甲 58，\n'))[0]
        self.assertEqual(r['candidates'][0]['support'], 58)

    def test_pdf_compatibility_glyphs(self):
        r = self.parsed(REPORT.replace('市長', '市⾧'))[0]
        self.assertEqual(r['county'], '台北市')

    def test_county_from_header_not_narrative(self):
        r = self.parsed(REPORT.replace('表 1、', '新北市人士評論這次選舉。\n表 1、'))[0]
        self.assertEqual(r['county'], '台北市')

    def test_comparison_table_selects_dated_column_not_delta(self):
        report = REPORT.replace('全體\n（100%）\n甲甲 58\n乙乙 30\n未決定 13', '114/8/26 115/8/26\nN=901 N=901\n甲甲 55 58 +3%\n乙乙 32 30 -2%\n未決定 13 13')
        r = self.parsed(report)[0]
        self.assertEqual([c['support'] for c in r['candidates']], [58, 30])
        with self.assertRaises(u.InvalidReport):
            self.parsed(report.replace('115/8/26', '115/8/25'))

    def test_invalid_totals_rejected(self):
        with self.assertRaises(u.InvalidReport):
            self.parsed(REPORT.replace('乙乙 30\n', '乙乙 80\n'))

    def test_future_dates_rejected(self):
        with self.assertRaises(u.InvalidReport):
            self.parsed(REPORT.replace('115 年 8 月', '116 年 8 月'))

    def test_missing_metadata_rejected(self):
        with self.assertRaises(u.InvalidReport):
            self.parsed(REPORT.replace('有效樣本', '樣本不明'))

    def test_date_across_months(self):
        r = self.parsed(REPORT.replace('8 月 21 日至 26 日', '7 月 30 日至 8 月 2 日'))[0]
        self.assertEqual((r['field_start'], r['date']), ('2026-07-30', '2026-08-02'))

    def test_primary_and_hypothetical_questions_not_blended(self):
        with self.assertRaises(u.InvalidReport):
            self.parsed(REPORT.replace('台北市長選舉，', '台北市長初選，'))
        second = REPORT.split('表 2、')[1].split('表 2-1')[0]
        records = self.parsed(REPORT + '\n表 3、' + second.replace('甲甲', '丙丙'))
        self.assertEqual(len(records), 2)
        self.assertTrue(all(r['multiple_matchups'] for r in records))
        self.assertTrue(all(not u.classify(r, CONFIG)['model_eligible'] for r in records))

    def test_model_cutoff_and_matchup_guards(self):
        r = self.parsed()[0]
        self.assertTrue(u.classify(r, CONFIG)['model_eligible'])
        old = dict(r, date='2026-06-27')
        self.assertFalse(u.classify(old, CONFIG)['model_eligible'])
        wrong = copy.deepcopy(r)
        wrong['candidates'][0]['name'] = '別人'
        self.assertFalse(u.classify(wrong, CONFIG)['model_eligible'])
        unknown = copy.deepcopy(r)
        unknown['candidates'][0]['bloc'] = None
        self.assertFalse(u.classify(unknown, CONFIG)['model_eligible'])

    def test_poll_rows_deduplicate_and_latest_only(self):
        r = u.classify(self.parsed()[0], CONFIG)
        old = dict(r, id='old', date='2026-08-20')
        rows = u.model_rows([r, old, r])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['date'], '2026-08-26')
        self.assertEqual(rows[0]['undecided'], 13)

    def snapshot(self, previous=None, content=REPORT):
        return u.update(CONFIG, previous or {}, get=lambda url: INDEX if url == u.INDEX else content.encode(), pdf_text=lambda raw: raw.decode(), now=NOW)

    def test_idempotent_update_not_new_data_timestamp(self):
        first = self.snapshot()
        second = self.snapshot(first)
        self.assertEqual(first['records'], second['records'])
        self.assertEqual(first['history'], second['history'])
        self.assertEqual(first['updated_at'], second['updated_at'])
        self.assertEqual(first['status'], 'ok')

    def test_index_failure_retains_valid_records(self):
        first = self.snapshot()
        def fail(url):
            raise OSError('Timeout')
        second = u.update(CONFIG, first, get=fail, now='2026-09-07T12:00:00+00:00')
        self.assertEqual(first['records'], second['records'])
        self.assertEqual(first['polls'], second['polls'])
        self.assertEqual(second['status'], 'degraded')
        self.assertEqual(second['index_checked_at'], first['index_checked_at'])

    def test_bad_changed_report_never_overwrites_good(self):
        first = self.snapshot()
        second = self.snapshot(first, content='invalid report')
        self.assertEqual(first['records'], second['records'])
        self.assertEqual(first['updated_at'], second['updated_at'])
        self.assertEqual(len(second['failures']), 1)

    def test_valid_revision_replaces_not_duplicates(self):
        first = self.snapshot()
        second = self.snapshot(first, content=REPORT.replace('甲甲 58\n', '甲甲 57\n'))
        self.assertEqual(len(second['records']), 1)
        self.assertEqual(second['records'][0]['id'], first['records'][0]['id'])
        self.assertEqual(second['polls'][0]['blue'], 57)

    def test_atomic_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'polls.json'
            u.atomic_json(path, {'value': 1})
            self.assertEqual(json.loads(path.read_text()), {'value': 1})
            self.assertFalse(path.with_suffix('.json.tmp').exists())

    def test_publication_boundaries(self):
        c = {'publication_pause_start': '2026-11-17T00:00:00+08:00', 'publication_pause_end': '2026-11-29T00:00:00+08:00'}
        self.assertFalse(b.paused(c, datetime.fromisoformat('2026-11-16T23:59:59+08:00')))
        self.assertTrue(b.paused(c, datetime.fromisoformat('2026-11-17T00:00:00+08:00')))
        self.assertFalse(b.paused(c, datetime.fromisoformat('2026-11-29T00:00:00+08:00')))

    def test_paused_build_contains_no_old_poll_assets(self):
        config = {'publication_pause_start': '2026-11-17T00:00:00+08:00', 'publication_pause_end': '2026-11-29T00:00:00+08:00'}
        original_root = b.ROOT
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'data').mkdir()
            (root / 'dist/vendor').mkdir(parents=True)
            (root / 'dist/polls.json').write_text('old private data')
            (root / 'dist/vendor/old.js').write_text('old model')
            (root / 'config.json').write_text(json.dumps(config))
            (root / 'data/polls.json').write_text(json.dumps({'schema_version': 1, 'records': []}))
            try:
                b.ROOT = root
                b.build(datetime.fromisoformat('2026-11-17T00:00:00+08:00'))
                self.assertEqual({p.name for p in (root / 'dist').iterdir()}, {'index.html', '.nojekyll'})
            finally:
                b.ROOT = original_root


if __name__ == '__main__':
    unittest.main()
