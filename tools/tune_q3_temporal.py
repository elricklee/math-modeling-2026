"""Select causal Q3 parameters on a temporal validation split.

The test period is evaluated only after the validation winner is selected.
The daily terminal SOC is fixed at 6000 kWh by the question boundary.
"""
from __future__ import annotations

import itertools
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.CUMCM2026_C.dispatch import Policy, run

TRAIN = (date(2025, 2, 1), date(2025, 6, 30))
VALID = (date(2025, 7, 1), date(2025, 9, 30))
TEST = (date(2025, 10, 1), date(2025, 12, 31))


def score(records, period):
    lo, hi = period
    rs = [r for r in records if lo.isoformat() <= r["date"] <= hi.isoformat()]
    return {"days": len(rs),
            "total_cost_yuan": float(sum(r["total_cost_yuan"] for r in rs)),
            "emergency_kwh": float(sum(r["emergency_kwh"] for r in rs)),
            "adjustment_cost_yuan": float(sum(r["adjustment_cost_yuan"] for r in rs))}


def main():
    rows = []
    # Q3 has its own optimization objective, so select its parameters
    # independently from Q2.  pv_scale=1 is retained as the unbiased forecast
    # baseline; only history window/load quantile are tuned here.
    for window, lq in itertools.product((14, 28, 42), (0.7, 0.8, 0.9, 1.0)):
        policy = Policy(history_days=window, load_quantile=lq,
                        historical_pv_quantile=0.2, pv_scale=1.0,
                        terminal_target_kwh=6000.0, known_daily_load=True)
        result = run("3", policy=policy)
        rows.append({"policy": {"history_days": window, "load_quantile": lq,
                                 "historical_pv_quantile": 0.2,
                                 "pv_scale": 1.0, "terminal_target_kwh": 6000.0},
                     "train": score(result["daily"], TRAIN),
                     "validation": score(result["daily"], VALID),
                     "test": score(result["daily"], TEST)})
        print(window, lq, rows[-1]["validation"], flush=True)
    rows.sort(key=lambda x: (x["validation"]["total_cost_yuan"],
                             x["validation"]["emergency_kwh"]))
    payload = {"split": {"train": [d.isoformat() for d in TRAIN],
                          "validation": [d.isoformat() for d in VALID],
                          "test": [d.isoformat() for d in TEST]},
               "selection_metric": "validation total settlement cost",
               "best": rows[0], "all_candidates": rows}
    out = Path("data/processed/CUMCM2026_C/q3_temporal_policy_tuning.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"best": rows[0], "output": str(out)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
