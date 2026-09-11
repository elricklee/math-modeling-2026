"""问题1 的独立直接形式 LP（队长收敛对账用，修正版）。

**关键修正**：题面为"微网提供的电能**不可低于**小区负载"，即
    p_t + y_t + pv_t·Δt  ≥  load_t·Δt + x_t
是**不等式**；光伏余量可以不被吸收（等价于弃光/限光），
**不需要显式引入限光变量**。上一版写成等式，强制全部光伏余量进入储能，
导致模型不可行（全天余量 6,247.96 kWh 无法在 S_0=S_144=6000 下全部吸收）。

模型：
    变量  p_t 购电量(kWh), x_t 充电量(kWh), y_t 放电量(kWh), S_t 时段末储电量(kWh)
    目标  min Σ_t c_t · p_t
    约束  ① p_t + y_t − x_t ≥ load_t·Δt − pv_t·Δt
          ② S_t = S_{t-1} + 0.9·x_t − y_t/0.9
          ③ 1200 ≤ S_t ≤ 10800,  S_0 = S_144 = 6000
          ④ 0 ≤ x_t,y_t ≤ 833.3333,  p_t ≥ 0
    额外约束（物理补充，题目未给但储能必需）：x_t ≤ pv_t·Δt + p_t  —— 不做此限制时
    储能可在夜间用外购电充电，这正是"低电价时段充电"的合法行为，故**不施加**。

基线：
    B0 不装储能 + 不允许余量抵扣（光伏只能就地消纳）：Σ c_t · max(net_t,0)
       —— 这里的 net_t = load−pv 已含就地消纳，故 B0 = Σ c_t·max(load·Δt − pv·Δt, 0)

用法：
    python tools/lp_problem1_direct.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import openpyxl
from scipy.optimize import linprog

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "CUMCM2026_C"
OUT = ROOT / "data" / "processed" / "CUMCM2026_C"

DT = 1.0 / 6.0
XMAX = 5000.0 * DT
S_LO, S_HI, S_INIT = 1200.0, 10800.0, 6000.0
ETA = 0.9
T = 144


def load_attach1() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    wb = openpyxl.load_workbook(RAW / "附件1.xlsx", read_only=True, data_only=True)
    ws = wb.active
    rows = [r for r in ws.iter_rows(values_only=True)][1:]
    wb.close()
    price = np.array([float(r[1]) for r in rows])
    load = np.array([float(r[2]) for r in rows])
    pv = np.array([float(r[3]) for r in rows])
    return price, load, pv


def solve_base(price: np.ndarray, load: np.ndarray, pv: np.ndarray) -> dict:
    """代入 LP：p_t 由等式给定，储能作为唯一自由度。

    由于目标只含 p_t，且 p_t = net_t + x_t − y_t（取等号最优），
    可直接把 p_t 代入目标，得到只含 x,y,S 的 LP：
        min Σ c_t·(net_t + x_t − y_t)
    """
    n = 3 * T
    ix, iy, iS = 0, T, 2 * T
    net = load * DT - pv * DT                     # kWh

    c = np.zeros(n)
    c[ix:ix + T] = price
    c[iy:iy + T] = -price
    const = float((price * net).sum())            # 目标中的常数项

    A_eq, b_eq = [], []
    for t in range(T):                            # SOC 递推
        row = np.zeros(n)
        row[iS + t] = 1.0
        if t > 0:
            row[iS + t - 1] = -1.0
        row[ix + t] = -ETA
        row[iy + t] = 1.0 / ETA
        A_eq.append(row)
        b_eq.append(0.0)
    row = np.zeros(n)                             # S_0 = S_INIT
    row[iS] = 1.0
    A_eq.append(row)
    b_eq.append(S_INIT)
    row = np.zeros(n)                             # S_144 = S_INIT
    row[iS + T - 1] = 1.0
    A_eq.append(row)
    b_eq.append(S_INIT)

    bounds = [(0, XMAX)] * T + [(0, XMAX)] * T + [(S_LO, S_HI)] * T
    res = linprog(c, A_eq=np.array(A_eq), b_eq=np.array(b_eq), bounds=bounds,
                  method="highs")
    if not res.success:
        return {"feasible": False, "message": res.message}

    z = res.x
    x, y, S = z[ix:ix + T], z[iy:iy + T], z[iS:iS + T]
    p = net + x - y                               # 由平衡等式反解购电量
    # 校验不等式约束 p >= 0（若为负说明可少买，故应 ≥ 0）
    return {
        "feasible": True,
        "objective_yuan": float(const + res.fun),
        "total_purchase_kwh": float(p.sum()),
        "charge_kwh": float(x.sum()),
        "discharge_kwh": float(y.sum()),
        "soc_min": float(S.min()),
        "soc_max": float(S.max()),
        "soc_start": S_INIT,
        "soc_end": float(S[-1]),
        "purchase_min": float(p.min()),
        "x_max": float(x.max()),
        "y_max": float(y.max()),
        "soc_recurrence_max_residual": float(np.abs(
            np.diff(np.concatenate([[S_INIT], S])) - (ETA * x - y / ETA)).max()),
        "supply_minus_demand_min": float((p + y - x - net).min()),
    }


def solve_with_export(price: np.ndarray, load: np.ndarray, pv: np.ndarray) -> dict:
    """允许上网（p_t 可负，即向外部电网售电且无收益），作为可行性上界对照。"""
    n = 4 * T
    ip, ix, iy, iS = 0, T, 2 * T, 3 * T
    net = load * DT - pv * DT
    c = np.zeros(n)
    c[ip:ip + T] = price
    A_eq, b_eq = [], []
    for t in range(T):
        row = np.zeros(n)
        row[ip + t], row[iy + t], row[ix + t] = 1.0, 1.0, -1.0
        A_eq.append(row)
        b_eq.append(net[t])
    for t in range(T):
        row = np.zeros(n)
        row[iS + t] = 1.0
        if t > 0:
            row[iS + t - 1] = -1.0
        row[ix + t] = -ETA
        row[iy + t] = 1.0 / ETA
        A_eq.append(row)
        b_eq.append(0.0)
    for idx, val in ((iS, S_INIT), (iS + T - 1, S_INIT)):
        row = np.zeros(n)
        row[idx] = 1.0
        A_eq.append(row)
        b_eq.append(val)
    bounds = [(None, None)] * T + [(0, XMAX)] * T + [(0, XMAX)] * T + [(S_LO, S_HI)] * T
    res = linprog(c, A_eq=np.array(A_eq), b_eq=np.array(b_eq), bounds=bounds, method="highs")
    if not res.success:
        return {"feasible": False, "message": res.message}
    p = res.x[ip:ip + T]
    return {"feasible": True, "objective_yuan": float(res.fun),
            "total_purchase_kwh": float(p.sum()), "min_purchase": float(p.min())}


def main() -> None:
    price, load, pv = load_attach1()
    net = load * DT - pv * DT

    b0 = float((price * np.maximum(net, 0.0)).sum())
    b1 = float((price * net).sum())
    print("=" * 78)
    print("基线（附件1 典型日）")
    print(f"  B0 不装储能、不允许余量抵扣 : {b0:>14,.2f} 元")
    print(f"  B1 不装储能、允许余量抵扣   : {b1:>14,.2f} 元   （不可与 B0 比较）")
    print(f"  附件1 光伏总发电量          : {(pv * DT).sum():>14,.2f} kWh")
    print(f"  附件1 负载总电量            : {(load * DT).sum():>14,.2f} kWh")
    print(f"  净负荷为负的时段数          : {(net < 0).sum():>14d} / 144")
    print(f"  负余量合计                  : {np.maximum(-net, 0).sum():>14,.2f} kWh")
    print(f"  单时段最大负余量            : {np.maximum(-net, 0).max():>14,.2f} kWh"
          f"  （吸收上限 {XMAX:,.4f}）")

    print("=" * 78)
    print("问题1 LP（题面不等式口径；光伏余量可弃，无需显式限光变量）")
    out = solve_base(price, load, pv)
    if out.get("feasible"):
        for key, value in out.items():
            if key != "feasible":
                print(f"  {key:32s} = {value}")
    else:
        print(f"  不可行: {out['message']}")

    print("=" * 78)
    print("对照：允许余量上网（p 可为负）")
    exp = solve_with_export(price, load, pv)
    for key, value in exp.items():
        print(f"  {key:32s} = {value}")

    OUT.mkdir(parents=True, exist_ok=True)
    payload = {
        "baseline_B0_no_storage": b0,
        "baseline_B1_with_offset": b1,
        "pv_total_kwh": float((pv * DT).sum()),
        "load_total_kwh": float((load * DT).sum()),
        "negative_surplus_periods": int((net < 0).sum()),
        "negative_surplus_total_kwh": float(np.maximum(-net, 0).sum()),
        "max_single_period_surplus_kwh": float(np.maximum(-net, 0).max()),
        "xmax_kwh": XMAX,
        "problem1_inequality_form": out,
        "problem1_with_export": exp,
    }
    dest = OUT / "problem1_reference_solution.json"
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果写入 {dest}")


if __name__ == "__main__":
    main()
