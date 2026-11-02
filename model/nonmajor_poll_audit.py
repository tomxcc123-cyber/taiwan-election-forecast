"""Read-only poll-vs-model nonmajor-share diagnostic; not an election predictor.

Published survey respondent shares are not election-day vote shares.  The
published estimate for unlisted minor candidates is an *upper response share*
only if documented by the polling organization.  A discrepancy with the
model's eventual ballot-share simulation is NOT a calibration residual, a
falsification test, or a legal/physical bound on the election result.
"""
from __future__ import annotations

from math import isfinite


def build_nonmajor_response_audit(counties, accepted_polls, generated_at):
    county_map={c['name']:c for c in counties}
    rows=[]
    for row in sorted(accepted_polls,key=lambda r:(r['date'],r.get('id','')),reverse=True):
        limit=row.get('reported_nonmajor_support_upper_pct')
        if limit is None:
            continue
        county=row['county']
        race=county_map.get(county)
        if race is None:
            raise ValueError('Audited polling county is absent from published model')
        candidates=race['candidates']
        kmt=[c for c in candidates if c.get('party')=='KMT']
        dpp=[c for c in candidates if c.get('party')=='DPP']
        minor=[c for c in candidates if c.get('party') not in ('KMT','DPP')]
        if not (len(kmt)==1 and len(dpp)==1 and minor):
            raise ValueError('Minor-response comparison requires a unique two-major-candidate roster plus others')
        names={c['name'] for c in row['candidates']}
        if names!={kmt[0]['name'],dpp[0]['name']}:
            raise ValueError('Survey upper limit cannot be attached to a different candidate slate')
        undecided=float(row['undecided'])
        unknown=float(row.get('response_mass_unreported',0))
        nonvote=float(row.get('nonvote',0))
        known_sum=sum(float(c['support']) for c in row['candidates'])
        cap=float(limit)
        if (not all(isfinite(x) for x in (cap,known_sum,unknown,undecided,nonvote))
            or not row.get('reported_nonmajor_upper_basis')
            or not 0 <= cap <= unknown
            or not 0 <= undecided <= 100
            or abs(known_sum+undecided+nonvote+unknown-100)>1.0
            or row.get('undecided_reported') is not True):
            raise ValueError('Missing primary poll nonmajor share evidence or valid response accounting')
        if not row.get('source_url','').startswith('https://') or not row.get('pollster_id'):
            raise ValueError('Survey original provenance is missing')
        if row['date']>generated_at[:10] or row.get('retrieved_at','')[:10]>generated_at[:10]:
            raise ValueError('Future polling evidence in historical publication')
        if not isinstance(race.get('draws'),list) or not race['draws']:
            raise ValueError('Nonmajor model draws are required for diagnostic, not a point-only proxy')
        ids=[i for i,c in enumerate(candidates) if c.get('party') not in ('KMT','DPP')]
        sums=[]
        for draw in race['draws']:
            if len(draw)!=len(candidates) or any(type(v) is not int or v<0 for v in draw) or sum(draw)!=1000000:
                raise ValueError('Original model ballot share draws are invalid')
            sums.append(100*sum(draw[i] for i in ids)/1000000)
        means=sum(sums)/len(sums)
        sorted_values=sorted(sums)
        def quantile(q):
            p=(len(sorted_values)-1)*q
            lo=int(p); hi=min(len(sorted_values)-1,lo+1)
            return sorted_values[lo]*(1-(p-lo))+sorted_values[hi]*(p-lo)
        rows.append({
            'county':county,'poll_id':row['id'],'pollster_id':row['pollster_id'],
            'source':row['source'],'source_url':row['source_url'],
            'field_start':row['field_start'],'date':row['date'],
            'published_at':row.get('published_at'),
            'candidate_names':sorted(names),
            'poll_major_reported_support_pct':known_sum,
            'poll_undecided_reported_pct':undecided,
            'poll_response_unclassified_pct':unknown,
            'poll_nonmajor_support_upper_pct':cap,
            'poll_nonmajor_limit_is_strict_less_than':True,
            'poll_nonmajor_upper_basis':row['reported_nonmajor_upper_basis'],
            'model_nonmajor_candidate_count':len(minor),
            'model_nonmajor_mean_ballot_pct':round(means,4),
            'model_nonmajor_p05_ballot_pct':round(quantile(.05),4),
            'model_nonmajor_p95_ballot_pct':round(quantile(.95),4),
            'illustrative_difference_of_incomparable_metrics_pp':round(means-cap,4),
            'survey_nonmajor_plus_all_undecided_pct':round(cap+undecided,4),
            'provenance':'first_party_reported_survey_responses_vs_uncalibrated_election_day_ballot_draws',
            'is_ballot_prediction_constraint':False,
            'reweighted_or_redistributed_undecided':False,
        })
    return {
        'schema_version':1,
        'kind':'nonmajor_survey_response_comparison_not_ballot_forecast_constraint',
        'generated_at':generated_at,'source_rows':len(rows),
        'unverified_nonmajor_polls_excluded':True,
        'formal_forecast_modified':False,'probabilities_calibrated':False,
        'metrics_not_interchangeable':True,
        'caution':'Published voter survey support with undecided/unknown categories and election-day simulated vote shares have different denominators and time horizons. This is a provenance-audited discrepancy indicator, NOT an estimate of polling error or a hard ceiling on election votes.',
        'rows':rows,
    }
