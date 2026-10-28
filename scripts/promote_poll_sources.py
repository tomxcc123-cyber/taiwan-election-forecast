"""Safely promote first-party discovery items into candidate-model poll records.

Only supported vote-intention article formats are promoted. Unreported response
mass is *unknown*, never silently assigned to undecided/non-voting categories.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from pathlib import Path
from lxml import html
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.discover_poll_sources import fetch, stamp
from scripts.update_polls import atomic_json, classify, model_rows

FEED_PATH = ROOT / 'data/polls.json'
CONFIG_PATH = ROOT / 'config.json'
REGISTRY_PATH = ROOT / 'data/pollster-registry.json'


class UnverifiedPoll(ValueError):
    pass


def squish(value):
    return re.sub(r'\s+', '', value or '').replace('臺', '台')


def number(text, pattern, label):
    hit = re.search(pattern, text)
    if not hit:
        raise UnverifiedPoll(f'{label}: original article did not disclose a parseable value')
    return float(hit.group(1).replace(',', ''))


def fieldwork(text):
    found = re.search(r'(?:調查時間是|從)(20\d{2})年(\d{1,2})月(\d{1,2})日至(?:(20\d{2})年)?(\d{1,2})月(\d{1,2})日', text)
    if not found:
        raise UnverifiedPoll('Missing explicit fieldwork period')
    y, m, d, y2, m2, d2 = found.groups()
    return date(int(y), int(m), int(d)), date(int(y2 or y), int(m2), int(d2))


def parse_article(raw, entry, roster, today):
    pollster = entry.get('pollster_id')
    if pollster not in {'shanshui', 'pearson-data'}:
        raise UnverifiedPoll('Pollster has no approved automatic parser')
    if not isinstance(raw, bytes) or len(raw) < 200:
        raise UnverifiedPoll('Empty or incomplete publisher article')
    doc = html.fromstring(raw, parser=html.HTMLParser(encoding='utf-8'))
    content = squish(doc.text_content())
    title = squish(entry.get('title', ''))
    if any(x in title for x in ('看好度', '票流向', '外溢助攻', '滿意度', '政黨認同')):
        raise UnverifiedPoll('Article is not a general vote-intention poll')
    county = entry['county']
    race = next((r for r in roster['races'] if r['county'] == county), None)
    if race is None:
        raise UnverifiedPoll('County does not exist in registered roster')
    candidates = []
    if pollster == 'shanshui':
        if '山水民意研究' not in content or 'CATI' not in content or '成功完訪' not in content:
            raise UnverifiedPoll('Missing first-party pollster, CATI method or sample evidence')
        marker = content.find('針對年底')
        if marker == -1:
            raise UnverifiedPoll('No vote-intention lead paragraph')
        lead = content[marker:content.find('。', marker)]
        if county not in lead:
            raise UnverifiedPoll('Headline-inferred county conflicts with the vote-intention paragraph')
        for c in race['candidates']:
            name = squish(c['name'])
            before = re.search(r'(\d{1,2}(?:\.\d+)?)%[^%，。]{0,70}?' + re.escape(name), lead)
            after = re.search(re.escape(name) + r'[^%，。]{0,15}?(?:獲得|支持度為)(\d{1,2}(?:\.\d+)?)%', lead)
            if before or after:
                candidates.append({'name': c['name'], 'support': float((before or after).group(1)), 'bloc': c.get('bloc', 'other')})
        sample = int(number(content, r'成功完訪([\d,]+)人', 'Sample size'))
        moe = number(content, r'抽樣誤差(?:約)?[±＋-]?(\d+(?:\.\d+)?)', 'Sampling error')
        method = 'CATI，住宅電話，系統抽樣與尾2碼隨機'
        method_class = 'landline_cati'
        population = f'設籍{county}，年滿20歲民眾'
        funding = '震傳媒'
        undecided, undecided_reported = 0.0, False
        publisher = '震傳媒'
        pollster_name = '山水民意研究股份有限公司'
    else:
        if county != '新北市' or '皮爾森數據' not in content or 'DMP' not in content or '有效樣本' not in content:
            raise UnverifiedPoll('Missing first-party pollster, DMP method or location evidence')
        marker = content.find('最新民調顯示')
        end = content.find('與今年7月', marker)
        if marker == -1 or end == -1 or end - marker > 250:
            raise UnverifiedPoll('No unambiguous current vote-intention lead')
        lead = content[marker:end]
        for c in race['candidates']:
            name = squish(c['name'])
            match = re.search(re.escape(name) + r'[^%，。]{0,18}?(\d{1,2}(?:\.\d+)?)%', lead)
            if match:
                candidates.append({'name': c['name'], 'support': float(match.group(1)), 'bloc': c.get('bloc', 'other')})
        sample = int(number(content, r'有效樣本為([\d,]+)份', 'Sample size'))
        moe = number(content, r'抽樣誤差為正負(\d+(?:\.\d+)?)%', 'Sampling error')
        undecided = number(content, r'尚未決定投給哪位候選人[^。]{0,150}?上升到(\d+(?:\.\d+)?)%', 'Undecided share')
        undecided_reported = True
        method = 'DMP網路調查，性別／年齡／居住地分層與事後加權'
        method_class = 'online_dmp_panel'
        population = '新北市年滿20歲之網路人口'
        funding = '鉅聞天下新聞網'
        publisher = '鉅聞天下新聞網'
        pollster_name = '皮爾森數據'
    if len(candidates) < 2 or len(candidates) > len(race['candidates']):
        raise UnverifiedPoll('Fewer than two registered candidates have current support figures')
    start, end = fieldwork(content)
    if not (date(2023, 1, 1) <= start <= end <= today):
        raise UnverifiedPoll('Invalid or future survey dates')
    date_string = re.search(r'2026[-/](\d{1,2})[-/](\d{1,2})', content)
    if date_string:
        published = date(2026, int(date_string.group(1)), int(date_string.group(2)))
        if published < end or published > today:
            raise UnverifiedPoll('Publication date conflicts with survey period')
    else:
        raise UnverifiedPoll('Missing publication date')
    if sample < 100 or not 0 < moe < 20:
        raise UnverifiedPoll('Invalid sample size or sampling error')
    supported = round(sum(c['support'] for c in candidates), 4)
    unreported = round(100 - supported - undecided, 4)
    if not (20 <= supported <= 100) or not (0 <= undecided <= 100) or not (0 <= unreported <= 30):
        raise UnverifiedPoll('Incomplete or internally inconsistent response mass')
    source_url = entry['url']
    identity = f"{pollster}|{county}|{end.isoformat()}|" + ','.join(sorted(c['name'] for c in candidates))
    record = {
        'id': hashlib.sha256(identity.encode()).hexdigest()[:24],
        'county': county, 'source': entry['source'], 'pollster_id': pollster,
        'pollster': pollster_name, 'publisher': publisher, 'source_url': source_url,
        'report_title': entry.get('title', ''), 'published_at': published.isoformat(),
        'field_start': start.isoformat(), 'date': end.isoformat(), 'sample_n': sample,
        'population': population, 'method': method, 'method_class': method_class,
        'margin_of_error': moe, 'confidence_level': 95, 'funding': funding,
        'candidates': candidates, 'undecided': undecided, 'undecided_reported': undecided_reported,
        'nonvote': 0, 'nonvote_reported': False,
        'response_mass_unreported': unreported,
        'response_mass_note': 'Only listed candidate shares and explicitly identified response categories; remainder is unclassified, NOT assumed undecided or abstention.',
        'multiple_matchups': False, 'question_number': 1,
        'ingestion': 'automatic_first_party_partial', 'verification_status': 'validated_partial_response',
        'retrieved_at': today.isoformat() + 'T00:00:00+00:00',
        'sample_note': 'Publisher sample; partial response categories. Relative candidate support only.',
    }
    return record


def promote(feed, config, roster, registry, get, checked, today=None):
    today = today or date.fromisoformat(checked[:10])
    out = json.loads(json.dumps(feed, ensure_ascii=False))
    permitted = {p['pollster_id']: p for p in registry['pollsters'] if p.get('discovery', {}).get('mode') == 'html_index_queue'}
    records = list(out.get('records', []))
    processed, remaining = [], []
    for item in out.get('discovery_queue', []):
        pollster = item.get('pollster_id')
        source = permitted.get(pollster)
        if not source:
            remaining.append(item)
            continue
        url = item['url']
        if not url.startswith('https://') or url.split('/')[2] not in {x.split('/')[2] for x in source['discovery']['index_urls']}:
            remaining.append({**item, 'last_validation_error': 'Publisher URL outside approved host'})
            continue
        try:
            raw = get(url, {url.split('/')[2]})
            row = parse_article(raw, item, roster, today)
            row['retrieved_at'] = checked
            if any(x.get('source_url') == row['source_url'] for x in records):
                processed.append(row)
                continue
            records.append(row)
            processed.append(row)
        except (OSError, ValueError, KeyError, TypeError) as error:
            remaining.append({**item, 'last_validation_error': str(error)[:160], 'last_validation_at': checked})
    out['records'] = sorted((classify(r, config) for r in records), key=lambda r: (r['date'], r['id']), reverse=True)
    out['polls'] = model_rows(out['records'])
    out['discovery_queue'] = remaining
    out['latest_fieldwork_date'] = max((r['date'] for r in out['records']), default=None)
    if processed:
        out['updated_at'] = checked
        history = list(out.get('history', []))
        for row in processed:
            history.insert(0, {'date': checked, 'county': row['county'], 'source_url': row['source_url'], 'kind': 'verified_partial_poll_promoted'})
        out['history'] = history[:100]
    for src in out.get('sources', []):
        if src.get('registry_pollster_id') in permitted:
            src['auto_pending'] = sum(1 for x in remaining if x.get('pollster_id') == src['registry_pollster_id'])
            src['auto_promoted'] = sum(1 for x in out['records'] if x.get('pollster_id') == src['registry_pollster_id'] and x.get('ingestion') == 'automatic_first_party_partial')
    return out, processed


def main():
    feed = json.loads(FEED_PATH.read_text(encoding='utf-8'))
    config = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))
    roster = json.loads((ROOT / 'data/registration-roster-2026.json').read_text(encoding='utf-8'))
    registry = json.loads(REGISTRY_PATH.read_text(encoding='utf-8'))
    checked = stamp()
    result, accepted = promote(feed, config, roster, registry, fetch, checked)
    atomic_json(FEED_PATH, result)
    print(json.dumps({'auto_promoted': len(accepted), 'pending': len(result['discovery_queue']), 'latest_fieldwork': result['latest_fieldwork_date']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
