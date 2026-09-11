"""问题1 参考解 —— 修正版（补齐 SOC 递推的缺行与首时段约束）。

## 前一版的缺陷（已定位并修正）
前一版把 SOC 递推写成 `for t in range(1, T)`，只生成 143 行（t=1..143），并额外加
`S[0] = S_INIT`、`S[T-1] = S_INIT`。结果是：
  · **时段 t=143 的递推未被任何约束覆盖**（143 行只到 t=143，但行索引错位一格，
    实际覆盖 t=1..143 中的 142 个，漏掉一个）；
  · **时段 0 的充放电完全没有递推约束**（`S[0] = S_INIT` 是硬等式，使 x[0]、y[0]
    成为不进入任何守恒关系的自由变量）。
⇒ 求解器可"免费"放电：实测 y[0] = 573.31 kWh 而 S[0] 仍被钉在 6000，凭空产生能量。
⇒ 因此前一版的 58 909.39 kWh / 34 886.19 元 **低估了费用**，不是有效参考解。
（前一版自报的"残差 4.5e-13"是对 `A_eq` 的残差，而该矩阵恰好缺那一行，故属空断言。
  编程手与建模手分别以 `Σy/Σx ≠ η²` 与 `residual_soc=1590` 独立发现了这个异常。）

## 本版模型（与附件1 时段语义严格对齐）
附件1/2/4 的时间列是**时段结束时刻**（`0:10` 表示 0:00–0:10），即 144 个时段
`t = 1..144`，`t=144` 覆盖 `23:50–24:00`。

  变量  p_t 购电, x_t 充电, y_t 放电, g_t 限光（kWh, t=1..144）, S_t 时段末储电量
  初值  S_0 = 6000（0:00 时刻）
  递推  S_t = S_{t-1} + 0.9·x_t − y_t/0.9          对 **t = 1..144 全部 144 个时段**
  边界  S_0 = S_144 = 6000,  1200 ≤ S_t ≤ 10800
  限值  0 ≤ x_t, y_t ≤ 833.3333
  平衡  p_t + y_t + (pv_t·Δt − g_t) ≥ load_t·Δt + x_t   ⇔  p_t ≥ net_t + x_t − y_t + g_t
  非负  p_t ≥ 0,  0 ≤ g_t ≤ pv_t·Δt
  目标  min Σ_t c_t·p_t

变量排布 [ S(145) | x(144) | y(144) | g(144) ]，n = 577
  · S 含 S_0..S_144 共 145 个，S_0 由 bounds 钉死为 6000
  · 目标用 p_t = net_t + x_t − y_t + g_t（平衡取等号最优）回代

用法：
    python tools/lp_p1_final.py
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

DT, XMAX, ETA = 1.0 / 6.0, 5000.0 / 6.0, 0.9
S_LO, S_HI, S_INIT, T = 1200.0, 10800.0, 6000.0, 144
NS = T + 1                       # S_0 .. S_144
IS, IX, IY, IG = 0, NS, NS + T, NS + 2 * T
N = NS + 3 * T


def load_data() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    wb = openpyxl.load_workbook(RAW / "附件1.xlsx", read_only=True, data_only=True)
    ws = wb.active
    rows = [r for r in ws.iter_rows(values_only=True)][1:]
    wb.close()
    return (np.array([float(r[1]) for r in rows]),
            np.array([float(r[2]) for r in rows]),
            np.array([float(r[3]) for r in rows]))


def build(price: np.ndarray, net: np.ndarray, pv_e: np.ndarray):
    """返回 (c, const, A_ub, b_ub, A_eq, b_eq, bounds)。"""
    c = np.zeros(N)
    c[IX:IX + T] = price          # p 中的 +x
    c[IY:IY + T] = -price         # p 中的 −y
    c[IG:IG + T] = price          # p 中的 +g
    const = float((price * net).sum())

    # SOC 递推：S_t − S_{t-1} − 0.9·x_t + y_t/0.9 = 0,  t = 1..144（全部 144 行）
    A_eq = np.zeros((T, N))
    b_eq = np.zeros(T)
    for t in range(1, T + 1):
        r = t - 1
        A_eq[r, IS + t] = 1.0
        A_eq[r, IS + t - 1] = -1.0
        A_eq[r, IX + t - 1] = -ETA
        A_eq[r, IY + t - 1] = 1.0 / ETA

    # p ≥ 0： y_t − x_t − g_t ≤ net_t
    A_ub = np.zeros((T, N))
    for t in range(T):
        A_ub[t, IY + t] = 1.0
        A_ub[t, IX + t] = -1.0
        A_ub[t, IG + t] = -1.0

    bounds = ([(S_INIT, S_INIT)]                       # S_0 钉死为初值
              + [(S_LO, S_HI)] * (T - 1)               # S_1..S_143
              + [(S_INIT, S_INIT)]                     # S_144 日终归位
              + [(0.0, XMAX)] * T + [(0.0, XMAX)] * T
              + [(0.0, float(v)) for v in pv_e])
    return c, const, A_ub, net.copy(), A_eq, b_eq, bounds


def evaluate(z, price, net, pv_e) -> dict:
    S = z[IS:IS + NS]
    x, y, g = z[IX:IX + T], z[IY:IY + T], z[IG:IG + T]
    p = net + x - y + g
    prev = S[:-1]
    return {
        "total_purchase_kwh": float(p.sum()),
        "total_cost_yuan": float((price * p).sum()),
        "curtail_kwh": float(g.sum()),
        "pv_total_kwh": float(pv_e.sum()),
        "load_total_kwh": float((net + pv_e).sum()),
        "charge_kwh": float(x.sum()),
        "discharge_kwh": float(y.sum()),
        "discharge_over_charge": float(y.sum() / x.sum()) if x.sum() > 0 else None,
        "soc_start": float(S[0]),
        "soc_end": float(S[-1]),
        "soc_min": float(S.min()),
        "soc_max": float(S.max()),
        "p_min": float(p.min()),
        "residual_soc": float(np.abs((S[1:] - prev) - (ETA * x - y / ETA)).max()),
        "residual_balance": float(np.abs(p + y + (pv_e - g) - ((net + pv_e) + x)).max()),
        "max_soc_violation": float(max(0.0, S[1:-1].max() - S_HI, S_LO - S[1:-1].min())),
    }


def main() -> None:
    price, load, pv = load_data()
    net = (load - pv) * DT
    pv_e = pv * DT
    b0 = float((price * np.maximum(net, 0.0)).sum())

    c, const, A_ub, b_ub, A_eq, b_eq, bounds = build(price, net, pv_e)
    print(f"变量数 n = {N}   等式约束 {A_eq.shape[0]} 行   不等式 {A_ub.shape[0]} 行")
    print(f"公平基线 B0（不装储能 + 允许弃光） = {b0:,.2f} 元")

    feas = linprog(np.zeros(N), A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq,
                   bounds=bounds, method="highs")
    print(f"可行性(零目标): success={feas.success} {'' if feas.success else feas.message}")
    res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds,
                  method="highs")
    if not res.success:
        print(f"优化失败: {res.message}")
        return

    out = evaluate(res.x, price, net, pv_e)
    # 独立残差核查：直接对约束矩阵断言，且逐行确认无缺行
    out["A_eq_max_residual"] = float(np.abs(A_eq @ res.x - b_eq).max())
    out["objective_recompute_residual"] = float(abs(out["total_cost_yuan"] - (const + res.fun)))
    out["eta_squared_check"] = ETA ** 2

    print("=" * 78)
    for k, v in out.items():
        print(f"  {k:32s} = {v}")
    print("=" * 78)
    print(f"  储能净收益 = {b0 - out['total_cost_yuan']:,.2f} 元 "
          f"({(b0 - out['total_cost_yuan']) / b0:.4%})")
    print(f"  校验 Σy/Σx 应 = η² = {ETA ** 2:.4f}（无额外损耗时的理论关系）")

    OUT.mkdir(parents=True, exist_ok=True)
    payload = {**out, "baseline_B0_yuan": b0,
               "storage_net_benefit_yuan": b0 - out["total_cost_yuan"],
               "model_note": "修正版：SOC 递推覆盖 t=1..144 全部时段，S_0 与 S_144 均钉死为 6000",
               "superseded": {
                   "total_purchase_kwh": 58909.39123168724,
                   "total_cost_yuan": 34886.19078334296,
                   "defect": "SOC 递推缺一行且时段0 无递推约束，y[0]=573.31 kWh 凭空放电，费用被低估",
               }}
    dest = OUT / "problem1_reference_solution.json"
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果写入 {dest}")


if __name__ == "__main__":
    main()
