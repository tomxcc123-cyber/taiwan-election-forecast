"""Import structured TVBS facts without publishing uploaded reports or executing documents."""
import argparse
import csv
import hashlib
import io
import json
import sys
import unicodedata
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model.data import digest, load_dataset


def canonical(value):
    return unicodedata.normalize('NFKC', value).replace('臺', '台')


def import_data(downloads):
    archives = ['2014九合一.zip', '2018九合一.zip', '2022九合一选举.zip']
    pdfs, sources = {}, []
    for name in archives:
        raw = (downloads/name).read_bytes()
        sources.append({'file': name, 'sha256': hashlib.sha256(raw).hexdigest()})
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for item in archive.infolist():
                if item.filename.endswith('.pdf'):
                    pdfs[Path(item.filename).name] = hashlib.sha256(archive.read(item)).hexdigest()
    path = downloads/'TVBS_九合一历史民调_建模CSV包.zip'
    sources.append({'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    with zipfile.ZipFile(path) as archive:
        tables = {Path(n).stem: list(csv.DictReader(io.StringIO(archive.read(n).decode('utf-8-sig'))))
                  for n in archive.namelist() if n.endswith('.csv')}
    # The workbook is a second representation of the same facts, never extra samples.
    import openpyxl
    workbook_path = downloads/'TVBS_2014_2018_2022九合一历史民调_整理建模版.xlsx'
    workbook = openpyxl.load_workbook(workbook_path, read_only=True, data_only=True)
    values = list(workbook['候选人支持度'].values)
    header_index = next(i for i,r in enumerate(values) if r and r[0]=='poll_id')
    workbook_rows = [r for r in values[header_index+1:] if r and r[0]]
    expected = {(r['poll_id'],r['candidate']):(float(r['raw_support']),float(r['undecided']))
                for r in tables['candidate_support_long']}
    actual = {(r[0],r[9]):(float(r[11]),float(r[12])) for r in workbook_rows}
    if len(workbook_rows)!=len(expected) or actual!=expected:
        raise ValueError('Workbook and CSV candidate facts differ')
    workbook.close()
    sources.append({'file':workbook_path.name,'sha256':hashlib.sha256(workbook_path.read_bytes()).hexdigest(),
                    'comparison':'All 292 candidate support and undecided values agree with CSV; not counted twice.'})
    history = load_dataset(ROOT/'data/candidate-history-cec.json')
    races = {(r['year'], canonical(r['county'])): r for r in history['races']}
    candidate_rows = {}
    for row in tables['candidate_support_long']:
        candidate_rows.setdefault(row['poll_id'], []).append(row)
    records, seen, occupied = [], set(), []
    for wave in tables['poll_waves']:
        if wave['poll_id'] in seen:
            raise ValueError('Duplicate wave ID')
        seen.add(wave['poll_id'])
        rows = candidate_rows.pop(wave['poll_id'])
        reasons = []
        year, county = int(wave['election_year']), canonical(wave['city'])
        race = races[year, county]
        names = {canonical(c['name']): c for c in race['candidates']}
        candidates = []
        for row in rows:
            for key in ['election_year', 'city', 'wave_date', 'undecided', 'quality_tier', 'provenance']:
                if row[key] != wave[key]:
                    raise ValueError('Wave and long-table conflict: '+wave['poll_id'])
            name = canonical(row['candidate'])
            candidates.append({'name': row['candidate'], 'support': float(row['raw_support']),
                               'candidate_id': names.get(name, {}).get('candidate_id')})
        if len(candidates) != int(wave['candidate_count']) or len({c['name'] for c in candidates}) != len(candidates):
            raise ValueError('Candidate count mismatch')
        if wave['provenance'] != 'document_current': reasons.append('後續報告趨勢回填，原波次方法未核對')
        if wave['matchup_type'] != 'listed_field': reasons.append('假設候選組合')
        if wave['quality_tier'] != 'A': reasons.append('未達核心資料品質層級')
        if not all(c['candidate_id'] for c in candidates): reasons.append('部分人選與最終名單不符或字形待核對')
        n = int(wave['support_base_n']) if wave['support_base_n'] else None
        if n is None or n < 100: reasons.append('支持度題目子樣本數缺失；不以總樣本代替')
        start, end = wave['wave_field_start'], wave['wave_field_end']
        if not start or start > end or end >= race['election_date']: reasons.append('訪問區間不完整或非選前')
        if wave['election_date'] != race['election_date']: reasons.append('選舉日期不符')
        support = sum(c['support'] for c in candidates)
        undecided, residual = float(wave['undecided']), float(wave['other_unlisted'])
        if (not all(0 <= c['support'] <= 100 for c in candidates) or not 0 <= undecided <= 100
                or not 0 <= residual <= 100 or support < 20 or abs(support+undecided+residual-100) > 2):
            reasons.append('支持比例或總和不符')
        if residual > 2: reasons.append('未列選項差額超過捨入容許值')
        if wave['source_file'] not in pdfs: reasons.append('缺少對應原始PDF')
        if not reasons:
            if any(c == county and y == year and start <= e and end >= s for y, c, s, e in occupied):
                reasons.append('同機構同縣市訪問區間重疊')
            else: occupied.append((year, county, start, end))
        records.append({'id': wave['poll_id'], 'year': year, 'county': race['county'], 'race_id': race['race_id'],
            'election_date': race['election_date'], 'date': end, 'field_start': start or None,
            'field_mid': (date.fromisoformat(start).toordinal()+date.fromisoformat(end).toordinal())/2 if start else None,
            'source': 'TVBS', 'pollster_id': 'tvbs', 'source_file': wave['source_file'],
            'source_sha256': pdfs.get(wave['source_file']), 'published_at': None,
            'quality_tier': wave['quality_tier'], 'provenance': wave['provenance'],
            'matchup_type': wave['matchup_type'], 'sample_n': n, 'document_sample_n': int(wave['source_doc_sample_n']) if wave['source_doc_sample_n'] else None,
            'turnout_screen': wave['turnout_screen'] == 'True', 'population': wave['base'],
            'method': wave['survey_method'], 'undecided': undecided, 'unlisted_or_rounding': residual,
            'candidates': candidates, 'candidate_ids': [c['candidate_id'] for c in candidates],
            'supports': [c['support'] for c in candidates], 'partial_ballot': len(candidates) < len(race['candidates']),
            'eligible': not reasons, 'reasons': reasons, 'source_note': wave['review_flag']})
    if candidate_rows: raise ValueError('Orphan candidate rows')
    payload = {'schema_version': 1, 'cec_data_hash': history['data_hash'], 'sources': sources,
        'source_report_count': len(pdfs), 'records': records,
        'audit': {'waves': len(records), 'candidate_rows': sum(len(r['candidates']) for r in records),
                  'eligible_waves': sum(r['eligible'] for r in records),
                  'excluded_reasons': dict(Counter(reason for r in records for reason in r['reasons'])),
                  'by_year': [{ 'year': y, 'waves': sum(r['year']==y for r in records),
                      'eligible': sum(r['year']==y and r['eligible'] for r in records)} for y in [2014,2018,2022]]},
        'verification': 'CSV relational, date, mass, exact roster and PDF-presence/hash checks; report spot checks, not independent verification of every extracted cell.',
        'availability': 'Original publication dates unknown. Fieldwork-cutoff retrospective validation only; trend carry-forwards excluded. XLSX is a parallel presentation, not extra samples.'}
    payload['data_hash'] = digest(payload)
    return payload


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--downloads', type=Path, default=Path('C:/Users/HP/Downloads'))
    args = parser.parse_args()
    payload = import_data(args.downloads)
    (ROOT/'data/historical-polls-tvbs.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps(payload['audit'], ensure_ascii=False))
