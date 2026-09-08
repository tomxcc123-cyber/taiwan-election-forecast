"""Approximate dynamic joint Gaussian inference, conditional on stated hyperparameters."""
import numpy as np
from .polling import day, observation_matrices

SETTINGS = {'design_effect': 2.0, 'poll_extra_sd': .12, 'house_sd': .18,
            'partial_ballot_sd': .25, 'undecided_sd': .5, 'rounded_zero_floor_pct': .05,
            'local_daily_variance': .0005, 'national_daily_variance': .00012,
            'regional_daily_variance': .00008, 'simulations': 2000, 'seed': 20260908}


def psd(matrix):
    values, vectors = np.linalg.eigh((matrix+matrix.T)/2)
    if values.min() < -1e-7:
        raise ValueError('Covariance is not positive semidefinite')
    return (vectors * np.maximum(values, 0)) @ vectors.T


def structure(races, settings):
    candidates = [c for r in races for c in r['candidates']]
    d = len(candidates)
    center = np.zeros((d, d)); offset = 0
    for r in races:
        k = len(r['candidates'])
        center[offset:offset+k, offset:offset+k] = np.eye(k)-np.ones((k,k))/k
        offset += k
    party_keys = sorted({c['party'] for c in candidates if c['party']})
    national = np.array([[int(c['party'] == p) for p in party_keys] for c in candidates], dtype=float)
    regional_keys = sorted({(r['region'], c['party']) for r in races for c in r['candidates'] if c['party']})
    regional = np.array([[int((r['region'], c['party']) == key) for key in regional_keys]
                         for r in races for c in r['candidates']], dtype=float)
    q = center @ (np.eye(d)*settings['local_daily_variance']
        + national@national.T*settings['national_daily_variance']
        + regional@regional.T*settings['regional_daily_variance']) @ center
    return candidates, center, q, center@national


def infer(prior_simulation, records, as_of, election_date, settings=None):
    settings = {**SETTINGS, **(settings or {})}
    if any(not np.isfinite(v) or v < 0 for v in settings.values()) or settings['design_effect'] <= 0:
        raise ValueError('Invalid model settings')
    races = prior_simulation['races']
    candidates, center, q, party_loadings = structure(races, settings)
    logs = np.concatenate([np.log(np.maximum(prior_simulation['shares'][r['race_id']], 1e-12)) for r in races], axis=1)
    logs = logs @ center
    mean, covariance = logs.mean(axis=0), np.cov(logs, rowvar=False)
    a, y, noise, groups, metadata = observation_matrices(records, candidates, settings)
    innovation_score = None
    if len(y):
        # Reverse-time Brownian covariance: observations at nearby dates share drift error.
        ages = np.array([max(0, day(as_of)-r['field_mid']) for r in metadata])
        noise += (a @ q @ a.T) * np.minimum.outer(ages, ages)
        # Shared zero-centered pollster effects are integrated out, not estimated independently
        # for every report or treated as additional sample size.
        for institution in sorted(set(groups)):
            load = a @ party_loadings
            load[np.array(groups) != institution] = 0
            noise += settings['house_sd']**2 * (load@load.T)
        s = a@covariance@a.T + noise
        innovation = y-a@mean
        solved = np.linalg.solve(s, a@covariance)
        mean = mean + solved.T @ innovation
        covariance = psd(covariance - covariance@a.T@solved)
        innovation_score = float(innovation @ np.linalg.solve(s, innovation))
    horizon = max(0, day(election_date)-day(as_of))
    current_covariance = covariance.copy()
    covariance = psd(center @ (covariance+q*horizon) @ center)
    mean = center@mean
    values, vectors = np.linalg.eigh(covariance)
    rng = np.random.default_rng(settings['seed'])
    draws = mean + rng.normal(size=(settings['simulations'], len(mean))) @ (vectors*np.sqrt(np.maximum(values,0))).T
    return {'races': races, 'draws': draws, 'mean': mean, 'covariance': covariance,
            'current_covariance': current_covariance, 'settings': settings,
            'diagnostics': {'observation_contrasts': len(y), 'included_reports': len(records),
                            'innovation_mahalanobis': innovation_score, 'horizon_days': horizon,
                            'minimum_eigenvalue': float(values.min()),
                            'inference': 'Gaussian moment approximation; hyperparameters assumed, not calibrated'}}
