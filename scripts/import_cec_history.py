"""Import user-supplied CEC result workbooks; never execute embedded content.

Optional import dependency: xlrd==2.0.2. Deployment uses the audited JSON only.
"""
import argparse
import hashlib
import io
import json
import re
import sys
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model.data import digest, load_dataset

ARCHIVES = {
    '1275d73551f2c0caf202e803b1766057.zip': 2022,
    'f75e94cad2958f8764f9d090e72b5567.zip': 2018,
    '63615098f5afa8ec53159c4a86fc01d3.zip': 2022,
    '4d5371ae79267a6fd9bb78199c636cfb.zip': 2014,
    '05cc7b904c7a30cc7c88d5b10898c98e.zip': 2022,
    '45ca615ee3ff7b12238c79783524bd8f.zip': 2014,
    'a0222f6529a3ff2192a1a04f209eaac3 (1).zip': 2018,
}
PARTIES = {'中國國民黨': 'KMT', '民主進步黨': 'DPP', '台灣民眾黨': 'TPP'}
DATES = {2014: '2014-11-29', 2018: '2018-11-24', 2022: '2022-11-26'}
NAME_REPAIRS = {
    (2014, '新北市', '游錫\ue808'): ('游錫堃', 'https://web.cec.gov.tw/api/file/d059e326-0770-4a21-8a0f-c3f95b70bcf3.pdf'),
    (2014, '花蓮縣', '傅\ue82f萁'): ('傅崐萁', 'https://web.cec.gov.tw/api/file/f0cbcee1-18b6-4ce5-a94d-bdf0650e8f8a.pdf'),
    (2014, '花蓮縣', '\ue929師鵬'): ('黄師鵬', 'https://web.cec.gov.tw/api/file/f0cbcee1-18b6-4ce5-a94d-bdf0650e8f8a.pdf'),
    (2022, '宜蘭縣', '江\ue018淵'): ('江聰淵', 'https://db.cec.gov.tw/ElecTable/Election/ElecTickets?areaCode=00&cityCode=002&dataLevel=D&dataType=tickets&deptCode=000&legisId=00&liCode=0000&prvCode=10&subjectId=D2&themeId=86cecbfc1f34decd0f283331496c1a75&typeId=ELC'),
}


def members(raw, prefix='', depth=0):
    if depth > 3:
        raise ValueError('Archive nesting limit')
    with ZipFile(io.BytesIO(raw)) as archive:
        if sum(i.file_size for i in archive.infolist()) > 300_000_000:
            raise ValueError('Archive size limit')
        for item in archive.infolist():
            if item.is_dir():
                continue
            name = item.filename
            if not item.flag_bits & 0x800:
                name = name.encode('cp437').decode('cp950')
            data = archive.read(item)
            path = prefix + '/' + name
            if name.lower().endswith('.zip'):
                yield from members(data, path, depth+1)
            else:
                yield path, data


def integer(value):
    number = float(str(value).replace(',', '').strip())
    if not number.is_integer() or number < 0:
        raise ValueError(f'Invalid count: {value!r}')
    return int(number)


def check_counts(values, candidate_count):
    votes = values[:candidate_count]
    a, b, c, d, e, f, g = values[candidate_count:]
    if sum(votes) != a or a+b != c or c+d != e or c > g:
        raise ValueError(f'Vote conservation failed: {values}, candidates={candidate_count}')
    return e+f-g


def parse_sheet(sheet, special=False):
    if special:
        names = [str(sheet.cell_value(4, j)).strip() for j in range(1, 6)]
        parties = [str(sheet.cell_value(5, j)).strip() for j in range(1, 6)]
        total = [integer(sheet.cell_value(6, j)) for j in range(1, 13)]
        districts = [[integer(sheet.cell_value(i, j)) for j in range(1, 13)] for i in (7, 8)]
        for row in [total, *districts]:
            check_counts(row, 5)
        if total != [sum(col) for col in zip(*districts)]:
            raise ValueError('Chiayi district totals mismatch')
        return names, parties, total, {'level': 'county_and_district', 'districts': 2, 'rows': [7, 8, 9]}
    headers = sheet.row_values(1)
    end = next(i for i, cell in enumerate(headers) if '有效票數' in str(cell))
    names, parties = [], []
    for i, j in enumerate(range(3, end), 1):
        parts = str(sheet.cell_value(2, j)).split('\n')
        if integer(parts[0]) != i or len(parts) < 3:
            raise ValueError('Invalid candidate header')
        names.append(parts[1].strip())
        parties.append(parts[2].strip())
    width = end+7-3
    total, district_sum = [0]*width, [0]*width
    expected, precincts, seen, district_count = None, [], set(), 0
    inventory_warnings = []
    def close_district():
        if expected is not None and district_sum != expected:
            raise ValueError('District/precinct totals mismatch')
    for i in range(3, sheet.nrows):
        row = sheet.row_values(i)
        station = str(row[2]).strip()
        area = str(row[0]).strip()
        if not station and area:
            close_district()
            expected = [integer(v) for v in row[3:end+7]]
            check_counts(expected, len(names))
            district_sum = [0]*width
            district_count += 1
        elif station:
            number = integer(station)
            if number in seen or expected is None:
                raise ValueError('Duplicate precinct or missing district')
            seen.add(number)
            values = [integer(v) for v in row[3:end+7]]
            inventory_delta = check_counts(values, len(names))
            if inventory_delta:
                inventory_warnings.append({'row': i+1, 'precinct': number, 'issued_plus_unused_minus_electorate': inventory_delta})
            total = [a+b for a, b in zip(total, values)]
            district_sum = [a+b for a, b in zip(district_sum, values)]
            precincts.append(i+1)
    close_district()
    if not precincts:
        raise ValueError('No precincts found')
    check_counts(total, len(names))
    return names, parties, total, {'level': 'precinct_and_district', 'precincts': len(precincts),
                                 'districts': district_count, 'first_precinct_row': min(precincts),
                                 'last_precinct_row': max(precincts), 'inventory_warnings': inventory_warnings}


def convert(folder):
    import xlrd
    old = load_dataset(ROOT/'data/candidate-history.json')
    county_meta = {r['county']: r for r in old['races']}
    races, archives = [], []
    for filename, year in ARCHIVES.items():
        raw = (folder/filename).read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        archives.append({'filename': filename, 'sha256': sha, 'year': year})
        for path, content in members(raw, filename):
            special = filename.startswith('1275') and '/表2-' in path
            if not path.endswith('.xls') or not (special or '縣表3-1-' in path):
                continue
            sheet = xlrd.open_workbook(file_contents=content).sheet_by_index(0)
            try:
                names, parties, total, checks = parse_sheet(sheet, special)
            except ValueError as error:
                raise ValueError(f'{path}: {error}') from error
            county = '嘉義市' if special else re.search(r'\(([^)]+)\)', path.rsplit('/', 1)[-1]).group(1).replace('臺', '台')
            if not special and str(year-1911)+'年' not in str(sheet.cell_value(0, 0)):
                raise ValueError('Workbook year mismatch')
            meta = county_meta[county]
            rid = f"local-executive-{year}-{meta['county_id']}"
            n, candidates, party_shares = len(names), [], {}
            for j, (name, party_name) in enumerate(zip(names, parties)):
                raw_name = name
                repair = NAME_REPAIRS.get((year, county, name))
                if repair:
                    name = repair[0]
                party = PARTIES.get(party_name)
                if party is None and party_name not in {'', '無', '無黨籍'}:
                    party = 'party-'+digest(party_name)[:12]
                share = total[j]/total[n]*100
                party_shares[party or 'IND'] = party_shares.get(party or 'IND', 0)+share
                candidates.append({'candidate_id': rid+'-'+digest(name)[:12], 'name': name,
                    'party': party, 'party_name': party_name or '無黨籍', 'legacy_bloc': party if party in PARTIES.values() else 'IND' if party is None else 'OTHER',
                    'votes': total[j], 'share_pct': share, 'winner': total[j] == max(total[:n]),
                    'ballot_number': j+1, 'identity_verified': False})
                if repair:
                    candidates[-1]['name_repair'] = {'raw': raw_name, 'canonical': name, 'source_url': repair[1]}
            races.append({'race_id': rid, 'county_id': meta['county_id'], 'county': county,
                'region': meta['region'], 'year': year, 'office': 'local_executive',
                'election_date': '2022-12-18' if special else DATES[year], 'available_at': None,
                'boundary_version': 'cec-county-2014-2022', 'roster_verified': False, 'source_verified': False,
                'counts_verified': True, 'party_shares_pct': party_shares, 'candidates': candidates,
                'valid_votes': total[n], 'invalid_votes': total[n+1], 'ballots_cast': total[n+2],
                'electorate': total[n+6], 'turnout_pct': total[n+2]/total[n+6]*100,
                'source_locator': path, 'source': {'archive_sha256': sha,
                    'table_sha256': hashlib.sha256(content).hexdigest(), 'sheet': sheet.name,
                    'kind': 'user_supplied_cec_result_workbook', 'checks': checks}})
    races.sort(key=lambda r: (r['year'], list(county_meta).index(r['county'])))
    if len(races) != 66 or len({r['race_id'] for r in races}) != 66:
        raise ValueError('Expected 66 unique county elections')
    value = {'schema_version': 1, 'source': {'kind': 'user_supplied_cec_result_workbooks',
        'archives': archives, 'notice': 'Exact vote totals checked within uploaded CEC tables; source files have not been independently hash-matched against online originals. No historical publication timestamp asserted.'}, 'races': races}
    value['data_hash'] = digest(value)
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT/'data/candidate-history-cec.json')
    args = parser.parse_args()
    result = convert(args.folder)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    from model.data import audit_dataset
    print(json.dumps(audit_dataset(result), ensure_ascii=False))
