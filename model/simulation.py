"""Joint experimental draws, keeping separate independent candidates and seat scopes."""
import numpy as np
from hashlib import sha256
from .fundamentals import fit, features, softmax, utilities

SEED = sum(map(ord, "taiwan-candidate-shadow-v1"))


def simulate(fitted, targets, history, training, residual_sd, draws=2000, seed=SEED,
             bootstrap_count=100, national_sd=0.15, regional_sd=0.10, support_proxy_sd=0.0):
    if (draws < 100 or bootstrap_count < 1 or not targets
            or any(not np.isfinite(x) or x < 0 for x in (residual_sd, national_sd, regional_sd, support_proxy_sd))):
        raise ValueError("Invalid simulation settings")
    targets = [{**r, "candidates": sorted(r["candidates"], key=lambda c: c["candidate_id"])}
               for r in sorted(targets, key=lambda r: r["race_id"])]
    for r in targets:
        utilities(fitted, r, history)  # Enforce time separation before bootstrap fits.
    rng = np.random.default_rng(seed)
    counties = sorted({r["county_id"] for r in training})
    bootstrap = []
    for _ in range(bootstrap_count):
        sampled = rng.choice(counties, len(counties), replace=True)
        rows = [r for county in sampled for r in training if r["county_id"] == county]
        bootstrap.append(fit(rows, history, fitted["alpha"], fitted["zero_floor_pct"]))
    # The same bootstrap coefficients and party shocks apply to every county in a draw.
    choices = rng.integers(0, bootstrap_count, draws)
    parties = sorted({c["party"] for r in targets for c in r["candidates"] if c["party"]})
    national = {p: rng.normal(0, national_sd, draws) for p in parties}
    regional = {(region, p): rng.normal(0, regional_sd, draws)
                for region in sorted({r["region"] for r in targets}) for p in parties}
    values, winners = {}, {}
    for r in targets:
        x = features(r, history)
        means = np.array([x / np.array(b["scale"]) @ b["coefficients"] for b in bootstrap])
        noise = rng.normal(0, residual_sd, (draws, len(r["candidates"])))
        for j, c in enumerate(r["candidates"]):
            if c.get('organization_evidence') and support_proxy_sd:
                proxy_seed = int.from_bytes(sha256(f"{seed}:{c['candidate_id']}:support-proxy".encode()).digest()[:8], 'big')
                proxy_rng = np.random.default_rng(proxy_seed)
                noise[:, j] += proxy_rng.normal(0, support_proxy_sd, draws)
            if c["party"]:
                noise[:, j] += national[c["party"]] + regional[r["region"], c["party"]]
        shares = softmax(means[choices] + noise)
        values[r["race_id"]] = shares
        winners[r["race_id"]] = np.argmax(shares, axis=1)
    return {"races": targets, "shares": values, "winners": winners, "draws": draws,
            "assumptions": {"residual_sd": residual_sd, "national_sd": national_sd,
                            "regional_sd": regional_sd, "bootstrap_count": bootstrap_count,
                            "seed": seed, "correlation_parameters_estimated": False,
                            "support_proxy_sd": support_proxy_sd, "intervals_calibrated": False}}


def condition_on_winner(simulation, race_id, candidate_id, minimum_ess=100):
    """Actual rejection conditioning, never a display-only forced seat."""
    if minimum_ess < 1:
        raise ValueError("Minimum ESS must be positive")
    race = next(r for r in simulation["races"] if r["race_id"] == race_id)
    index = next(i for i, c in enumerate(race["candidates"]) if c["candidate_id"] == candidate_id)
    mask = simulation["winners"][race_id] == index
    ess = int(mask.sum())
    if ess < minimum_ess:
        raise ValueError(f"Condition too rare: {ess} accepted draws < minimum ESS {minimum_ess}")
    return {**simulation, "shares": {k: v[mask] for k, v in simulation["shares"].items()},
            "winners": {k: v[mask] for k, v in simulation["winners"].items()}, "draws": ess,
            "conditioning": {"race_id": race_id, "candidate_id": candidate_id, "ess": ess,
                             "acceptance": ess / simulation["draws"]}}


def summarize(simulation):
    rows, seats = [], {}
    for race in simulation["races"]:
        values = simulation["shares"][race["race_id"]]
        winner = simulation["winners"][race["race_id"]]
        candidates = []
        for j, c in enumerate(race["candidates"]):
            group = c["party"] or ("IND" if c["legacy_bloc"] == "IND" else "UNRESOLVED")
            seats.setdefault(group, np.zeros(simulation["draws"], dtype=int))
            seats[group] += winner == j
            candidates.append({"candidate_id": c["candidate_id"], "name": c["name"],
                               "party": c["party"], "share_mean": float(values[:, j].mean()),
                               "p05": float(np.quantile(values[:, j], .05)),
                               "p95": float(np.quantile(values[:, j], .95)),
                               "win_probability": float(np.mean(winner == j))})
        rows.append({"race_id": race["race_id"], "county": race["county"], "candidates": candidates})
    n = len(rows)
    return {"county_forecasts": rows, "joint_seats": {"scope": "audited historical subset only",
            "covered_races": n, "national_majority_probability": None,
            "groups": {p: {"mean": float(v.mean()), "p05": int(np.quantile(v, .05)),
                           "p95": int(np.quantile(v, .95)),
                           "histogram": (np.bincount(v, minlength=n+1) / len(v)).tolist()}
                       for p, v in seats.items()}}}
