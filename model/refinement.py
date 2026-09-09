"""Training-only grouped tuning and explicit organizational-support proxies."""
import copy
import json
import numpy as np
from .data import KNOWN_PARTIES
from .fundamentals import fit, features, softmax

ALPHAS = (.01, .03, .1, .3, 1.0)


def select_fit(training, history):
    counties = sorted({r['county_id'] for r in training})
    if len(counties) < 3:
        raise ValueError('At least three training county groups required')
    scores = []
    for alpha in ALPHAS:
        errors, losses, county_losses = [], [], []
        for county in counties:
            local_losses = []
            inner = [r for r in training if r['county_id'] != county]
            fitted = fit(inner, history, alpha=alpha)
            for r in training:
                if r['county_id'] != county:
                    continue
                prediction = softmax(features(r, history)/np.array(fitted['scale'])@fitted['coefficients'])
                actual = np.array([c['share_pct'] for c in r['candidates']]); actual /= actual.sum()
                losses.append(float(-actual@np.log(np.maximum(prediction, 1e-12))))
                local_losses.append(losses[-1])
                errors.append(float(np.mean(np.abs(prediction-actual))*100))
            county_losses.append(float(np.mean(local_losses)))
        scores.append({'alpha': alpha, 'cross_entropy': float(np.mean(losses)), 'mae_pp': float(np.mean(errors)),
                       'county_losses': county_losses})
    proposed = min(scores, key=lambda row: (row['cross_entropy'], -row['alpha']))
    anchor = next(row for row in scores if row['alpha'] == .1)
    improvement = np.array(anchor['county_losses'])-np.array(proposed['county_losses'])
    mean = float(improvement.mean())
    se = float(improvement.std(ddof=1)/np.sqrt(len(counties)))
    # A conservative development guard, not a significance test on dependent CV folds.
    accepted = mean > 2*se and proposed['mae_pp'] <= anchor['mae_pp']
    selected = proposed if accepted else anchor
    fitted = fit(training, history, alpha=selected['alpha'])
    fitted['selection'] = {'method': 'leave-one-county-out within training years',
        'objective': 'equal-race cross entropy of candidate vote shares; not winner log loss',
        'county_groups': len(counties), 'training_years': sorted({r['year'] for r in training}),
        'selected_alpha': selected['alpha'], 'grid': scores,
        'proposed_alpha': proposed['alpha'], 'proposal_adopted': bool(accepted),
        'paired_loss_improvement': mean, 'paired_loss_se': se,
        'release_guard': 'Keep 0.1 unless paired county loss improves by more than two descriptive standard errors and CV share MAE does not worsen. This is not a formal hypothesis test.',
        'boundary_solution': selected['alpha'] in (ALPHAS[0], ALPHAS[-1]),
        'proposal_at_grid_boundary': proposed['alpha'] in (ALPHAS[0], ALPHAS[-1]),
        'scope': 'No later-election labels enter selection. Geographic CV is not an extra independent election cycle.'}
    return fitted


def support_roster(roster, root, as_of):
    """Keep formal party identity. Transport party-history features, not fixed vote transfers."""
    result = copy.deepcopy(roster)
    context = json.loads((root/'data/candidate-context.json').read_text(encoding='utf-8'))
    applied = []
    if context['reviewed_at'] > as_of[:10]:
        return result, applied
    for event in context['events']:
        if event['date'] > as_of[:10] or event['type'] != 'documented_support':
            continue
        party = event['supporting_party']
        if party not in KNOWN_PARTIES or not event['source_url'].startswith('https://'):
            raise ValueError('Unsupported endorsement source or party')
        race = next(r for r in result['races'] if r['county'] == event['county'])
        candidate = next(c for c in race['candidates'] if c['name'] == event['candidate'])
        candidate['organization_parties'] = sorted(set(candidate.get('organization_parties', [])) | {party})
        candidate['organization_evidence'] = sorted(set(candidate.get('organization_evidence', [])) | {event['id']})
        applied.append(event['id'])
    return result, sorted(applied)
