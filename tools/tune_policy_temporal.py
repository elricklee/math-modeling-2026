"""Temporal train/validation/test tuning for the causal dispatch policy.

The search never uses test-period realized costs to choose parameters.  Each
candidate is evaluated with the same causal information structure as the main
solver; only the date-range aggregate used for ranking changes.
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
    selected = [r for r in records if lo.isoformat() <= r["date"] <= hi.isoformat()]
    if not selected:
        raise ValueError(period)
    keys = ("total_cost_yuan", "emergency_kwh", "plan_purchase_kwh")
    return {k: float(sum(r[k] for r in selected)) for k in keys} | {"days": len(selected)}


def main():
    # Small, interpretable grid.  The validation objective is total settlement
    # cost; emergency energy is retained for tie-breaking and reporting.
    grid = itertools.product(
        (14, 28, 42),       # history_days
        (0.6, 0.8, 0.9),    # load quantile
        (0.1, 0.2, 0.3),    # historical PV quantile
        (6000.0,),          # fixed by the question's daily boundary condition
    )
    rows = []
    for n, (window, lq, pq, terminal) in enumerate(grid, 1):
        policy = Policy(history_days=window, load_quantile=lq,
                        historical_pv_quantile=pq,
                        terminal_target_kwh=terminal)
        result = run("2", policy=policy)
        recs = result["daily"]
        train = score(recs, TRAIN)
        valid = score(recs, VALID)
        test = score(recs, TEST)
        rows.append({"policy": {"history_days": window,
                                 "load_quantile": lq,
                                 "historical_pv_quantile": pq,
                                 "terminal_target_kwh": terminal},
                     "train": train, "validation": valid, "test": test})
        print(f"{n}: {window}/{lq}/{pq}/{terminal} -> "
              f"val={valid['total_cost_yuan']:.2f}, emg={valid['emergency_kwh']:.2f}",
              flush=True)
    rows.sort(key=lambda x: (x["validation"]["total_cost_yuan"],
                             x["validation"]["emergency_kwh"]))
    best = rows[0]
    payload = {"split": {"train": [d.isoformat() for d in TRAIN],
                          "validation": [d.isoformat() for d in VALID],
                          "test": [d.isoformat() for d in TEST]},
               "selection_metric": "validation total settlement cost",
               "best": best, "all_candidates": rows}
    out = Path("data/processed/CUMCM2026_C/temporal_policy_tuning.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"best": best, "output": str(out)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
