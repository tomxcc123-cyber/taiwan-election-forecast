"""Import a provided registration workbook without editing it or fetching external links."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from model.data import load_dataset
from model.roster import import_workbook, roster_summary


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("workbook", type=Path)
    p.add_argument("--as-of", required=True)
    p.add_argument("--output", type=Path, default=ROOT / "data/registration-roster-2026.json")
    args = p.parse_args()
    data = import_workbook(args.workbook, load_dataset(ROOT / "data/candidate-history.json"), args.as_of)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
    print(json.dumps(roster_summary(data), ensure_ascii=False))
