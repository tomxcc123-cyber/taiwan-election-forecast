"""Two separate election-cycle CEC county-turnout holdouts (2014→2018, 2018→2022).

Source data: audited historical county mayoral turnout counts only.
Each prediction sees the EARLIER election's 22 county rates and its nationwide
average. No 2018 values in 2018 predictions; no 2022 values in 2022 predictions.
Shrinkage weights 1.0, 0.75 and 0.5 are fixed, never selected per cycle.
This is county-level baseline replication, NOT validation of township formulas.
"""
import argparse
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
YEARS=(2014,2018,2022)
METHODS={'persistence':1.0,'national_shrink_75':0.75,'national_shrink_50':0.5}
FIELDS=('electorate','ballots_cast','valid_votes','invalid_votes')


def checked_rate(record):
    for field in FIELDS:
        if type(record.get(field)) is not int or record[field]<0:
            raise ValueError('CEC county vote count missing or non-integer')
    if (record['electorate']==0 or record['ballots_cast']>record['electorate'] or
        record['valid_votes']+record['invalid_votes']!=record['ballots_cast']):
        raise ValueError('CEC county turnout accounting error')
    return record['ballots_cast']/record['electorate']


def county_cycles(history):
    races=history.get('races',[])
    if len(races)!=66:
        raise ValueError('Expected 66 original CEC mayoral races')
    by_year={y:{} for y in YEARS}
    for r in races:
        y=r['year']
        if y not in YEARS or r['county'] in by_year[y]:
            raise ValueError('Duplicate, unexpected CEC county-year')
        checked_rate(r)
        by_year[y][r['county']]=r
    names=set(by_year[2014])
    if len(names)!=22 or any(set(by_year[y])!=names for y in YEARS):
        raise ValueError('County sets not comparable across election cycles')
    rates={}
    for y in YEARS:
        total_e=sum(r['electorate'] for r in by_year[y].values())
        total_v=sum(r['ballots_cast'] for r in by_year[y].values())
        rates[y]=total_v/total_e
    result={}
    for prev,target in [(2014,2018),(2018,2022)]:
        rows=[]
        for county in sorted(names):
            old,new=by_year[prev][county],by_year[target][county]
            old_rate=checked_rate(old)
            truth=checked_rate(new)
            predictions={
                k:rates[prev]+w*(old_rate-rates[prev])
                for k,w in METHODS.items()
            }
            rows.append({
                'county':county,'training_year':prev,'target_year':target,
                'prev_turnout_pct':round(old_rate*100,5),
                'target_turnout_pct':round(truth*100,5),
                'target_electorate':new['electorate'],
                'predicted_turnout_pct':{k:round(v*100,5) for k,v in predictions.items()},
                'errors_pp':{k:(v-truth)*100 for k,v in predictions.items()}
            })
        total=sum(x['target_electorate'] for x in rows)
        scores={}
        for k in METHODS:
            score={
                'weighted_mae_pp':round(sum(
                    r['target_electorate']*abs(r['errors_pp'][k]) for r in rows)/total,5),
                'weighted_rmse_pp':round(math.sqrt(sum(
                    r['target_electorate']*r['errors_pp'][k]**2 for r in rows)/total),5),
                'equal_county_mae_pp':round(sum(abs(r['errors_pp'][k]) for r in rows)/len(rows),5),
            }
            scores[k]=score
        for k,score in scores.items():
            score['delta_mae_vs_persistence_pp']=round(
                score['weighted_mae_pp']-scores['persistence']['weighted_mae_pp'],5)
            score['improved_counties']=sum(
                abs(x['errors_pp'][k])+1e-10<abs(x['errors_pp']['persistence'])
                for x in rows)
        result[f'{prev}_to_{target}']={
            'train_year':prev,'test_year':target,'counties':len(rows),
            'train_national_turnout_pct':round(rates[prev]*100,5),
            'scores':scores,'rows':rows
        }
    stable=[k for k in METHODS if k!='persistence' and
        all(result[period]['scores'][k]['delta_mae_vs_persistence_pp']<0
            for period in result)]
    return {
        'schema_version':1,'kind':'cec_county_turnout_two_cycle_baseline_check',
        'source':'CEC 2014/2018/2022 audited same-office county mayoral original integer totals',
        'years':list(YEARS),'cycle_count':2,'county_count_each_cycle':22,
        'model_weights':METHODS,
        'model_selection':'Fixed weights, no parameters estimated from holdout labels',
        'training_info':'For each held-out year use only immediately preceding election county counts and its pooled all-county rate',
        'leakage_gate':'no 2018 outcome enters 2018 predictor; no 2022 outcome enters 2022 predictor',
        'county_not_township':'This cannot validate the more granular 2018→2022 township shadow model or its national-drift term.',
        'cycles':result,
        'both_cycles_improved_over_persistence':stable,
        'promotion_gate':{
            'status':'blocked',
            'reason':'Only two county-wide retrospective cycles and no pre-2018 district source alignment; does not establish prospective performance or candidate vote effects',
            'formal_hb_tlef_unchanged':True,
            'allow_2026_candidate_win_probability_modification':False,
        }
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--history',type=Path,default=ROOT/'data/candidate-history-cec.json')
    p.add_argument('--output',type=Path,default=ROOT/'data/turnout-county-two-cycle-2014-2022.json')
    args=p.parse_args()
    source=json.loads(args.history.read_text(encoding='utf8'))
    result=county_cycles(source)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    print(json.dumps({'independent_county_cycles':{
        period:{k:r['weighted_mae_pp'] for k,r in info['scores'].items()}
        for period,info in result['cycles'].items()},
        'both_cycles_improved':result['both_cycles_improved_over_persistence'],
        'promotion':result['promotion_gate']['status']},ensure_ascii=False))


if __name__=='__main__':main()
