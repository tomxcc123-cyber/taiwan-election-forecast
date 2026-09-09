"""Race-block TVBS error fitting and held-out fieldwork-cutoff backtests.

This is conditional Gaussian likelihood estimation, not MCMC or a real-time archive.
The 2022 labels never enter parameter selection. Other pollsters retain prior settings.
"""
import json
from collections import defaultdict
from datetime import date, timedelta
import numpy as np
from .data import digest, eligible_cec_transitions
from .fundamentals import fit, residual_scale, softmax
from .simulation import simulate
from .polling import day, observation_matrices
from .joint import SETTINGS, infer, structure
from .validation import evaluate
from .refinement import select_fit

GRID = (.08, .12, .18, .25, .35, .5, .7, 1.0)


def load_polls(root, cec_hash):
    data = json.loads((root/'data/historical-polls-tvbs.json').read_text(encoding='utf-8'))
    if data['cec_data_hash'] != cec_hash or digest({k:v for k,v in data.items() if k!='data_hash'}) != data['data_hash']:
        raise ValueError('Historical poll provenance hash mismatch')
    return data


def fit_error(records, history):
    training = [r for r in records if r['eligible'] and r['year'] in (2014, 2018)]
    groups = defaultdict(list)
    for r in training: groups[r['race_id']].append(r)
    races = {r['race_id']:r for r in history if r['year'] in (2014, 2018)}
    if len(groups) < 5: raise ValueError('Insufficient historical election clusters')
    blocks = []
    for race_id, rows in sorted(groups.items()):
        race = races[race_id]
        candidates, _, q, party = structure([race], SETTINGS)
        # Build the full within-election covariance. Repeated waves are not iid elections.
        a, y, noise, _, metadata = observation_matrices(rows, candidates, {**SETTINGS, 'poll_extra_sd':0})
        ages = np.array([day(race['election_date'])-r['field_mid'] for r in metadata])
        noise += (a@q@a.T)*np.minimum.outer(ages, ages)
        load = a@party
        noise += SETTINGS['house_sd']**2*(load@load.T)
        actual = np.log(np.maximum([c['share_pct'] for c in candidates], .025))
        blocks.append((race['county'], y-a@actual, noise))
    losses = []
    block_losses = []
    for sd in GRID:
        values = []
        for _, error, base in blocks:
            covariance = base+np.eye(len(error))*sd**2
            sign, determinant = np.linalg.slogdet(covariance)
            if sign <= 0: raise ValueError('Invalid historical likelihood covariance')
            values.append(float((determinant+error@np.linalg.solve(covariance,error))/2/len(error)))
        block_losses.append(values)
        losses.append(float(np.mean(values)))
    selected = int(np.argmin(losses))
    # County-block bootstrap describes selection stability, not a posterior interval.
    counties = sorted({b[0] for b in blocks})
    rng = np.random.default_rng(20260908)
    matrix = np.array(block_losses)
    bootstrap = []
    for _ in range(200):
        sampled = rng.choice(counties, size=len(counties), replace=True)
        indices = [i for c in sampled for i,b in enumerate(blocks) if b[0]==c]
        bootstrap.append(GRID[int(np.argmin(matrix[:,indices].mean(axis=1)))])
    boundary = selected in (0,len(GRID)-1)
    return {'parameter':'tvbs_poll_extra_sd', 'value':GRID[selected],
        'applied_value':max(SETTINGS['poll_extra_sd'], GRID[selected]),
        'release_rule':'Never tighten the existing error floor from this single-pollster small sample; retain at least 0.12. This rule does not inspect 2022 scores.',
        'training_years':[2014,2018],
        'training_waves':len(training), 'training_races':len(groups), 'training_counties':len(counties),
        'training_ids':[r['id'] for r in training], 'objective':'equal-election, per-contrast Gaussian block negative log likelihood',
        'grid':[{'sd':sd,'loss':loss} for sd,loss in zip(GRID,losses)],
        'boundary_solution':boundary,
        'bootstrap_selection_p05_p95':np.quantile(bootstrap,[.05,.95]).tolist(),
        'bootstrap_notice':'200 county-cluster resamples of the fixed grid; stability range, not a confidence or credible interval.',
        'remaining_assumptions':['design_effect','house_sd','partial_ballot_sd','undecided_sd',
                                 'local_daily_variance','national_daily_variance','regional_daily_variance'],
        'scope':'TVBS only; no fitted cross-pollster bias or turnout-screen coefficient. No 2022 outcomes used.'}


def eligible_at(records, year, cutoff):
    return [r for r in records if r['eligible'] and r['year']==year and r['date']<=cutoff]


def posterior_simulation(prior, records, horizon, settings):
    shares, winners = {}, {}
    # Separate postponed Chiayi election; do not backdate its December polls to November.
    for election_day in sorted({r['election_date'] for r in prior['races']}):
        races = [r for r in prior['races'] if r['election_date']==election_day]
        ids = {r['race_id'] for r in races}
        cutoff = (date.fromisoformat(election_day)-timedelta(days=horizon)).isoformat()
        rows = [r for r in eligible_at(records,2022,cutoff) if r['race_id'] in ids]
        subset = {**prior,'races':races}
        result = infer(subset,rows,cutoff,election_day,settings)
        offset = 0
        for r in races:
            k = len(r['candidates'])
            v = softmax(result['draws'][:,offset:offset+k]);offset+=k
            shares[r['race_id']]=v;winners[r['race_id']]=np.argmax(v,axis=1)
    return {'races':prior['races'],'shares':shares,'winners':winners,'draws':2000}


def validate_history(history, poll_data, fitted):
    transitions = eligible_cec_transitions(history)
    train = [r for r in transitions if r['year']==2018]
    test = [r for r in transitions if r['year']==2022]
    fundamental_fit = select_fit(train, history)
    prior = simulate(fundamental_fit,test,history,train,residual_scale(train,history,alpha=fundamental_fit['alpha']),draws=2000)
    settings = {'tvbs_poll_extra_sd':fitted['value']}
    reports = []
    for horizon in (90,30,14):
        used = [r for r in poll_data['records'] if r['eligible'] and r['year']==2022
                and day(r['election_date'])-day(r['date'])>=horizon]
        simulation = posterior_simulation(prior,poll_data['records'],horizon,settings)
        report = evaluate(simulation,history)
        old = evaluate(posterior_simulation(prior,poll_data['records'],horizon,{}),history)
        no_polls = evaluate(posterior_simulation(prior,[],horizon,{}),history)
        polled = {r['race_id'] for r in used}
        subset = {**simulation, 'races':[r for r in simulation['races'] if r['race_id'] in polled]}
        reports.append({'horizon_days':horizon,'poll_count':len(used),'polled_counties':len(polled),
            'poll_ids':[r['id'] for r in used], 'metrics':report['metrics'],
            'previous_settings':old['metrics'], 'no_polls':no_polls['metrics'],
            'polled_subset':evaluate(subset,history)['metrics'] if polled else None,
            'baselines':report['baselines'], 'details':report['details'],
            'reliability_bins':report['reliability_bins']})
    return {'test_year':2022,'test_cycles':1,'training_years':[2014,2018],
        'fundamental_selection': fundamental_fit['selection'],
        'roster_condition':'Final listed historical candidates are known retrospectively.',
        'availability':'Fieldwork-end cutoffs, NOT verified publication-time backtests.',
        'not_independent':'The same 22 elections recur at all three horizons; do not count as 66 test elections.',
        'reports':reports}


def build_research(root, historical):
    polls = load_polls(root,historical['data_hash'])
    fitted = fit_error(polls['records'],historical['races'])
    return {'data_hash':polls['data_hash'],'audit':polls['audit'],'fit':fitted,
            'validation':validate_history(historical['races'],polls,fitted),
            'records':polls['records'],'verification':polls['verification'],'availability':polls['availability']}
