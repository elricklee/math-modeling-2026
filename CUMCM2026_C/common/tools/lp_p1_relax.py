"""逐步放宽约束，定位问题1 不可行的确切来源（队长收敛诊断）。

依次测试：
  T1 无储能（x=y=0）+ 允许限光                 → 应可行
  T2 有储能，但放开储能容量上下限[-1e9,1e9]     → 检验 SOC 区间是否是瓶颈
  T3 有储能 + 正常 SOC 区间，去掉 S_144=S_INIT → 检验"日终归位"是否是瓶颈
  T4 有储能 + 正常 SOC 区间 + S_144=S_INIT     → 完整模型

变量 [ x | y | curt | S ]，n = 4T。

用法：
    python tools/lp_p1_relax.py
"""

from __future__ import annotations

import numpy as np
import openpyxl
from pathlib import Path
from scipy.optimize import linprog

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "CUMCM2026_C"
DT, XMAX, ETA = 1.0 / 6.0, 5000.0 / 6.0, 0.9
S_LO, S_HI, S_INIT, T = 1200.0, 10800.0, 6000.0, 144
IX, IY, ICURT, IS = 0, T, 2 * T, 3 * T
N = 4 * T


def load_data():
    wb = openpyxl.load_workbook(RAW / "附件1.xlsx", read_only=True, data_only=True)
    ws = wb.active
    rows = [r for r in ws.iter_rows(values_only=True)][1:]
    wb.close()
    return (np.array([float(r[1]) for r in rows]),
            np.array([float(r[2]) for r in rows]),
            np.array([float(r[3]) for r in rows]))


def build(price, net, pv_e, *, soc_lo, soc_hi, fix_end, no_storage, no_soc_bounds):
    c = np.zeros(N)
    c[IX:IX + T] = price
    c[IY:IY + T] = -price
    c[ICURT:ICURT + T] = price

    A_eq_rows, b_eq_rows = [], []
    if not no_soc_bounds:
        for t in range(T):
            row = np.zeros(N)
            row[IS + t] = 1.0
            if t > 0:
                row[IS + t - 1] = -1.0
            row[IX + t] = -ETA
            row[IY + t] = 1.0 / ETA
            A_eq_rows.append(row)
            b_eq_rows.append(0.0)
        row = np.zeros(N); row[IS] = 1.0
        A_eq_rows.append(row); b_eq_rows.append(S_INIT)
        if fix_end:
            row = np.zeros(N); row[IS + T - 1] = 1.0
            A_eq_rows.append(row); b_eq_rows.append(S_INIT)

    A_ub = np.zeros((T, N))
    for t in range(T):
        A_ub[t, IY + t] = 1.0
        A_ub[t, IX + t] = -1.0
        A_ub[t, ICURT + t] = -1.0

    if no_soc_bounds:
        soc_b = [(None, None)] * T
    else:
        soc_b = [(soc_lo, soc_hi)] * T
    if no_storage:
        xb = [(0.0, 0.0)] * T
        yb = [(0.0, 0.0)] * T
    else:
        xb = [(0.0, XMAX)] * T
        yb = [(0.0, XMAX)] * T
    bounds = xb + yb + [(0.0, float(v)) for v in pv_e] + soc_b

    A_eq = np.array(A_eq_rows) if A_eq_rows else None
    b_eq = np.array(b_eq_rows) if b_eq_rows else None
    return c, A_ub, net.copy(), A_eq, b_eq, bounds


def main() -> None:
    price, load, pv = load_data()
    net = (load - pv) * DT
    pv_e = pv * DT

    cases = [
        ("T1 无储能 + 允许限光", dict(no_storage=True, no_soc_bounds=True,
                                soc_lo=S_LO, soc_hi=S_HI, fix_end=False)),
        ("T2 有储能 + SOC 无界 + S_0=6000", dict(no_storage=False, no_soc_bounds=True,
                                            soc_lo=S_LO, soc_hi=S_HI, fix_end=False)),
        ("T3 有储能 + SOC [1200,10800] + 仅 S_0=6000（不要求日终归位）",
         dict(no_storage=False, no_soc_bounds=False, soc_lo=S_LO, soc_hi=S_HI, fix_end=False)),
        ("T4 完整模型（含 S_144=S_0=6000）",
         dict(no_storage=False, no_soc_bounds=False, soc_lo=S_LO, soc_hi=S_HI, fix_end=True)),
        ("T5 完整模型但放宽 SOC 上界到 11500",
         dict(no_storage=False, no_soc_bounds=False, soc_lo=S_LO, soc_hi=11500.0, fix_end=True)),
        ("T6 完整模型但放宽 SOC 下界到 500",
         dict(no_storage=False, no_soc_bounds=False, soc_lo=500.0, soc_hi=S_HI, fix_end=True)),
    ]
    for label, kw in cases:
        c, A_ub, b_ub, A_eq, b_eq, bounds = build(price, net, pv_e, **kw)
        res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds,
                      method="highs")
        print("=" * 78)
        print(label)
        if not res.success:
            print(f"    不可行: {res.message}")
            continue
        x, y = res.x[IX:IX + T], res.x[IY:IY + T]
        curt, S = res.x[ICURT:ICURT + T], res.x[IS:IS + T]
        p = net + x - y + curt
        print(f"    购电量 {p.sum():>14,.2f} kWh   购电费 {(price * p).sum():>14,.2f} 元")
        print(f"    充电 {x.sum():>14,.2f} kWh   放电 {y.sum():>14,.2f} kWh   "
              f"限光 {curt.sum():>12,.2f} kWh")
        print(f"    SOC 范围 [{S.min():,.2f}, {S.max():,.2f}]   末值 {S[-1]:,.2f}")


if __name__ == "__main__":
    main()
