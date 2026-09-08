"""Candidate-matched Gaussian poll likelihoods with explicit partial-ballot assumptions."""
from datetime import date
import unicodedata
import numpy as np


def day(value):
    return date.fromisoformat(value[:10]).toordinal()


def match_records(feed, roster, as_of):
    races = {r['county']: r for r in roster['races']}
    accepted, audit, samples = [], [], set()
    # Later revisions of overlapping fieldwork replace earlier questions, not independent samples.
    records = sorted(feed['records'], key=lambda r: (r.get('date', ''), r.get('retrieved_at', ''), r.get('id', '')), reverse=True)
    occupied = []
    for row in records:
        reason = None
        try:
            race = races[row['county']]
            start, end = day(row['field_start']), day(row['date'])
            if start > end or end > day(as_of) or start <= day('2022-12-31'):
                raise ValueError('日期超出候選人模型可用範圍')
            if row.get('retrieved_at') and day(row['retrieved_at']) > day(as_of):
                raise ValueError('資料在本次時間截點之後才收錄')
            if row.get('multiple_matchups'):
                raise ValueError('多組假設對決，暫不混入同一候選名單')
            if not row.get('source_url', '').startswith('https://') or not row.get('source'):
                raise ValueError('缺少可追溯來源')
            names = {unicodedata.normalize('NFKC', c['name']): c['candidate_id'] for c in race['candidates']}
            matched, support = [], []
            for c in row['candidates']:
                key = unicodedata.normalize('NFKC', c['name'])
                if key not in names:
                    raise ValueError('民調人選與登記名單不符，或姓名字形尚未核對')
                matched.append(names[key]); support.append(float(c['support']))
            n, undecided = float(row['sample_n']), float(row['undecided'])
            nonvote = float(row.get('nonvote',0))
            if (len(matched) < 2 or len(set(matched)) != len(matched) or n < 100
                    or not np.isfinite([n, undecided, nonvote, *support]).all()
                    or min(support) < 0 or max(support) > 100 or not 0 <= undecided <= 100
                    or not 0 <= nonvote <= 100
                    or sum(support) < 20 or abs(sum(support)+undecided+nonvote-100) > 3):
                raise ValueError('比例、樣本或未表態資料無效')
            sample = (row['county'], row['source_url'], row['field_start'], row['date'])
            pollster = row.get('pollster_id',row['source'])
            if sample in samples or any(c == row['county'] and s == pollster and start <= e and end >= b
                                        for c, s, b, e in occupied):
                raise ValueError('同來源重複題目或重疊訪問區間，保留較新紀錄')
            samples.add(sample); occupied.append((row['county'], pollster, start, end))
            accepted.append({**row, 'race_id': race['race_id'], 'candidate_ids': matched,
                             'supports': support, 'partial_ballot': len(matched) < len(race['candidates']),
                             'field_mid': (start+end)/2})
        except (KeyError, TypeError, ValueError) as error:
            reason = str(error)
        audit.append({'id': row.get('id'), 'county': row.get('county'), 'source': row.get('source'),
                      'date': row.get('date'), 'included': reason is None,
                      'reason': reason or ('已配對；僅觀測題目列出人選的相對支持' if accepted[-1]['partial_ballot'] else '已配對完整名單')})
    return sorted(accepted, key=lambda r: (r['date'], r['id'])), audit


def observation_matrices(records, candidates, settings):
    index = {c['candidate_id']: i for i, c in enumerate(candidates)}
    matrices, ys, variances, groups, metadata = [], [], [], [], []
    for row in records:
        # A fixed orthonormal contrast basis avoids privileging one denominator candidate.
        k = len(row['candidate_ids'])
        h = np.zeros((k-1, k))
        for j in range(1, k):
            h[j-1, :j] = 1 / np.sqrt(j*(j+1))
            h[j-1, j] = -j / np.sqrt(j*(j+1))
        select = np.zeros((k, len(candidates)))
        for j, cid in enumerate(row['candidate_ids']): select[j, index[cid]] = 1
        matrix = h @ select
        support = np.maximum(row['supports'], settings['rounded_zero_floor_pct'])
        q = support / support.sum()
        effective_n = row['sample_n'] * min(sum(row['supports'])/100, 1) / settings['design_effect']
        # Published weighted percentages are NOT converted to invented raw counts.
        variance = h @ np.diag(1/(effective_n*q)) @ h.T
        variance += np.eye(k-1)*(settings['poll_extra_sd']**2
                    + (row['undecided']/100 * settings['undecided_sd'])**2
                    + (settings['partial_ballot_sd']**2 if row['partial_ballot'] else 0))
        matrices.append(matrix); ys.append(h @ np.log(q)); variances.append(variance)
        groups.extend([row.get('pollster_id',row['source'])]*(k-1))
        metadata.extend([row]*(k-1))
    if not matrices:
        return np.zeros((0, len(candidates))), np.zeros(0), np.zeros((0, 0)), [], []
    a = np.vstack(matrices); y = np.concatenate(ys)
    measurement = np.zeros((len(y), len(y))); offset = 0
    for v in variances:
        measurement[offset:offset+len(v), offset:offset+len(v)] = v
        offset += len(v)
    return a, y, measurement, groups, metadata
