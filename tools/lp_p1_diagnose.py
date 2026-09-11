"""问题1 LP 的最小可诊断重建（队长收敛用）。

不依赖任何成员代码，全部变量显式排布，逐步做可行性诊断：
  步骤 1  只含 SOC 递推 + S_0=S_144=6000 + 界          → 应可行（y≡0）
  步骤 2  加入 p ≥ 0（即 p = net + x − y ≥ 0）          → 检验是否仍可行
  步骤 3  求解最优目标 min Σ c_t p_t

变量排布   [ x(144) | y(144) | S(144) ]，n = 432
  x_t 充电量 kWh，y_t 放电量 kWh，S_t 时段末储电量 kWh
  p_t = net_t + x_t − y_t   （题面：微网供电不可低于负载，故 p ≥ 0）

用法：
    python tools/lp_p1_diagnose.py
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
IX, IY, IS = 0, T, 2 * T
N = 3 * T


def data() -> tuple[np.ndarray, np.ndarray]:
    wb = openpyxl.load_workbook(RAW / "附件1.xlsx", read_only=True, data_only=True)
    ws = wb.active
    rows = [r for r in ws.iter_rows(values_only=True)][1:]
    wb.close()
    load = np.array([float(r[2]) for r in rows])
    pv = np.array([float(r[3]) for r in rows])
    price = np.array([float(r[1]) for r in rows])
    return price, load * DT - pv * DT          # price, net_kwh


def soc_rows() -> tuple[np.ndarray, np.ndarray]:
    A = np.zeros((T, N))
    for t in range(T):
        A[t, IS + t] = 1.0
        if t > 0:
            A[t, IS + t - 1] = -1.0
        A[t, IX + t] = -ETA
        A[t, IY + t] = 1.0 / ETA
    return A, np.zeros(T)


def bounds(with_soc: bool = True) -> list[tuple[float, float]]:
    b = [(0.0, XMAX)] * T + [(0.0, XMAX)] * T
    b += [(S_LO, S_HI)] * T if with_soc else [(None, None)] * T
    return b


def run(net: np.ndarray, price: np.ndarray | None, with_soc: bool = True,
        force_zero_discharge: bool = False, label: str = "") -> dict:
    A_eq, b_eq = soc_rows()
    if with_soc:
        r = np.zeros((1, N)); r[0, IS] = 1.0
        A_eq = np.vstack([A_eq, r]); b_eq = np.append(b_eq, S_INIT)
        r = np.zeros((1, N)); r[0, IS + T - 1] = 1.0
        A_eq = np.vstack([A_eq, r]); b_eq = np.append(b_eq, S_INIT)
    bnd = bounds(with_soc)
    if force_zero_discharge:
        bnd[IY:IY + T] = [(0.0, 0.0)] * T
    c = np.zeros(N)
    if price is not None:
        c[IX:IX + T] = price
        c[IY:IY + T] = -price

    # 显式不等式：p = net + x - y >= 0  →  -x + y <= net
    A_ub = np.zeros((T, N))
    for t in range(T):
        A_ub[t, IX + t] = -1.0
        A_ub[t, IY + t] = 1.0
    b_ub = net.copy()

    res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bnd,
                  method="highs")
    out: dict = {"label": label, "feasible": bool(res.success)}
    if not res.success:
        out["message"] = res.message
        return out
    x, y, S = res.x[IX:IX + T], res.x[IY:IY + T], res.x[IS:IS + T]
    p = net + x - y
    out.update({
        "objective_kind": "min cost" if price is not None else "feasibility only",
        "objective_yuan": float(res.fun) + (float((price * net).sum()) if price is not None else 0.0),
        "total_purchase_kwh": float(p.sum()),
        "charge_kwh": float(x.sum()),
        "discharge_kwh": float(y.sum()),
        "soc_min": float(S.min()),
        "soc_max": float(S.max()),
        "soc_end": float(S[-1]),
        "p_min": float(p.min()),
        "purchase_cost_yuan": float((price * p).sum()) if price is not None else None,
        "soc_residual": float(np.abs(np.diff(np.concatenate([[S_INIT], S]))
                                     - (ETA * x - y / ETA)).max()),
        "balance_residual": float(np.abs(p + y - x - net).max()),
    })
    return out


def main() -> None:
    price, net = data()
    print("=" * 78)
    print(f"附件1：净负荷 kWh  范围 [{net.min():,.2f}, {net.max():,.2f}]  "
          f"负值时段 {(net < 0).sum()}/144")

    for kwargs, label in [
        (dict(price=None, with_soc=True, force_zero_discharge=True),
         "步骤1 仅可行性：y≡0（储能不动）"),
        (dict(price=None, with_soc=True, force_zero_discharge=False),
         "步骤2 仅可行性：允许充放"),
        (dict(price=price, with_soc=True, force_zero_discharge=False),
         "步骤3 最优：min Σ c_t p_t"),
    ]:
        out = run(net, label=label, **kwargs)
        print("-" * 78)
        print(f"{label}")
        for k, v in out.items():
            if k != "label":
                print(f"    {k:22s} = {v}")


if __name__ == "__main__":
    main()
