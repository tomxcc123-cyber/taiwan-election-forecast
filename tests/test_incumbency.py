import unittest

from model.incumbency import build_incumbency_map, infer_incumbent_party


class IncumbencyTests(unittest.TestCase):
    def _history(self):
        return [
            {"race_id": "r2014", "county_id": "c1", "county": "X", "office": "local_executive", "year": 2014,
             "candidates": [
                 {"name": "A", "party": "DPP", "winner": True},
                 {"name": "B", "party": "KMT", "winner": False},
             ]},
            {"race_id": "r2018", "county_id": "c1", "county": "X", "office": "local_executive", "year": 2018,
             "candidates": [
                 {"name": "A", "party": "DPP", "winner": True},
                 {"name": "C", "party": "KMT", "winner": False},
             ]},
            {"race_id": "r2022", "county_id": "c1", "county": "X", "office": "local_executive", "year": 2022,
             "candidates": [
                 {"name": "D", "party": "DPP", "winner": False},
                 {"name": "E", "party": "KMT", "winner": True},
             ]},
        ]

    def test_prior_regular_winner_reappearing_is_incumbent(self):
        history = self._history()
        party, audit = infer_incumbent_party(history[1], history)
        self.assertEqual(party, "DPP")
        self.assertEqual(audit["method"], "prior_regular_winner_reappears")

    def test_open_seat_is_not_inferred_from_party_control(self):
        history = self._history()
        party, audit = infer_incumbent_party(history[2], history)
        self.assertIsNone(party)
        self.assertEqual(audit["method"], "open_seat_or_no_exact_incumbent")

    def test_explicit_by_election_override_wins(self):
        history = self._history()
        party, audit = infer_incumbent_party(
            history[2], history,
            overrides={"r2022": {"party": "DPP", "candidate": "D", "reason": "by-election"}})
        self.assertEqual(party, "DPP")
        self.assertEqual(audit["method"], "explicit_override")

    def test_map_contains_only_verified_or_inferred_incumbents(self):
        history = self._history()
        mapping, audit = build_incumbency_map(history)
        self.assertEqual(mapping, {"r2018": "DPP"})
        self.assertEqual(len(audit), 3)


if __name__ == "__main__":
    unittest.main()
