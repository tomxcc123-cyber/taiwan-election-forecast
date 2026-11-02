import copy
import unittest
from pathlib import Path

import numpy as np

from model.nonmajor_rolling_holdout import build_report, build_report_from_rows, _score


ROOT = Path(__file__).resolve().parents[1]


def fixture():
    rows, races = [], []
    for year in (2014, 2018, 2022):
        for county, nonmajor, observed in (
            ("甲縣", 1, .04 + (year-2014)/1000),
            ("乙縣", 2, .32 - (year-2014)/1000),
            ("丙縣", 0, 0),
        ):
            carry = .02 if county=="甲縣" else .28 if county=="乙縣" else 0
            rows.append({
                "target_year":year,"county":county,"race_id":f"{year}-{county}",
                "target_nonmajor_share":observed,"previous_nonmajor_share":carry,
                "council_independent_share":carry+.05,
                "town_independent_share":carry/2,
                "town_available":1,
                "faction_propensity":carry,
                "log_nonmajor_candidate_count":float(np.log1p(nonmajor)),
                "has_tpp_candidate":float(nonmajor==2),
                "log_independent_candidate_count":float(np.log1p(nonmajor)),
                "log_minor_party_candidate_count":0,
                "information_weight":1,
            })
            candidates=[{"party":"KMT"},{"party":"DPP"}]+[{"party":None} for _ in range(nonmajor)]
            races.append({"year":year,"county":county,"candidates":candidates})
    return rows,races


class NonmajorRollingHoldoutTests(unittest.TestCase):
    def test_chronological_folds_holdout_labels_and_promotion_are_isolated(self):
        source, history=fixture()
        before=copy.deepcopy(source)
        report=build_report_from_rows(source,history)
        self.assertEqual(source,before)
        self.assertEqual(report["evaluation_cycles"],[2018,2022])
        self.assertEqual(report["row_count"],6)
        self.assertEqual(report["folds"][0]["training_years"],[2014])
        self.assertEqual(report["folds"][1]["training_years"],[2014,2018])
        self.assertFalse(report["promotion_gate"]["promote_to_formal_forecast"])
        self.assertFalse(report["promotion_gate"]["2026_forecast_t3_parameters_changed"])
        self.assertFalse(report["promotion_gate"]["independent_unseen_future_election_validation"])
        self.assertEqual(report["scores"]["2022"]["unique_kmt_dpp_pair"]["models"]["t3_blend_pct"]["n"],3)
        self.assertEqual(report["scores"]["2022"]["nonmajor_present_unique_pair"]["models"]["t3_blend_pct"]["n"],2)
        self.assertEqual(report["bootstrap"]["cluster_combined"]["unique_counties"],2)
        self.assertEqual(report,build_report_from_rows(source,history))

    def test_roster_feasibility_zero_minor_and_mass_consistency(self):
        source,history=fixture()
        report=build_report_from_rows(source,history)
        no_third=[r for r in report["rows"] if r["county"]=="丙縣"]
        self.assertEqual(len(no_third),2)
        self.assertTrue(all(r["t3_blend_pct"]==r["carry_pct"]==0 for r in no_third))
        self.assertTrue(all(r["no_nonmajor_candidate_forces_zero"] for r in no_third))

    def test_future_target_does_not_fit_earlier_years(self):
        rows,races=fixture()
        a=build_report_from_rows(rows,races)
        future=[dict(x) for x in rows]
        for x in future:
            if x["target_year"]==2022:
                x["target_nonmajor_share"]=.90 if x["county"]!="丙縣" else 0
        b=build_report_from_rows(future,races)
        self.assertEqual(
            [(x["county"],x["t3_blend_pct"]) for x in a["rows"] if x["year"]==2018],
            [(x["county"],x["t3_blend_pct"]) for x in b["rows"] if x["year"]==2018])
        self.assertEqual(
            [(x["county"],x["t3_blend_pct"]) for x in a["rows"] if x["year"]==2022],
            [(x["county"],x["t3_blend_pct"]) for x in b["rows"] if x["year"]==2022])

    def test_duplicates_future_leak_and_missing_actual_roster_fail_closed(self):
        rows,races=fixture()
        with self.assertRaisesRegex(ValueError,"duplicate"):
            build_report_from_rows(rows+[copy.deepcopy(rows[0])],races)
        bad=copy.deepcopy(rows);bad[0]["target_year"]=2026
        with self.assertRaisesRegex(ValueError,"outside"):
            build_report_from_rows(bad,races)
        with self.assertRaisesRegex(ValueError,"target missing"):
            build_report_from_rows(rows,races[:-1])
        broken=copy.deepcopy(rows);x=next(x for x in broken if x["target_year"]==2022 and x["county"]=="丙縣")
        x["target_nonmajor_share"]=.30
        with self.assertRaisesRegex(ValueError,"contradicts"):
            build_report_from_rows(broken,races)

    def test_bias_and_overestimate_are_signed_not_absolute(self):
        rows=[{"actual_pct":10,"pred":15},{"actual_pct":30,"pred":20}]
        z=_score(rows,"pred")
        self.assertEqual(z["mae_pp"],7.5)
        self.assertEqual(z["bias_pp"],-2.5)
        self.assertEqual(z["overestimated"],1)
        self.assertEqual(z["over_5pp"],0)
        self.assertEqual(z["under_5pp"],1)

    def test_actual_cec_lineage_and_unique_scopes(self):
        report=build_report(ROOT)
        self.assertEqual(report["kind"],"historical_t3_rolling_origin_research_no_2026_forecast_promotion")
        self.assertTrue(report["rows_by_year"]["2014"]>0)
        self.assertTrue(report["rows_by_year"]["2018"]>0)
        self.assertTrue(report["rows_by_year"]["2022"]>0)
        self.assertFalse(report["promotion_gate"]["promote_to_formal_forecast"])
        for y in ("2018","2022"):
            self.assertGreater(report["scores"][y]["all_counties"]["models"]["t3_blend_pct"]["n"],0)
            self.assertGreater(report["scores"][y]["nonmajor_present_unique_pair"]["models"]["t3_blend_pct"]["n"],0)
            rows=[x for x in report["rows"] if x["year"]==int(y)]
            self.assertTrue(all(max(x["training_years"])<x["year"] for x in rows))
            self.assertTrue(all(0 <= x["actual_pct"] <= 100 for x in rows))
            self.assertTrue(all(0 <= x["t3_blend_pct"] <= 100 for x in rows))


if __name__=="__main__": unittest.main()
