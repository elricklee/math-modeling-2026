"""Plan-3 volatile-price variants for questions 4-2 and 4-3.

Rulings (2026-09-13):
* Price information is causal, like load: at any decision moment only the
  realised price curve up to now is known; future prices are forecast from
  history (per-interval same-weekday median over the last 28 days -- the
  same ``history_prediction`` the engine uses, so centre and error history
  share one forecaster definition).
* Settlement of planned, adjusted and emergency energy is at realised
  trade-time prices (emergency at 5x).  Price forecast errors therefore hit
  the bill directly; forecasting only decides WHEN to buy.
* 4-2 keeps the question-2 information structure (own SARIMA PV); 4-3 uses
  attachment-3 releases and the strict (load-forecast) reading.

Scenarios resample (load, pv, price) error days JOINTLY -- the same
historical day feeds all three -- preserving the load-price correlation
(daily-total vs daily-mean-price r = +0.898).  At 6/12/18 releases the
remaining-day price centre is level-shifted by the mean bias of realised
vs forecast elapsed prices.
"""
from __future__ import annotations

import json
import time

import numpy as np

from . import io_attachments as io, paths
from .dispatch import Policy, run, history_prediction
from .sp_plan import build_inputs, score, VALID, TEST
from .sp_rolling import build_pv_release_errors, sp_solve

START = 31


def build_price_history():
    """Causal per-interval median price forecast for every day + its errors."""
    a1, a2, a3, a4 = io.load_all()
    price = np.asarray([np.asarray(r, float) for r in a4.price])
    center = np.zeros_like(price)
    for i in range(len(a4.dates)):
        center[i] = history_prediction(a4.price, i, a4.dates, 0.5, 28, 1.0)
    return price, center, price - center


def make_q42_planner(inputs, price_err, K=200, lam=1.0):
    lm, pv_point = inputs["lm"], inputs["pv_point"]
    err_load, err_pv = inputs["err_load"], inputs["err_pv"]

    def load_pred(i):
        return np.maximum(lm[i], 0.0)

    def pv_pred(i):
        return pv_point[i]

    def plan_fn(price, load_kw, pv_kw, initial_soc, original_plan, terminal_soc,
                i, start):
        n = len(price)
        rng = np.random.default_rng(3_000_003 + i)
        past = list(range(START, i))
        if not past:
            sl = np.zeros((K, n)); spv = np.zeros((K, n))
            sc = np.tile(np.maximum(price, 0.0), (K, 1))
        else:
            days = [past[j] for j in rng.choice(len(past), size=K, replace=True)]
            sl = err_load[days]
            spv = err_pv[days]
            sc = np.maximum(price[None, :] + lam * price_err[days, :], 0.0)
        return sp_solve(price, load_kw, pv_kw, initial_soc, terminal_soc,
                        sl, spv, lam, original_plan, scen_price=sc)

    return load_pred, pv_pred, plan_fn


def make_q43_planner(inputs, price, price_center, price_err, pv_err, K=200, lam=1.0):
    lm, err_load = inputs["lm"], inputs["err_load"]

    def load_pred(i):
        return np.maximum(lm[i], 0.0)

    def plan_fn(pcenter, load_kw, pv_kw, initial_soc, original_plan, terminal_soc,
                i, start):
        n = len(pcenter)
        h = start // 6
        rng = np.random.default_rng(4_000_003 + 57 * i + h)
        # remaining-day price centre, level-shifted by realised elapsed bias
        if start == 0:
            pc = np.maximum(price_center[i], 0.0)
        else:
            bias = float(np.mean(price[i, :start] - price_center[i, :start]))
            pc = np.maximum(price_center[i, start:] + bias, 0.0)
        past = list(range(START, i))
        if not past:
            sl = np.zeros((K, n)); spv = np.zeros((K, n))
            sc = np.tile(pc, (K, 1))
        else:
            days = [past[j] for j in rng.choice(len(past), size=K, replace=True)]
            sl = err_load[days, start:]
            spv = pv_err[h][days]
            sc = np.maximum(pc[None, :] + lam * price_err[days, start:], 0.0)
        return sp_solve(pc, load_kw, pv_kw, initial_soc, terminal_soc,
                        sl, spv, lam, original_plan, scen_price=sc)

    return load_pred, plan_fn


def run_variant(question, K=200, lam=1.0):
    inputs = build_inputs()
    price, price_center, price_err = build_price_history()
    t0 = time.time()
    if question == "4-2":
        lp, pp, pf = make_q42_planner(inputs, price_err, K=K, lam=lam)
        r = run("4-2", policy=Policy(pv_scale=1.0),
                load_predictor=lp, pv_predictor=pp, plan_fn=pf,
                adaptive_storage=True)
    else:
        pv_err = build_pv_release_errors()
        lp, pf = make_q43_planner(inputs, price, price_center, price_err, pv_err,
                                  K=K, lam=lam)
        r = run("4-3", policy=Policy(pv_scale=1.0),
                load_predictor=lp, plan_fn=pf, adaptive_storage=True)
    s = r["summary"]
    val, test = score(r["daily"], VALID), score(r["daily"], TEST)
    print(f"[{question}] year={s['total_cost_yuan']:,.0f} val={val:,.0f} "
          f"test={test:,.0f} emg={s['emergency_kwh']:,.0f} "
          f"plan={s['plan_purchase_kwh']:,.0f} final={s['final_purchase_kwh']:,.0f} "
          f"({time.time()-t0:.0f}s)", flush=True)
    out = paths.PROCESSED_DIR / f"problem{question.replace('-', '_')}_sp.json"
    out.write_text(json.dumps(r, ensure_ascii=False), encoding="utf-8")
    print("saved ->", out, flush=True)
    return r


def main() -> int:
    import sys
    q = "4-3" if "--q3" in sys.argv else "4-2"
    run_variant(q)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
