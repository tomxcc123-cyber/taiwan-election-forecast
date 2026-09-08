"""Race-balanced ridge regression on centered candidate log-ratio outcomes."""
import numpy as np
from .data import KNOWN_PARTIES, identity_ok, previous_race

FEATURES = ["log_previous_candidate_share", "log_previous_named_party_share_per_nominee",
            "previous_listed_winner", "no_exact_previous_name_match", "named_major_party"]
DEFAULT_ALPHA = 0.1
ZERO_FLOOR_PCT = 0.025


def center(values):
    return values - np.mean(values, axis=0)


def softmax(values):
    e = np.exp(values - np.max(values, axis=-1, keepdims=True))
    return e / e.sum(axis=-1, keepdims=True)


def target_clr(race, floor=ZERO_FLOOR_PCT):
    if not 0 < floor < 1:
        raise ValueError("Invalid rounded-zero floor (percentage points)")
    return center(np.log(np.maximum([c["share_pct"] for c in race["candidates"]], floor)))


def features(race, history):
    prior = previous_race(history, race)
    if prior is None:
        raise ValueError("No earlier comparable election; cannot manufacture historical features")
    rows = []
    for candidate in race["candidates"]:
        matches = [c for c in prior["candidates"] if c["name"] == candidate["name"]
                   and identity_ok(c["name"])]
        old = matches[0] if len(matches) == 1 else None
        party = candidate["party"] if candidate["party"] in KNOWN_PARTIES else None
        nominees = sum(c["party"] == party for c in race["candidates"]) if party else 1
        party_share = prior["party_shares_pct"].get(party, 0) / nominees if party else 0
        rows.append([np.log1p(old["share_pct"] if old else 0), np.log1p(party_share),
                     int(bool(old and old["winner"])), int(old is None), int(party is not None)])
    return center(np.array(rows, dtype=float))


def carry_forward(race, history):
    """A stated benchmark, not a trained probability: no pooled independent candidate."""
    prior = previous_race(history, race)
    scores = []
    for c in race["candidates"]:
        old = next((p for p in prior["candidates"] if p["name"] == c["name"]
                    and identity_ok(p["name"])), None)
        count = sum(p["party"] == c["party"] for p in race["candidates"]) if c["party"] else 1
        score = old["share_pct"] if old else (
            prior["party_shares_pct"].get(c["party"], 1) / count if c["party"] else 1)
        scores.append(max(score, ZERO_FLOOR_PCT))
    values = np.array(scores)
    return values / values.sum()


def fit(races, history, alpha=DEFAULT_ALPHA, floor=ZERO_FLOOR_PCT):
    if not races or not np.isfinite(alpha) or alpha <= 0:
        raise ValueError("Training races and positive regularization are required")
    xs = [features(r, history) for r in races]
    x = np.vstack(xs)
    y = np.concatenate([target_clr(r, floor) for r in races])
    weights = np.concatenate([np.full(len(z), 1 / (len(races) * len(z))) for z in xs])
    scale = np.sqrt(np.sum(weights[:, None] * x*x, axis=0))
    scale = np.where(scale > 1e-8, scale, 1)
    z = x / scale
    # Augmented least squares is ridge without explicitly inverting a normal matrix.
    a = np.vstack([z * np.sqrt(weights[:, None]), np.sqrt(alpha) * np.eye(x.shape[1])])
    b = np.concatenate([y * np.sqrt(weights), np.zeros(x.shape[1])])
    beta, _, _, _ = np.linalg.lstsq(a, b, rcond=None)
    return {"alpha": alpha, "zero_floor_pct": floor, "features": FEATURES,
            "scale": scale.tolist(), "coefficients": beta.tolist(),
            "training_years": sorted({r["year"] for r in races}),
            "training_race_ids": [r["race_id"] for r in races],
            "feature_status": ["observed" if np.any(x[:, j]) else "no_training_variation"
                               for j in range(x.shape[1])]}


def utilities(fitted, race, history):
    if max(fitted["training_years"]) >= race["year"]:
        raise ValueError("Prediction requires a strictly later election than all training labels")
    return features(race, history) / np.array(fitted["scale"]) @ np.array(fitted["coefficients"])


def residual_scale(races, history, alpha=DEFAULT_ALPHA, floor=ZERO_FLOOR_PCT):
    # Internal geographic cross-fitting uses only training cycles, never the time holdout.
    variances = []
    for county in sorted({r["county_id"] for r in races}):
        train = [r for r in races if r["county_id"] != county]
        fitted = fit(train, history, alpha, floor)
        for r in races:
            if r["county_id"] != county:
                continue
            pred = features(r, history) / np.array(fitted["scale"]) @ fitted["coefficients"]
            error = target_clr(r, floor) - pred
            if len(error) > 1:
                variances.append(float(error @ error / (len(error) - 1)))
    if not variances:
        raise ValueError("Too few training counties to estimate residual dispersion")
    return float(np.sqrt(np.mean(variances)))
