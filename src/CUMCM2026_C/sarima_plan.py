"""SARIMA day-ahead predictors for question 2 -- comparison against the
built-in similar-day quantile forecasts.

Design (kept strictly causal, mirroring ``dispatch.history_prediction``):

* For each of the 144 ten-minute intervals, the past days of that interval
  form a daily series.  A SARIMA(p,0,q)x(P,0,Q)_7 is refit every
  ``REFIT_EVERY`` days on a rolling window (max ``window`` days, strictly
  before the forecast block) and produces the multi-step forecasts for the
  days up to the next refit; ``get_forecast`` supplies the h-step mean and
  standard error.
* Differencing orders are kept at d=D=0: the rolling window already removes
  slow level drift, and integrated models on 31--182 observations proved
  unstable in benchmarking.
* Quantile forecasts are ``mean + z * se`` with z tuned on the same
  validation split used by the original quantile search.  Load is modeled on
  the raw kW scale; PV is modeled on a sqrt scale (variance stabilisation for
  a zero-bounded, right-skewed series) and the quantile is clipped at zero
  *before* squaring back, so a negative sqrt-quantile cannot invert the
  conservatism.
* Night PV intervals (all-zero window) are assigned 0 / 0 without fitting.
* Any fit failure falls back to the window mean/std and is counted.

Only steps 1--2 of the pipeline are replaced: the LP, physical replay and
settlement are the untouched ``dispatch`` implementations.
"""
from __future__ import annotations

import argparse
import json
import time
import warnings
from datetime import date
from pathlib import Path

import numpy as np

from . import io_attachments as io, paths
from .dispatch import Policy, history_prediction, run

START = 31                     # first forecast day: 2025-02-01 (index 31)
REFIT_EVERY = 7                # weekly refit cadence
VALID = (date(2025, 7, 1), date(2025, 9, 30))
TEST = (date(2025, 10, 1), date(2025, 12, 31))

VARIANTS = {
    "A":   dict(order=(1, 0, 0), seasonal=(1, 0, 0, 7), window=182),
    "A90": dict(order=(1, 0, 0), seasonal=(1, 0, 0, 7), window=90),
    "B":   dict(order=(2, 0, 1), seasonal=(1, 0, 1, 7), window=182),
}

Z_LOAD = (0.25, 0.52, 0.84, 1.28, 1.64, 2.05)       # ~ .60 .70 .80 .90 .95 .98
Z_PV = (0.25, 0.0, -0.52, -0.84, -1.28, -1.64)      # ~ .60 .50 .30 .20 .10 .05


def cache_path(kind: str, variant: str) -> Path:
    return paths.PROCESSED_DIR / f"sarima_cache_{kind}_{variant}.npz"


def precompute(values: np.ndarray, order, seasonal, window, transform,
               refit_every=REFIT_EVERY, start=START):
    """Return (mean, se, fallback_count) with rows indexed by day index."""
    from statsmodels.tsa.statespace.sarimax import SARIMAX

    n_days, n_int = values.shape
    mean = np.zeros((n_days, n_int))
    se = np.zeros((n_days, n_int))
    fallback = 0
    for t in range(n_int):
        col = values[:, t]
        i0 = start
        while i0 < n_days:
            stop = min(i0 + refit_every, n_days)
            steps = stop - i0
            y = col[max(0, i0 - window):i0].astype(float)
            if transform == "sqrt":
                y = np.sqrt(y)
            if y.size < 14 or y.max() == y.min():
                m = float(y.mean()) if y.size else 0.0
                mean[i0:stop, t] = m
                i0 = stop
                continue
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    res = SARIMAX(y, order=order, seasonal_order=seasonal,
                                  enforce_stationarity=False,
                                  enforce_invertibility=False,
                                  concentrate_scale=True).fit(disp=False, maxiter=50)
                    fr = res.get_forecast(steps)
                    mu = np.asarray(fr.predicted_mean, float)
                    s = np.asarray(fr.se_mean, float)
                if not (np.isfinite(mu).all() and np.isfinite(s).all()
                        and (s >= 0).all()):
                    raise RuntimeError("nonfinite forecast")
                # Guard against near-unit-root fits whose h-step forecasts
                # explode (observed for richer orders on short windows).
                lo, hi = y.mean() - 10 * y.std(), y.mean() + 10 * y.std()
                if np.any(mu < lo) or np.any(mu > hi) or np.any(s > hi - y.mean()):
                    raise RuntimeError("forecast outside physical envelope")
            except Exception:
                fallback += 1
                mu = np.full(steps, y.mean())
                s = np.full(steps, y.std())
            mean[i0:stop, t] = mu
            se[i0:stop, t] = s
            i0 = stop
    return mean, se, fallback


def run_precompute(variant: str) -> None:
    cfg = VARIANTS[variant]
    a1, a2, a3, a4 = io.load_all()
    load = np.asarray([np.asarray(r, float) for r in a2.load])
    pv = np.asarray([np.asarray(r, float) for r in a2.pv_actual])
    out = {}
    for kind, arr, transform in (("load", load, None), ("pv", pv, "sqrt")):
        t0 = time.time()
        mean, se, fb = precompute(arr, cfg["order"], cfg["seasonal"],
                                  cfg["window"], transform)
        print(f"[{variant}/{kind}] fallback={fb} elapsed={time.time()-t0:.0f}s",
              flush=True)
        p = cache_path(kind, variant)
        p.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(p, mean=mean, se=se, fallback=fb)
        out[kind] = dict(fallback=fb, path=str(p))
    print(json.dumps(out))


def load_cache(kind: str, variant: str):
    z = np.load(cache_path(kind, variant))
    return z["mean"], z["se"], int(z["fallback"])


def sanitize(mean, se, values, window, transform, start=START):
    """Post-hoc equivalent of the in-fit envelope guard for already-cached
    predictions: any cell whose mean/se leaves the causal-window mean±10σ
    envelope falls back to that window's mean/std -- identical policy to the
    precompute fallback, so caches computed before the guard stay usable."""
    n_days, n_int = values.shape
    patched = 0
    for t in range(n_int):
        col = values[:, t].astype(float)
        if transform == "sqrt":
            col = np.sqrt(col)
        for i in range(start, n_days):
            y = col[max(0, i - window):i]
            ystd = float(y.std()) if y.size >= 2 else 0.0
            ymean = float(y.mean()) if y.size else 0.0
            m, s = mean[i, t], se[i, t]
            if (not np.isfinite(m) or not np.isfinite(s)
                    or m < ymean - 10 * ystd or m > ymean + 10 * ystd
                    or s > 10 * ystd):
                mean[i, t] = ymean
                se[i, t] = ystd
                patched += 1
    return mean, se, patched


def make_load_predictor(mean, se, z):
    def predict(i):
        return np.maximum(mean[i] + z * se[i], 0.0)
    return predict


def make_pv_predictor(mean, se, z):
    def predict(i):
        q_sqrt = np.maximum(mean[i] + z * se[i], 0.0)
        return q_sqrt ** 2
    return predict


def score(records, period):
    lo, hi = period
    sel = [r for r in records if lo.isoformat() <= r["date"] <= hi.isoformat()]
    return {"total": sum(r["total_cost_yuan"] for r in sel),
            "emg_kwh": sum(r["emergency_kwh"] for r in sel)}


def run_grid() -> dict:
    a1, a2, a3, a4 = io.load_all()
    load = np.asarray([np.asarray(r, float) for r in a2.load])
    pv = np.asarray([np.asarray(r, float) for r in a2.pv_actual])
    dates = a2.dates
    rows = []

    # --- baselines (original similar-day quantile method) ---
    for tag, pol in (("baseline_default(0.9/0.2/28)", Policy()),
                     ("baseline_valbest(0.95/0.2/28)", Policy(load_quantile=0.95))):
        r = run("2", policy=pol)
        s = r["summary"]
        v, t = score(r["daily"], VALID), score(r["daily"], TEST)
        rows.append({"variant": tag, "zl": None, "zp": None,
                     "year": s["total_cost_yuan"], "emg": s["emergency_kwh"],
                     "val": v["total"], "test": t["total"]})
        print(f"{tag}: year={s['total_cost_yuan']:,.0f} val={v['total']:,.0f}")

    # --- SARIMA grid ---
    for variant in VARIANTS:
        cfg = VARIANTS[variant]
        lm, ls, lf = load_cache("load", variant)
        lm, ls, patched_l = sanitize(lm, ls, load, cfg["window"], None)
        pm, ps, pf = load_cache("pv", variant)
        pm, ps, patched_p = sanitize(pm, ps, pv, cfg["window"], "sqrt")
        print(f"[{variant}] sanitized cells: load={patched_l} pv={patched_p}", flush=True)
        for zl in Z_LOAD:
            for zp in Z_PV:
                r = run("2", policy=Policy(pv_scale=1.0),
                        load_predictor=make_load_predictor(lm, ls, zl),
                        pv_predictor=make_pv_predictor(pm, ps, zp))
                s = r["summary"]
                v, t = score(r["daily"], VALID), score(r["daily"], TEST)
                rows.append({"variant": variant, "zl": zl, "zp": zp,
                             "year": s["total_cost_yuan"], "emg": s["emergency_kwh"],
                             "val": v["total"], "test": t["total"]})
        print(f"[{variant}] grid done (load_fallback={lf}, pv_fallback={pf})",
              flush=True)

    # --- unbiased point-forecast MAE diagnostics (z = 0) ---
    diag = {}
    bl_load = np.array([history_prediction(a2.load, i, dates, .5, 28) for i in range(START, 365)])
    bl_pv = np.array([history_prediction(a2.pv_actual, i, dates, .5, 28) for i in range(START, 365)])
    diag["baseline_median"] = {
        "load_mae_kw": float(np.abs(bl_load - load[START:]).mean()),
        "pv_mae_kw": float(np.abs(bl_pv - pv[START:]).mean())}
    for variant in VARIANTS:
        lm, ls, lf = load_cache("load", variant)
        lm, ls, patched_l = sanitize(lm, ls, load, VARIANTS[variant]["window"], None)
        pm, ps, pf = load_cache("pv", variant)
        pm, ps, patched_p = sanitize(pm, ps, pv, VARIANTS[variant]["window"], "sqrt")
        diag[variant] = {
            "load_mae_kw": float(np.abs(lm[START:] - load[START:]).mean()),
            "pv_mae_kw": float(np.abs(pm[START:] ** 2 - pv[START:]).mean()),
            "load_fallback": lf, "pv_fallback": pf,
            "sanitized_cells": {"load": patched_l, "pv": patched_p}}

    payload = {"design": {"refit_every": REFIT_EVERY, "start_index": START,
                          "variants": {k: {kk: list(vv) if isinstance(vv, tuple) else vv
                                           for kk, vv in v.items()} for k, v in VARIANTS.items()},
                          "z_load": list(Z_LOAD), "z_pv": list(Z_PV),
                          "pv_transform": "sqrt, clip-then-square"},
               "rows": rows, "diagnostics": diag}
    out = paths.PROCESSED_DIR / "sarima_vs_baseline.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    best_val = min((r for r in rows if r["zl"] is not None), key=lambda r: r["val"])
    best_year = min((r for r in rows if r["zl"] is not None), key=lambda r: r["year"])
    print(f"\nSARIMA validation-best: {best_val['variant']} zl={best_val['zl']} zp={best_val['zp']} "
          f"val={best_val['val']:,.0f} year={best_val['year']:,.0f}")
    print(f"SARIMA full-year-best (hindsight): {best_year['variant']} zl={best_year['zl']} zp={best_year['zp']} "
          f"year={best_year['year']:,.0f}")
    print(f"saved -> {out}")
    return payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("precompute", "grid"))
    ap.add_argument("variant", nargs="?", choices=tuple(VARIANTS))
    args = ap.parse_args()
    if args.mode == "precompute":
        if not args.variant:
            ap.error("precompute requires a variant")
        run_precompute(args.variant)
    else:
        run_grid()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
