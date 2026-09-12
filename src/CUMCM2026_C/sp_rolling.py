"""Plan-3 rolling multi-stage stochastic planner for question 3 (and 4-3).

At each PV-forecast release (0/6/12/18h) the planner solves one scenario LP
for the REMAINING intervals of the day:

* shared decisions: adjusted purchase, charge, discharge, SOC path;
* per-scenario recourse: emergency purchase (5x), curtailment (<= scenario
  PV), unused plan (free -- the plan is prepaid);
* from the second release on, the adjustment tariffs vs the 0:00 plan enter
  the objective (0.5x down / 1.5x up); the 0:00 plan itself is prepaid and
  its cost appears only in the first release's objective.

Scenarios resample whole error DAYS, causally:
* PV errors come from the release-specific attachment-3 forecast error
  history (actual - released forecast, per 0/6/12/18 release hour; January
  days are legitimate history because their forecasts exist);
* load: zeros in the main (known-daily-load) reading; in the strict variant
  they come from the SARIMA load error history as in question 2.

Execution inherits the trajectory-guarded adaptive storage of the adopted
question-2 pipeline.
"""
from __future__ import annotations

import json
import time
from datetime import date

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

from . import io_attachments as io, paths
from .dispatch import Policy, run, forecast_vector
from .sp_plan import build_inputs, score, VALID, TEST

DT = paths.INTERVAL_MINUTES / 60
ETA = paths.STORAGE.efficiency
CAP = paths.STORAGE.max_energy_per_interval_charge
LO, HI = paths.STORAGE.soc_min_kwh, paths.STORAGE.soc_max_kwh
N = paths.INTERVALS_PER_DAY


def sp_solve(price, load_kw, pv_kw, initial_soc, terminal_soc,
             scen_load, scen_pv, lam=1.0, original_plan=None, scen_price=None):
    """Scenario LP over the remaining-day horizon (n = len(price)).

    scen_price: optional (K, n) scenario prices.  First-stage quantities
    (plan / adjustments) are settled at realised trade-time prices, so their
    expected cost uses the scenario mean price; the scenario-dependent
    emergency recourse is priced per scenario (5x)."""
    K = scen_load.shape[0]
    n = len(price)
    if scen_price is None:
        scen_price = np.broadcast_to(np.asarray(price, float), (K, n))
    mean_price = scen_price.mean(axis=0)
    adj = original_plan is not None
    nQ, nC, nD, nS = 0, n, 2 * n, 3 * n
    nU = 4 * n + 1                                   # only when adj
    baseZ = (6 * n + 1) if adj else (4 * n + 1)
    size = baseZ + 3 * n * K

    lk = np.maximum(load_kw + lam * scen_load, 0.0) * DT
    pk = np.maximum(pv_kw + lam * scen_pv, 0.0) * DT
    net = lk - pk

    obj = np.zeros(size)
    if adj:
        obj[nU:nU + n] = 1.5 * mean_price            # up-adjustment
        obj[nU + n:nU + 2 * n] = 0.5 * mean_price    # down-adjustment penalty
    else:
        obj[nQ:nQ + n] = mean_price                  # prepaid 0:00 plan
    for k in range(K):
        obj[baseZ + 3 * n * k: baseZ + 3 * n * k + n] = (5.0 / K) * scen_price[k]

    rows, cols, vals = [], [], []

    def add(r, c, v):
        rows.append(r); cols.append(c); vals.append(v)

    tt = np.arange(n)
    for k in range(K):
        r0 = k * n + tt
        off = baseZ + 3 * n * k
        add(r0, nQ + tt, np.ones(n)); add(r0, nD + tt, np.ones(n))
        add(r0, nC + tt, -np.ones(n))
        add(r0, off + tt, np.ones(n))                # z: emergency
        add(r0, off + n + tt, -np.ones(n))           # g: curtail
        add(r0, off + 2 * n + tt, -np.ones(n))       # w: unused plan
    rsoc = K * n + tt
    add(rsoc, nS + tt + 1, np.ones(n)); add(rsoc, nS + tt, -np.ones(n))
    add(rsoc, nC + tt, -ETA * np.ones(n)); add(rsoc, nD + tt, (1 / ETA) * np.ones(n))
    if adj:
        radj = K * n + n + tt
        add(radj, nQ + tt, np.ones(n)); add(radj, nU + tt, -np.ones(n))
        add(radj, nU + n + tt, np.ones(n))
    nrow = K * n + n + (n if adj else 0)
    A = coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                   shape=(nrow, size)).tocsc()
    rhs = np.concatenate([net.ravel(), np.zeros(n),
                          np.asarray(original_plan, float) if adj else np.zeros(0)])

    ub = coo_matrix((np.ones(2 * n),
                     (np.concatenate([tt, tt]), np.concatenate([nC + tt, nD + tt]))),
                    shape=(n, size)).tocsc()

    bounds = ([(0.0, None)] * n + [(0.0, CAP)] * n + [(0.0, CAP)] * n
              + [(initial_soc, initial_soc)] + [(LO, HI)] * (n - 1)
              + [(terminal_soc, terminal_soc)])
    if adj:
        bounds += [(0.0, None)] * n + [(0.0, None)] * n
    for k in range(K):
        bounds += ([(0.0, None)] * n
                   + [(0.0, float(v)) for v in pk[k]]
                   + [(0.0, None)] * n)

    res = linprog(obj, A_eq=A, b_eq=rhs, A_ub=ub, b_ub=np.full(n, CAP),
                  bounds=bounds, method="highs")
    if not res.success:
        raise RuntimeError(res.message)
    z = np.where(np.abs(res.x) < 1e-9, 0.0, res.x)
    return {"purchase": z[nQ:nQ + n], "charge": z[nC:nC + n],
            "discharge": z[nD:nD + n], "soc": z[nS:nS + n + 1],
            "objective_yuan": float(obj @ z)}


def build_pv_release_errors():
    """err[h][d] = actual_pv[d, 6h:144] - released_forecast_{d,h}[6h:144]."""
    a1, a2, a3, a4 = io.load_all()
    pv = np.asarray([np.asarray(r, float) for r in a2.pv_actual])
    out = {}
    for h in (0, 6, 12, 18):
        arr = np.full((len(a2.dates), 144 - 6 * h), np.nan)
        for d, day in enumerate(a2.dates):
            fv = forecast_vector(a3, day, h, scale=1.0)
            arr[d] = pv[d, 6 * h:] - fv[6 * h:]
        assert np.isfinite(arr).all()
        out[h] = arr
    return out


def make_rolling_planner(pv_err, load_err=None, K=200, lam=1.0):
    """load_err None -> known-load reading (zero load scenarios)."""

    def plan_fn(price, load_kw, pv_kw, initial_soc, original_plan, terminal_soc,
                i, start):
        n = len(price)
        h = start // 6
        rng = np.random.default_rng(2_000_003 + 57 * i + h)
        hist = pv_err[h][:i]                          # strictly past days
        if hist.shape[0]:
            sp_ = hist[rng.choice(hist.shape[0], size=K, replace=True)]
        else:
            sp_ = np.zeros((K, n))                    # first-day degenerate
        if load_err is None:
            sl = np.zeros((K, n))
        else:
            lh = load_err[31:i, start:]
            sl = (lh[rng.choice(lh.shape[0], size=K, replace=True)]
                  if lh.shape[0] else np.zeros((K, n)))
        return sp_solve(price, load_kw, pv_kw, initial_soc, terminal_soc,
                        sl, sp_, lam, original_plan)

    return plan_fn


def run_variant(tag, strict_load=False, K=200, lam=1.0):
    inputs = build_inputs() if strict_load else None
    pv_err = build_pv_release_errors()
    kwargs = {}
    if strict_load:
        lm = inputs["lm"]
        load_err = inputs["err_load"]

        def load_pred(i):
            return np.maximum(lm[i], 0.0)

        kwargs["load_predictor"] = load_pred
        planner = make_rolling_planner(pv_err, load_err=load_err, K=K, lam=lam)
    else:
        planner = make_rolling_planner(pv_err, load_err=None, K=K, lam=lam)
    policy = Policy(pv_scale=1.0, known_daily_load=not strict_load)
    t0 = time.time()
    r = run("3", policy=policy, plan_fn=planner, adaptive_storage=True, **kwargs)
    s = r["summary"]
    val, test = score(r["daily"], VALID), score(r["daily"], TEST)
    print(f"[{tag}] year={s['total_cost_yuan']:,.0f} val={val:,.0f} test={test:,.0f} "
          f"emg={s['emergency_kwh']:,.0f} plan={s['plan_purchase_kwh']:,.0f} "
          f"final={s['final_purchase_kwh']:,.0f} ({time.time()-t0:.0f}s)", flush=True)
    return r


def main() -> int:
    import sys
    strict = "--strict" in sys.argv
    r = run_variant("Q3-SP known-load" if not strict else "Q3-SP strict-load",
                    strict_load=strict)
    out = paths.PROCESSED_DIR / ("problem3_sp_strict.json" if strict
                                 else "problem3_sp_known_load.json")
    out.write_text(json.dumps({"model": r["model"], "summary": r["summary"],
                               "daily": r["daily"]}, ensure_ascii=False),
                   encoding="utf-8")
    print("saved ->", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
