"""Regression fixtures for safe discovery-to-model promotion."""
import unittest
from datetime import date

import numpy as np

from scripts.promote_poll_sources import UnverifiedPoll, parse_article, promote
from model.polling import match_records, observation_matrices
from model.joint import SETTINGS

ROSTER = {'races': [
    {'county': '台北市', 'race_id': 'taipei', 'candidates': [
        {'name': name, 'candidate_id': 'tp' + str(i)} for i, name in
        enumerate(['蔣萬安', '沈伯洋', '郭璽', '蕭文乾', '唐新民', '林志成'])]},
    {'county': '新北市', 'race_id': 'newtaipei', 'candidates': [
        {'name': name, 'candidate_id': 'nt' + str(i)} for i, name in
        enumerate(['李四川', '蘇巧慧', '蘇輝湟'])]},
]}

SHAN_TP = """2026/10/22 震傳媒今（22）日公布最新時事議題民調。
針對年底台北市長選戰，在6名市長參選人中，42.8%台北市民表示支持民進黨籍參選人沈伯洋、39.0%支持現任市長蔣萬安，在投票率部分，90.1%表示會投票。
本次民調是由震傳媒出資委託山水民意研究股份有限公司執行，調查時間是2026年10月18日至10月19日，針對設籍台北市、年滿20歲民眾為調查對象，透過CATI系統電話訪問。成功完訪1,074人，在95%信心水準下，抽樣誤差約±2.99個百分點。"""
SHAN_NT = """2026/09/23 震傳媒今（23）日公布最新時事議題民調。
針對年底新北市長選舉，在三位登記參選人中，38.2%新北市民支持民進黨籍參選人蘇巧慧，37.1%支持國民黨籍參選人李四川，雙方差距1.1%，至於無黨籍參選人蘇輝湟則獲得2.6%新北市民的支持。若與4月相比有所變化。
本次民調是由震傳媒出資委託山水民意研究股份有限公司執行，調查時間是2026年9月20日至9月21日，針對設籍新北市、年滿20歲民眾為調查對象，透過CATI系統電話訪問。成功完訪1,076人，在95%信心水準下，抽樣誤差約±2.99個百分點。"""
PEARSON_NT = """2026-10-15 01:00 《鉅聞天下新聞網》公布新北市長最新民調顯示，國民黨李四川以45.74%支持度與民進黨蘇巧慧45.18%已經打平，與今年7月調查相較，兩人的支持有所變化。表示「尚未決定投給哪位候選人」的比例，也由上次調查的3.40%上升到6.96%。
本次調查是由《鉅聞天下》新聞網委託，皮爾森數據負責執行，經費來源為《鉅聞天下》新聞網。針對新北市年滿20歲以上之網路人口，從2026年9月28日至2026年10月3日，當中有效樣本為1,066份，在95%信心水準下，抽樣誤差為正負3.00%以內。調查採資料管理平台（DMP）網路抽樣。"""

def page(text):
    return ('<!doctype html><html><head><meta charset="utf-8"></head><body><main>'
            + text + '</main></body></html>').encode('utf-8')

ENTRIES = [
    {'pollster_id': 'shanshui', 'county': '台北市', 'source': '震傳媒／山水民調',
     'url': 'https://www.zmedia.com.tw/Document/Detail/44789', 'title': '42.8%北市民支持沈伯洋'},
    {'pollster_id': 'shanshui', 'county': '新北市', 'source': '震傳媒／山水民調',
     'url': 'https://www.zmedia.com.tw/Document/Detail/44348', 'title': '38.2%新北市民支持蘇巧慧'},
    {'pollster_id': 'pearson-data', 'county': '新北市', 'source': '鉅聞天下／皮爾森數據',
     'url': 'https://www.bigmedia.com.tw/article/1791969638295', 'title': '新北市長選情膠著'},
]

class PollPromotionTests(unittest.TestCase):
    def test_three_recent_articles_keep_unknown_response_mass(self):
        for entry, raw, expected in zip(ENTRIES, [SHAN_TP, SHAN_NT, PEARSON_NT], [18.2, 22.1, 2.12]):
            row = parse_article(page(raw), entry, ROSTER, date(2026, 10, 28))
            self.assertAlmostEqual(row['response_mass_unreported'], expected, places=2)
            self.assertEqual(row['undecided_reported'], entry['pollster_id'] == 'pearson-data')
            self.assertEqual(row['verification_status'], 'validated_partial_response')

    def test_non_vote_intention_and_wrong_region_are_rejected(self):
        with self.assertRaises(UnverifiedPoll):
            parse_article(page(SHAN_TP), {**ENTRIES[0], 'title': '台北市長看好度'}, ROSTER, date(2026, 10, 28))
        with self.assertRaises(UnverifiedPoll):
            parse_article(page(SHAN_TP), {**ENTRIES[0], 'county': '新北市'}, ROSTER, date(2026, 10, 28))

    def test_queue_promotes_verified_but_retains_rejected(self):
        other = {**ENTRIES[0], 'url': 'https://www.zmedia.com.tw/Document/Detail/44790', 'title': '市長看好度'}
        pages = {x['url']: page(t) for x, t in zip(ENTRIES, [SHAN_TP, SHAN_NT, PEARSON_NT])}
        pages[other['url']] = page(SHAN_TP)
        registry = {'pollsters': [
            {'pollster_id': 'shanshui', 'discovery': {'mode': 'html_index_queue', 'index_urls': ['https://www.zmedia.com.tw/Document/Pool']}},
            {'pollster_id': 'pearson-data', 'discovery': {'mode': 'html_index_queue', 'index_urls': ['https://www.bigmedia.com.tw/article']}},
        ]}
        config = {'baseline_cutoff': '2026-06-27', 'matchups': {}}
        feed = {'records': [], 'polls': [], 'discovery_queue': ENTRIES + [other], 'sources': [], 'history': []}
        result, accepted = promote(feed, config, ROSTER, registry, lambda url, hosts: pages[url], '2026-10-28T00:00:00+00:00')
        self.assertEqual(len(accepted), 3)
        self.assertEqual(len(result['discovery_queue']), 1)
        self.assertEqual(result['latest_fieldwork_date'], '2026-10-19')
        self.assertTrue(all(not x['model_eligible'] for x in result['records']))
        model, audit = match_records(result, ROSTER, '2026-10-28')
        self.assertEqual(len(model), 3)
        self.assertTrue(all(x['included'] for x in audit))
        self.assertEqual(len(result['polls']), 0)

    def test_unreported_mass_inflates_measurement_uncertainty(self):
        rec = parse_article(page(PEARSON_NT), ENTRIES[2], ROSTER, date(2026, 10, 28))
        model, _ = match_records({'records': [rec]}, ROSTER, '2026-10-28')
        candidates = [{'candidate_id': c['candidate_id']} for r in ROSTER['races'] for c in r['candidates']]
        noisy = observation_matrices(model, candidates, SETTINGS)[2]
        complete = [{**model[0], 'response_mass_unreported': 0, 'method_class': 'landline_cati'}]
        plain = observation_matrices(complete, candidates, SETTINGS)[2]
        self.assertGreater(float(np.trace(noisy)), float(np.trace(plain)))


if __name__ == '__main__':
    unittest.main()
