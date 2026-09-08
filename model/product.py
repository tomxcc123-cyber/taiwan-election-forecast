"""Publishable research product contract. Calibration is never inferred from code completion."""
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from .data import audit_race, digest, load_dataset, previous_race
from .fundamentals import fit, residual_scale, softmax
from .roster import load_roster
from .simulation import simulate
from .polling import match_records
from .joint import infer
from .validation import evaluate

VERSION = '2026.09-candidate-joint.1'


def validate_joint(history, settings=None):
    eligible=[r for r in history if audit_race(r)['research_eligible'] and previous_race(history,r)]
    train=[r for r in eligible if r['year']==2018]
    test=[r for r in eligible if r['year']==2022]
    prior=simulate(fit(train,history),test,history,train,residual_scale(train,history),draws=2000)
    # Equal terminal dates mean zero extrapolation, not a claim of historical publication dates.
    posterior=infer(prior,[],'2022-12-31','2022-12-31',settings)
    shares,winners,offset={},{},0
    for r in posterior['races']:
        k=len(r['candidates']);v=softmax(posterior['draws'][:,offset:offset+k]);offset+=k
        shares[r['race_id']]=v;winners[r['race_id']]=np.argmax(v,axis=1)
    report=evaluate({'races':posterior['races'],'shares':shares,'winners':winners,
                     'draws':posterior['settings']['simulations']},history)
    return {'scope':'same joint inference engine, no polls, zero forecast horizon, retrospective listed roster',
            'training_years':[2018],'test_year':2022,'test_cycles':1,
            'polling_likelihood_validated_on_real_elections':False,**report}


def build_product(root, now, feed, settings=None):
    historical = load_dataset(root/'data/candidate-history.json')
    roster = load_roster(root/'data/registration-roster-2026.json', historical)
    as_of = now.isoformat()
    if as_of[:10] < roster['as_of']:
        raise ValueError('Forecast date precedes registration snapshot')
    history = historical['races']
    training = [r for r in history if audit_race(r)['research_eligible'] and previous_race(history,r)]
    fitted = fit(training, history)
    sd = residual_scale(training, history)
    prior = simulate(fitted, roster['races'], history, training, sd, draws=2000)
    records, audit = match_records(feed, roster, as_of)
    posterior = infer(prior, records, as_of, '2026-11-28', settings)
    counties, offset = [], 0
    for race in posterior['races']:
        k = len(race['candidates'])
        values = softmax(posterior['draws'][:,offset:offset+k])
        quantized = np.rint(values*1000000).astype(int)
        normalized = quantized / quantized.sum(axis=1, keepdims=True)
        winners = np.argmax(normalized, axis=1)
        candidates = [{**c, 'mean': float(normalized[:,j].mean()*100),
                       'p05': float(np.quantile(normalized[:,j], .05)*100),
                       'p95': float(np.quantile(normalized[:,j], .95)*100),
                       'probability': float(np.mean(winners == j))} for j,c in enumerate(race['candidates'])]
        counties.append({'name':race['county'], 'race_id':race['race_id'], 'region':race['region'],
                         'candidates':candidates, 'draws':quantized.tolist(),
                         'poll_ids':[r['id'] for r in records if r['county'] == race['county']],
                         'history':next(r for r in history if r['county']==race['county'] and r['year']==2022)})
        previous=previous_race(history,race)
        previous_names={c['name']:c for c in previous['candidates']}
        counties[-1]['quality']={'party_changes':[c['name'] for c in race['candidates']
            if c['name'] in previous_names and c['party']!=previous_names[c['name']]['party']],
            'no_exact_previous_match':sum(c['name'] not in previous_names for c in race['candidates']),
            'latest_fieldwork':max((r['date'] for r in records if r['county']==race['county']),default=None)}
        offset += k
    order={name:i for i,name in enumerate(dict.fromkeys(r['county'] for r in history))}
    counties.sort(key=lambda r:order[r['name']])
    payload = {'schema_version':2, 'model_version':VERSION, 'generated_at':as_of,
               'election_date':'2026-11-28', 'roster_as_of':roster['as_of'],
               'candidate_set_version':roster['data_hash'], 'training_data_hash':historical['data_hash'],
               'feed_checked_at':feed['checked_at'], 'feed_hash':digest(feed['records']),
               'simulations':posterior['settings']['simulations'], 'counties':counties,
               'poll_audit':audit, 'settings':posterior['settings'], 'diagnostics':posterior['diagnostics'],
               'release':{'research_publication_allowed':True, 'calibrated_forecast':False,
                          'candidate_status':'registered_pending_review'},
               'validation':validate_joint(history,settings),
               'limitations':['候選人級研究預測，尚未完成機率校準。',
                              '登記名單尚待資格審定；歷史名單仍有缺漏，未全數核對官方原檔。',
                              '動態誤差、機構偏差及未表態誤差尺度為明示假設，非台灣資料估計值。',
                              '少數人選題目只提供相對支持訊號，未列人選保留基本面不確定性。',
                              '沒有微觀調查與人口聯合分布，不聲稱完成MRP或因果策略投票分析。']}
    payload['fingerprint'] = digest(payload)
    return payload


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('.cache/candidate-product.json'))
    parser.add_argument('--at', default=datetime.now(timezone.utc).isoformat())
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    feed = json.loads((root/'data/polls.json').read_text(encoding='utf-8'))
    output = build_product(root, datetime.fromisoformat(args.at), feed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output,ensure_ascii=False,allow_nan=False),encoding='utf-8')
    print(json.dumps({'version':VERSION,'reports':output['diagnostics']['included_reports'],'candidates':sum(len(r['candidates']) for r in output['counties'])}))
