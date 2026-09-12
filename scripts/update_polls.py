"""Fetch official/reviewed poll reports; publish facts only, never infer missing results."""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import os
import sys
import re
import time
import unicodedata
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pdfplumber
from lxml import html

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ettoday, formosa

INDEX = 'https://www.tvbs.com.tw/poll-center'
ALLOWED_HOSTS = {'www.tvbs.com.tw', 'www-asset.tvbs.com.tw'} | formosa.HOSTS | ettoday.HOSTS
COUNTIES = ['台北市','新北市','桃園市','台中市','台南市','高雄市','基隆市','新竹市',
            '新竹縣','苗栗縣','彰化縣','南投縣','雲林縣','嘉義市','嘉義縣','屏東縣',
            '宜蘭縣','花蓮縣','台東縣','澎湖縣','金門縣','連江縣']
PARSER_VERSION = 2


class InvalidReport(ValueError):
    pass


def stamp():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def canonical(value):
    return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value)).replace('臺', '台').replace('啓', '啟')


def allowed_url(url):
    p = urlparse(url)
    return p.scheme == 'https' and p.hostname in ALLOWED_HOSTS and not p.username and not p.password


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed_url(newurl):
            raise InvalidReport('Redirect outside official source allowlist')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url):
    if not allowed_url(url):
        raise InvalidReport('URL outside official source allowlist')
    error = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'TaiwanElectionPollMonitor/1.0 (public-source research)',
                'Cache-Control': 'no-cache',
            })
            with urllib.request.build_opener(SafeRedirect()).open(req, timeout=35) as response:
                raw = response.read(12_000_001)
                if len(raw) > 12_000_000:
                    raise InvalidReport('Report exceeds download limit')
                return raw
        except (OSError, InvalidReport) as exc:
            error = exc
            if attempt < 2:
                time.sleep(2 ** attempt)
    raise error


def discover(raw):
    doc = html.fromstring(raw.decode('utf-8'))
    links = {}
    all_pdfs = 0
    for a in doc.xpath('//a[@href]'):
        url = a.get('href', '')
        if not url.lower().endswith('.pdf') or not allowed_url(url):
            continue
        all_pdfs += 1
        title = canonical(a.text_content())
        if '2026' not in title or not any(x in title for x in ('市長', '縣長')):
            continue
        if not any(x in title for x in ('選情', '人選')):
            continue
        links[url] = {'url': url, 'title': title[:100]}
    if not all_pdfs:
        raise InvalidReport('Official index structure changed: no report links')
    return list(links.values())[:30]


def extract_pdf(raw):
    if not raw.startswith(b'%PDF-'):
        raise InvalidReport('Source did not return a PDF')
    with pdfplumber.open(io.BytesIO(raw)) as doc:
        if len(doc.pages) > 40:
            raise InvalidReport('Unexpected report length')
        return '\n\n'.join(p.extract_text() or '' for p in doc.pages)


def roc_dates(text):
    m = re.search(r'訪問時間\s*[|｜]\s*(\d{2,4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日\s*至\s*(?:(\d{1,2})\s*月\s*)?(\d{1,2})\s*日', text)
    if not m:
        raise InvalidReport('Missing or unsupported fieldwork dates')
    y, mo, day, end_mo, end_day = m.groups()
    y = int(y) + (1911 if int(y) < 1911 else 0)
    return date(y, int(mo), int(day)).isoformat(), date(y, int(end_mo or mo), int(end_day)).isoformat()


def party_for(name, question):
    q = canonical(question)
    for pattern, bloc in [
        (r'國民黨(?:和|與|、)民眾黨(?:共同)?支持的' + re.escape(name), 'blue'),
        (r'國民黨(?:的|推出的|支持的)?' + re.escape(name), 'blue'),
        (r'民進黨(?:的|推出的|支持的)?' + re.escape(name), 'dpp'),
        (r'民眾黨(?:的|推出的|支持的)?' + re.escape(name), 'third'),
        (r'無黨籍(?:的)?' + re.escape(name), 'other'),
    ]:
        if re.search(pattern, q):
            return bloc
    return None


def parse_report(text, entry, now=None):
    now = now or date.today()
    text = unicodedata.normalize('NFKC', text)
    header = text[:900]
    compact = canonical(header.split('訪問時間', 1)[0])
    counties = [c for c in COUNTIES if c in compact]
    if len(counties) != 1 or '2026' not in compact:
        raise InvalidReport('County or election year is ambiguous')
    start, end = roc_dates(header)
    if not (date(2025, 1, 1) <= date.fromisoformat(start) <= date.fromisoformat(end) <= now):
        raise InvalidReport('Invalid or future fieldwork dates')
    sample = re.search(r'有效樣本\s*[|｜]\s*([\d,]+)\s*位\s*([^\n]+)', header)
    method = re.search(r'調查方法\s*[|｜]\s*([^\n]+)', header)
    moe = re.search(r'抽樣誤差\s*[|｜].*?[±正負]\s*(\d+(?:\.\d+)?)', header)
    funding = re.search(r'經費來源\s*[|｜]\s*([^\n]+)', header)
    if not all((sample, method, moe, funding)):
        raise InvalidReport('Missing sampling metadata')
    n = int(sample[1].replace(',', ''))
    if not 100 <= n <= 100000 or not 0 < float(moe[1]) < 15:
        raise InvalidReport('Implausible sample size or margin of error')
    blocks = re.split(r'(?m)^表\s*(\d+)\s*[、，,]', text)
    questions = []
    for i in range(1, len(blocks), 2):
        number, block = blocks[i], blocks[i + 1]
        table = re.split(r'(?m)^表\s*\d+\s*[-－]', block)[0]
        is_vote_question = bool(re.search(r'投票給|支持哪|支持那', canonical(table.split('Base', 1)[0])))
        column = 0
        column_count = 1
        if '全體' in table:
            question, values = table.split('全體', 1)
        else:
            dates = re.search(r'(?m)^\s*(\d{2,4}/\d{1,2}/\d{1,2}(?:\s+\d{2,4}/\d{1,2}/\d{1,2})*)\s*$', table)
            if not dates:
                if is_vote_question:
                    raise InvalidReport('Vote-intention question has an unsupported table header')
                continue
            question, values = table[:dates.start()], table[dates.end():]
            labels = dates[1].split()
            iso_dates = []
            for label in labels:
                y, m, d = map(int, label.split('/'))
                iso_dates.append(date(y + (1911 if y < 1911 else 0), m, d).isoformat())
            if iso_dates.count(end) != 1:
                raise InvalidReport('Comparison table lacks a unique current fieldwork column')
            column, column_count = iso_dates.index(end), len(iso_dates)
        question = unicodedata.normalize('NFKC', question)
        if not re.search(r'投票給|支持哪|支持那', canonical(question)) or not re.search(r'市長|縣長', canonical(question)):
            continue
        if any(x in question for x in ('初選', '滿意', '喜歡')):
            continue
        values = values.split('Base', 1)[0]
        candidates, undecided = [], None
        for line in values.splitlines():
            match = re.fullmatch(r'\s*([\u3400-\u9fff]{2,8})\s+((?:\d+(?:\.\d+)?[%,]?\s*)+)(?:\s+[+-]\d+(?:\.\d+)?%)?\s*', line)
            if not match:
                continue
            numbers = re.findall(r'\d+(?:\.\d+)?', match[2])
            if len(numbers) != column_count:
                raise InvalidReport('Comparison row does not match dated columns')
            name, support = canonical(match[1]), float(numbers[column])
            if name in ('未決定', '未表態', '不知道'):
                if undecided is not None:
                    raise InvalidReport('Duplicate undecided category')
                undecided = support
            else:
                if name not in canonical(question):
                    raise InvalidReport('Unexpected category in vote-intention table')
                candidates.append({'name': name, 'support': support, 'bloc': party_for(name, question)})
        if not 2 <= len(candidates) <= 5 or undecided is None:
            raise InvalidReport('Vote-intention totals cannot be parsed safely')
        if len({c['name'] for c in candidates}) != len(candidates):
            raise InvalidReport('Duplicate candidates')
        total = sum(c['support'] for c in candidates) + undecided
        if abs(total - 100) > 2 or any(not 0 <= c['support'] <= 100 for c in candidates) or not 0 <= undecided <= 100:
            raise InvalidReport('Percentages do not total 100 within rounding tolerance')
        questions.append({'question_number': int(number), 'candidates': candidates, 'undecided': undecided})
    if not questions:
        raise InvalidReport('No supported vote-intention questionnaire table')
    records = []
    for question in questions:
        identity = '|'.join([entry['url'], end, str(question['question_number']),
                             ','.join(sorted(c['name'] for c in question['candidates']))])
        records.append({
            'id': hashlib.sha256(identity.encode()).hexdigest()[:24],
            'county': counties[0], 'source': 'TVBS 民意調查中心', 'pollster_id': 'tvbs',
            'publisher': 'TVBS', 'source_url': entry['url'], 'report_title': entry['title'],
            'field_start': start, 'date': end, 'sample_n': n,
            'population': sample[2].strip(), 'method': method[1].strip(), 'method_class': 'telephone_cati',
            'margin_of_error': float(moe[1]), 'confidence_level': 95, 'funding': funding[1].strip(),
            'supervisor': None, 'population_size': None,
            'sample_note': '報告總樣本；投票意向子樣本量未另列',
            'multiple_matchups': len(questions) > 1, **question,
        })
    return records


def classify(record, config):
    r = copy.deepcopy(record)
    r['model_eligible'] = False
    if r.get('nonvote', 0):
        r['exclusion_reason'] = '舊版三方模型不支援獨立不投票類別；候選人模型另行檢查'
    elif r['date'] <= config['baseline_cutoff']:
        r['exclusion_reason'] = '基線日期以前的資料，僅供查閱，避免重複加權'
    elif r['multiple_matchups'] or '可能人選' in r['report_title']:
        r['exclusion_reason'] = '同份報告含多組對陣，不自動合併'
    else:
        expected = config['matchups'].get(r['county'], {})
        names = {c['name'] for c in r['candidates']}
        if not expected or names != set(expected):
            r['exclusion_reason'] = '候選人組合與模型基線不一致'
        elif any(c['bloc'] != expected[c['name']] for c in r['candidates']):
            r['exclusion_reason'] = '題目中的陣營歸屬與模型不一致或不明'
        else:
            r.update(model_eligible=True, exclusion_reason=None)
    return r


def model_rows(records):
    latest = {}
    for r in sorted(records, key=lambda p: (p['date'], p['id'])):
        if r['model_eligible']:
            latest[(r.get('pollster_id', r['source']), r['county'])] = r
    rows = []
    for r in latest.values():
        row = {k: r[k] for k in ('id', 'county', 'source', 'date', 'sample_n', 'undecided')}
        row['pollster_id'] = r.get('pollster_id', r['source'])
        row['method_class'] = r.get('method_class')
        row.update(blue=0, dpp=0, third=0, other=0)
        for c in r['candidates']:
            row[c['bloc']] += c['support']
        rows.append(row)
    return sorted(rows, key=lambda r: (r['date'], r['county']))


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)


def _replace_review(items, name, value):
    out = [x for x in items if x.get('name') != name]
    out.append(value)
    return out


def update(config, previous, get=fetch, pdf_text=extract_pdf, now=None,
           include_formosa=False, include_ettoday=False):
    checked = now or stamp()
    today = datetime.fromisoformat(checked).date()
    records = {r['id']: r for r in previous.get('records', [])}
    reports = copy.deepcopy(previous.get('reports', {}))
    failures, changed = [], []
    extra_sources = []
    source_review = []
    discovery_queue = []

    if include_formosa:
        reviewed = json.loads((ROOT/'data/reviewed-poll-sources.json').read_text(encoding='utf-8'))
        source_review = reviewed['source_review']
        seed_entries = []
        for entry in reviewed['reports']:
            seed_entries.append({'url':entry['url'],'title':entry['title']})
            if date.fromisoformat(reviewed['reviewed_at'][:10]) > today:
                continue
            for q in entry['questions']:
                candidates=[{'name':n,'support':v,'bloc':b} for n,v,b in zip(q['names'],q['supports'],q['blocs'])]
                row=formosa.record(entry,entry['county'],entry['field_start'],entry['date'],entry['sample_n'],q['number'],candidates,q['undecided'],q['nonvote'],len(entry['questions'])>1,entry['method'],today)
                row.update(retrieved_at=reviewed['reviewed_at'],ingestion='reviewed_original_page_facts')
                if row['id'] not in records:
                    records[row['id']]=row
                    changed.append({'date':checked,'county':row['county'],'source_url':row['source_url'],'kind':'reviewed_report_added'})
        formosa_entries={e['url']:e for e in seed_entries}
        formosa_index_ok=False
        try:
            for entry in formosa.discover(get(formosa.INDEX)):
                formosa_entries[entry['url']]=entry
            formosa_index_ok=True
        except Exception as exc:
            failures.append({'source':'美麗島','url':formosa.INDEX,'message':str(exc)[:180]})
        formosa_good=0
        if formosa_index_ok:
            for entry in formosa_entries.values():
                try:
                    raw=get(entry['url']);digest=hashlib.sha256(raw).hexdigest()
                    parsed=formosa.parse(raw,entry,today)
                    old=reports.get(entry['url'],{})
                    if old.get('sha256')!=digest or old.get('parser_version')!=formosa.VERSION:
                        records={k:r for k,r in records.items() if r['source_url']!=entry['url']}
                        for row in parsed:
                            row.update(retrieved_at=checked,report_sha256=digest,ingestion='automatic_original_html')
                            records[row['id']]=row
                        changed.append({'date':checked,'county':parsed[0]['county'],'source_url':entry['url'],'kind':'report_updated'})
                    reports[entry['url']]={'sha256':digest,'parser_version':formosa.VERSION,'status':'valid','checked_at':checked}
                    formosa_good+=1
                except Exception as exc:
                    failures.append({'source':'美麗島','url':entry['url'],'message':str(exc)[:180]})
        extra_sources.append({'name':formosa.SOURCE,'url':formosa.INDEX,'discovered':len(formosa_entries),
            'validated_reports':formosa_good,'index_ok':formosa_index_ok,
            'status':'checked' if formosa_index_ok else 'unavailable',
            'note':'本輪自動擷取通過數不含先前核對的存檔；失敗保留最後有效資料。'})

    if include_ettoday:
        reviewed_et = json.loads((ROOT/'data/reviewed-ettoday-polls.json').read_text(encoding='utf-8'))
        seed_count = 0
        if date.fromisoformat(reviewed_et['reviewed_at'][:10]) <= today:
            for entry in reviewed_et['reports']:
                try:
                    row = ettoday.reviewed_record(entry, today)
                    row['retrieved_at'] = reviewed_et['reviewed_at']
                    seed_count += 1
                    if row['id'] not in records:
                        records[row['id']] = row
                        changed.append({'date':checked,'county':row['county'],'source_url':row['source_url'],'kind':'reviewed_ettoday_added'})
                except Exception as exc:
                    failures.append({'source':'ETtoday reviewed seed','url':entry.get('verification_urls',[''])[0],'message':str(exc)[:180]})
        et_entries = []
        et_index_ok = False
        try:
            et_entries = ettoday.discover(get(ettoday.INDEX))
            et_index_ok = True
        except Exception as exc:
            failures.append({'source':'ETtoday','url':ettoday.INDEX,'message':str(exc)[:180]})
        et_good = 0
        if et_index_ok:
            for entry in et_entries:
                try:
                    raw = get(entry['url']); digest = hashlib.sha256(raw).hexdigest()
                    parsed = ettoday.parse(raw, entry, today, config['matchups'])
                    old = reports.get(entry['url'], {})
                    for row in parsed:
                        row.update(retrieved_at=checked, report_sha256=digest, ingestion='automatic_original_html')
                        records[row['id']] = row
                    reports[entry['url']]={'sha256':digest,'parser_version':ettoday.VERSION,'status':'valid','checked_at':checked}
                    if old.get('sha256') != digest or old.get('parser_version') != ettoday.VERSION:
                        changed.append({'date':checked,'county':parsed[0]['county'],'source_url':entry['url'],'kind':'ettoday_original_verified'})
                    et_good += 1
                except Exception as exc:
                    message = str(exc)[:180]
                    failures.append({'source':'ETtoday','url':entry['url'],'message':message})
                    discovery_queue.append({'source':'ETtoday','title':entry.get('title'),'county':entry.get('county'),
                                            'url':entry.get('url'),'status':'discovered_unverified','reason':message})
        source_review = _replace_review(source_review, 'ETtoday', {
            'name':'ETtoday',
            'status':'integrated_with_reviewed_seed_and_live_discovery',
            'note':'已接入ETtoday民調雲封閉式會員網路調查。原文可自動解析時優先使用；來源暫時不可用時保留已核對波次，未通過解析的新文章列入待核驗佇列。',
            'url':'https://www.ettoday.net/'
        })
        extra_sources.append({'name':ettoday.SOURCE,'url':ettoday.INDEX,'discovered':len(et_entries),
            'validated_reports':et_good,'reviewed_reports':seed_count,'index_ok':et_index_ok,
            'status':'checked' if et_index_ok else 'reviewed_seed_only',
            'method_class':'closed_online_panel',
            'note':'封閉式會員網路問卷另保留method_class；目前使用通用非TVBS民調不確定性，尚未宣稱已估計ETtoday house effect。'})

    entries = []
    index_ok = False
    try:
        entries = discover(get(INDEX))
        index_ok = True
    except Exception as exc:
        failures.append({'source': 'TVBS', 'url': INDEX, 'message': str(exc)[:180]})
    good = 0
    for entry in entries:
        url = entry['url']
        try:
            raw = get(url)
            digest = hashlib.sha256(raw).hexdigest()
            old = reports.get(url, {})
            if digest == old.get('sha256') and old.get('parser_version') == PARSER_VERSION:
                if old.get('status') == 'valid':
                    good += 1
                else:
                    failures.append({'source': 'TVBS', 'url': url, 'message': old['message']})
                continue
            parsed = parse_report(pdf_text(raw), entry, now=today)
            records = {k: r for k, r in records.items() if r['source_url'] != url}
            for r in parsed:
                r.update(retrieved_at=checked, report_sha256=digest)
                records[r['id']] = r
            reports[url] = {'sha256': digest, 'parser_version': PARSER_VERSION, 'status': 'valid', 'checked_at': checked}
            changed.append({'date': checked, 'county': parsed[0]['county'], 'source_url': url, 'kind': 'report_updated' if old else 'report_added'})
            good += 1
        except Exception as exc:
            message = str(exc)[:180]
            failures.append({'source': 'TVBS', 'url': url, 'message': message})

    classified = sorted((classify(r, config) for r in records.values()), key=lambda r: (r['date'], r['id']), reverse=True)
    latest = max((r['date'] for r in classified), default=None)
    status = 'ok' if index_ok and not failures else ('degraded' if classified else 'unavailable')
    source_list = [{'name': 'TVBS 民意調查中心', 'url': INDEX, 'discovered': len(entries),
                    'validated_reports': good, 'index_ok':index_ok}] + extra_sources
    if include_ettoday:
        coverage = ('來源包括TVBS、美麗島與ETtoday民調雲。自動來源失敗時保留最後核對資料；'
                    'ETtoday新文章若尚未通過完整方法與候選人解析，會列為已發現／待核驗，而不是靜默遺漏。')
    elif include_formosa:
        coverage = '來源包括TVBS原始報告與美麗島原始問卷。部分為已核對存檔；自動抓取失敗會明示，不代表所有機構或所有縣市都有近期民調。'
    else:
        coverage = '目前自動來源為 TVBS 原始報告，不代表所有機構或所有縣市都有近期民調。'
    return {
        'schema_version': 1, 'checked_at': checked,
        'last_success_at': checked if index_ok and not failures else previous.get('last_success_at'),
        'index_checked_at': checked if index_ok else previous.get('index_checked_at'),
        'updated_at': checked if changed else previous.get('updated_at'),
        'latest_fieldwork_date': latest, 'status': status, 'baseline_cutoff': config['baseline_cutoff'],
        'sources': source_list, 'source_review':source_review,
        'discovery_queue': discovery_queue,
        'records': classified, 'polls': model_rows(classified), 'failures': failures,
        'reports': reports, 'history': (changed + previous.get('history', []))[:100],
        'coverage_note': coverage,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--offline', action='store_true', help='Use cached source payloads; never claim a live source check')
    args = parser.parse_args()
    config = json.loads((ROOT / 'config.json').read_text(encoding='utf-8'))
    target = ROOT / 'data/polls.json'
    previous = json.loads(target.read_text(encoding='utf-8')) if target.exists() else {}
    cache = ROOT / '.cache'
    cache.mkdir(exist_ok=True)

    def get(url):
        path = cache / (hashlib.sha256(url.encode()).hexdigest() + '.bin')
        if args.offline:
            return path.read_bytes()
        raw = fetch(url)
        path.write_bytes(raw)
        return raw

    result = update(config, previous, get=get, include_formosa=True, include_ettoday=True)
    if args.offline:
        print(json.dumps({'offline_test': True, 'records': len(result['records']), 'failures': len(result['failures'])}))
        return
    atomic_json(target, result)
    print(json.dumps({k: result[k] for k in ('status', 'checked_at', 'latest_fieldwork_date')}))
    print(f"Validated questions: {len(result['records'])}; model inputs: {len(result['polls'])}; skipped/failed reports: {len(result['failures'])}; discovery queue: {len(result['discovery_queue'])}")


if __name__ == '__main__':
    main()
