"""Election-year holdout; race-balanced scores and explicitly limited calibration evidence."""
import numpy as np
from .fundamentals import carry_forward


def point_metrics(predictions, targets):
    absolute, squared = [], []
    for r in targets:
        actual = np.array([c["share_pct"] for c in r["candidates"]], dtype=float)
        actual /= actual.sum()
        error = (predictions[r["race_id"]] - actual) * 100
        absolute.append(float(np.mean(np.abs(error))))
        squared.append(float(np.mean(error**2)))
    return {"mae_pp": float(np.mean(absolute)), "rmse_pp": float(np.sqrt(np.mean(squared))),
            "races": len(targets), "candidate_rows": sum(len(r["candidates"]) for r in targets)}


def evaluate(simulation, history):
    targets = simulation["races"]
    predictions = {k: v.mean(axis=0) for k, v in simulation["shares"].items()}
    metrics = point_metrics(predictions, targets)
    coverage, widths, wis, brier, losses, details = [], [], [], [], [], []
    bins = [{"lower": i/5, "upper": (i+1)/5, "candidate_rows": 0,
             "probability_sum": 0.0, "wins": 0} for i in range(5)]
    for race in targets:
        v = simulation["shares"][race["race_id"]]
        actual = np.array([c["share_pct"] for c in race["candidates"]])
        actual = actual / actual.sum()
        truth = np.array([int(c["winner"]) for c in race["candidates"]])
        counts = np.bincount(simulation["winners"][race["race_id"]], minlength=len(truth))
        # Finite-draw smoothing avoids reporting log(0) as evidence of true impossibility.
        probabilities = (counts + .5) / (simulation["draws"] + .5 * len(truth))
        low, median, high = np.quantile(v, [.05, .5, .95], axis=0)
        interval_score = high-low + 20*np.maximum(low-actual, 0) + 20*np.maximum(actual-high, 0)
        score = (.5 * np.abs(actual-median) + .05 * interval_score) / 1.5
        coverage.append(float(np.mean((low <= actual) & (actual <= high))))
        widths.append(float(np.mean(high-low) * 100))
        wis.append(float(np.mean(score) * 100))
        brier.append(float(np.sum((probabilities-truth)**2)))
        losses.append(float(-np.log(probabilities[truth == 1][0])))
        for j, c in enumerate(race["candidates"]):
            bucket = bins[min(4, int(probabilities[j]*5))]
            bucket["candidate_rows"] += 1
            bucket["probability_sum"] += float(probabilities[j])
            bucket["wins"] += int(truth[j])
            details.append({"county": race["county"], "race_id": race["race_id"],
                            "candidate_id": c["candidate_id"], "name": c["name"],
                            "actual_raw_pct": c["share_pct"], "actual_closed_pct": float(actual[j]*100),
                            "predicted_pct": float(predictions[race["race_id"]][j]*100),
                            "p05_pct": float(low[j]*100), "p95_pct": float(high[j]*100),
                            "win_probability": float(probabilities[j]), "winner": bool(truth[j])})
    metrics.update({"coverage_90": float(np.mean(coverage)), "mean_width_90_pp": float(np.mean(widths)),
                    "wis_90_pp": float(np.mean(wis)), "multiclass_brier": float(np.mean(brier)),
                    "log_loss": float(np.mean(losses))})
    return {"metrics": metrics, "baselines": {
            "carry_forward": point_metrics({r["race_id"]: carry_forward(r, history) for r in targets}, targets),
            "uniform": point_metrics({r["race_id"]: np.full(len(r["candidates"]), 1/len(r["candidates"]))
                                      for r in targets}, targets)},
            "reliability_bins": [{"lower": b["lower"], "upper": b["upper"],
                                  "candidate_rows": b["candidate_rows"], "wins": b["wins"],
                                  "mean_probability": b["probability_sum"]/b["candidate_rows"] if b["candidate_rows"] else None,
                                  "observed_fraction": b["wins"]/b["candidate_rows"] if b["candidate_rows"] else None}
                                 for b in bins], "details": details,
            "metric_definition": "Equal race weight. Share errors use listed-candidate closure within rounding tolerance. Brier is sum across candidates then mean across races; win scores use 0.5-count Monte Carlo smoothing. WIS uses median and one central 90% interval. Reliability rows are dependent, not independent election cycles."}
