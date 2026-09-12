"""Plan 3: two-stage stochastic-programming planner for question 2.

Replaces only the 0:00 planning step of the pipeline:

* The scenario centre is the variant-A SARIMA median forecast (z = 0).
* Scenarios are whole error DAYS resampled from the causal history
  ``actual_d - forecast_d`` of that same SARIMA (load and PV errors of one
  historical day are resampled jointly, preserving intra-day correlation);
  errors from days >= the planning day are never touched.
* The planner solves one LP over the shared day plan (purchase, charge,
  discharge, SOC) plus per-scenario recourse (emergency purchase at 5x,
  curtailment), minimising the expected settlement cost.  The shared power
  cap ``x_t + y_t <= 833.33`` forbids simultaneous charge/discharge.
* Execution, SOC carry-over and settlement are the untouched dispatch code.

Tuned on the same validation split as plans 1 and 2: scenario count K,
error-history window, tail inflation lambda.
"""
from __future__ import annotations

import json
import time
from datetime import date

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix

from . import io_attachments as io, paths
from .dispatch import Policy, run
from .sarima_plan import VARIANTS, load_cache, sanitize

DT = paths.INTERVAL_MINUTES / 60
ETA = paths.STORAGE.efficiency
CAP = paths.STORAGE.max_energy_per_interval_charge
LO, HI = paths.STORAGE.soc_min_kwh, paths.STORAGE.soc_max_kwh
N = paths.INTERVALS_PER_DAY
START = 31

VALID = (date(2025, 7, 1), date(2025, 9, 30))
TEST = (date(2025, 10, 1), date(2025, 12, 31))


def build_inputs():
    a1, a2, a3, a4 = io.load_all()
    load = np.asarray([np.asarray(r, float) for r in a2.load])
    pv = np.asarray([np.asarray(r, float) for r in a2.pv_actual])
    lm, ls, _ = load_cache("load", "A")
    lm, ls, _ = sanitize(lm, ls, load, VARIANTS["A"]["window"], None)
    pm, ps, _ = load_cache("pv", "A")
    pm, ps, _ = sanitize(pm, ps, pv, VARIANTS["A"]["window"], "sqrt")
    pv_point = np.maximum(pm ** 2, 0.0)
    return dict(load=load, pv=pv, lm=lm, ls=ls, pm=pm, ps=ps,
                pv_point=pv_point,
                err_load=load - lm,           # rows >= START are meaningful
                err_pv=pv - pv_point)


def sp_plan(price, load_kw, pv_kw, initial_soc, terminal_soc,
            scen_load, scen_pv, lam=1.0):
    """One SP LP.  scen_*: (K, 144) kW error curves around load_kw/pv_kw."""
    K = scen_load.shape[0]
    nQ, nC, nD, nS = 0, N, 2 * N, 3 * N
    baseZ = 3 * N + N + 1
    size = 3 * N + (N + 1) + 3 * N * K   # per scenario: emergency z, curtail g, unused w

    lk = np.maximum(load_kw[None, :] + lam * scen_load, 0.0) * DT   # (K,144) kWh
    pk = np.maximum(pv_kw[None, :] + lam * scen_pv, 0.0) * DT
    net = lk - pk

    # objective: price on plan purchase, (5/K)*price on each scenario's emergency.
    # w (plan bought but not needed) carries no extra cost: the plan is prepaid.
    obj = np.zeros(size)
    obj[nQ:nQ + N] = price
    for k in range(K):
        obj[baseZ + 3 * N * k: baseZ + 3 * N * k + N] = (5.0 / K) * price

    rows, cols, vals = [], [], []

    def add(r, c, v):
        rows.append(r); cols.append(c); vals.append(v)

    tt = np.arange(N)
    for k in range(K):
        r0 = k * N + tt
        off = baseZ + 3 * N * k
        add(r0, nQ + tt, np.ones(N)); add(r0, nD + tt, np.ones(N))
        add(r0, nC + tt, -np.ones(N))
        add(r0, off + tt, np.ones(N))          # z
        add(r0, off + N + tt, -np.ones(N))     # g (<= scenario PV)
        add(r0, off + 2 * N + tt, -np.ones(N)) # w (unused plan, unbounded)
    rsoc = N * K + tt
    add(rsoc, nS + tt + 1, np.ones(N)); add(rsoc, nS + tt, -np.ones(N))
    add(rsoc, nC + tt, -ETA * np.ones(N)); add(rsoc, nD + tt, (1 / ETA) * np.ones(N))
    eq = coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                    shape=(N * K + N, size)).tocsc()
    rhs = np.concatenate([net.ravel(), np.zeros(N)])

    rows, cols, vals = [], [], []
    add(tt, nC + tt, np.ones(N)); add(tt, nD + tt, np.ones(N))
    ub = coo_matrix((np.concatenate(vals), (np.concatenate(rows), np.concatenate(cols))),
                    shape=(N, size)).tocsc()

    bounds = ([(0.0, None)] * N + [(0.0, CAP)] * N + [(0.0, CAP)] * N
              + [(initial_soc, initial_soc)] + [(LO, HI)] * (N - 1)
              + [(terminal_soc, terminal_soc)])
    for k in range(K):
        bounds += ([(0.0, None)] * N                      # z: emergency
                   + [(0.0, float(v)) for v in pk[k]]     # g: curtail <= scenario PV
                   + [(0.0, None)] * N)                   # w: unused plan

    res = linprog(obj, A_eq=eq, b_eq=rhs, A_ub=ub, b_ub=np.full(N, CAP),
                  bounds=bounds, method="highs")
    if not res.success:
        raise RuntimeError(res.message)
    z = np.where(np.abs(res.x) < 1e-9, 0.0, res.x)
    return {"purchase": z[nQ:nQ + N], "charge": z[nC:nC + N],
            "discharge": z[nD:nD + N], "curtail": np.zeros(N), "unused": np.zeros(N),
            "soc": z[nS:nS + N + 1], "objective_yuan": float(obj @ z),
            "simultaneous": int(np.sum((z[nC:nC + N] > 1e-6) & (z[nD:nD + N] > 1e-6)))}


def make_planner(inputs, K=50, err_window=None, lam=1.0):
    lm, ls = inputs["lm"], inputs["ls"]
    pm, ps, pv_point = inputs["pm"], inputs["ps"], inputs["pv_point"]
    err_load, err_pv = inputs["err_load"], inputs["err_pv"]
    holder = {"i": 0}

    def load_pred(i):
        holder["i"] = i
        return np.maximum(lm[i], 0.0)

    def pv_pred(i):
        return pv_point[i]

    def plan_fn(price, load_kw, pv_kw, initial_soc, original_plan, terminal_soc,
                day_index=None, start=None):
        i = holder["i"]
        rng = np.random.default_rng(1_000_003 + i)     # fixed per day
        past = list(range(START, i))
        if err_window is not None:
            past = past[-err_window:]
        if past:
            pick = rng.choice(len(past), size=K, replace=True)
            days = [past[j] for j in pick]
            sl = np.stack([err_load[d] for d in days])
            sp = np.stack([err_pv[d] for d in days])
        else:                                            # cold start day
            sl = np.stack([rng.normal(0.0, np.maximum(ls[i], 1.0)) for _ in range(K)])
            sp = np.stack([rng.normal(0.0, 2 * np.maximum(pm[i], 0.0) * ps[i] + 1.0)
                           for _ in range(K)])
        return sp_plan(price, load_kw, pv_kw, initial_soc, terminal_soc, sl, sp, lam)

    return load_pred, pv_pred, plan_fn


def score(records, period):
    lo, hi = period
    sel = [r for r in records if lo.isoformat() <= r["date"] <= hi.isoformat()]
    return sum(r["total_cost_yuan"] for r in sel)


def main() -> int:
    inputs = build_inputs()
    configs = [
        dict(K=50, err_window=None, lam=1.0),
        dict(K=50, err_window=None, lam=1.15),
        dict(K=50, err_window=90, lam=1.0),
        dict(K=50, err_window=90, lam=1.15),
        dict(K=30, err_window=None, lam=1.0),
        dict(K=50, err_window=None, lam=1.3),
        dict(K=50, err_window=None, lam=1.5),
        dict(K=100, err_window=None, lam=1.15),
        dict(K=100, err_window=None, lam=1.0),
        dict(K=100, err_window=None, lam=1.3),
        dict(K=200, err_window=None, lam=1.15),
    ]
    rows = []
    for cfg in configs:
        t0 = time.time()
        lp, pp, pf = make_planner(inputs, **cfg)
        r = run("2", policy=Policy(pv_scale=1.0),
                load_predictor=lp, pv_predictor=pp, plan_fn=pf)
        s = r["summary"]
        val, test = score(r["daily"], VALID), score(r["daily"], TEST)
        rows.append({"cfg": cfg, "year": s["total_cost_yuan"], "val": val,
                     "test": test, "emg": s["emergency_kwh"],
                     "runtime_s": round(time.time() - t0, 1)})
        print(f"{cfg}: year={s['total_cost_yuan']:,.0f} val={val:,.0f} "
              f"test={test:,.0f} emg={s['emergency_kwh']:,.0f} "
              f"({rows[-1]['runtime_s']}s)", flush=True)
    best = min(rows, key=lambda x: x["val"])
    payload = {"plan": "SP over SARIMA-A errors", "rows": rows,
               "validation_best": best,
               "reference": {"plan1_default": 15780940.73,
                             "plan1_valbest": 15735295,
                             "plan2_A": 15197005, "plan2_A_val": 4366838,
                             "plan2_B_valbest": 15268464}}
    out = paths.PROCESSED_DIR / "sp_vs_plans.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nvalidation-best {best['cfg']}: val={best['val']:,.0f} "
          f"year={best['year']:,.0f} test={best['test']:,.0f}")
    print(f"saved -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
