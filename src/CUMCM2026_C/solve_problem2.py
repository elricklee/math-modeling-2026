"""问题 2 的逐日确定性线性规划求解器。

该实现严格采用题面单位：附件中的负荷/光伏是 kW，先乘
``DT = 10/60`` 转成每个 10 分钟时段的 kWh。每天独立优化，储能首末
电量均钉在附录给出的 6000 kWh；外购电没有题面给出的容量上限，因此
紧急购电变量在最优解中应为 0，但仍显式保留并按 5 倍电价计费，便于
后续做容量上限或预测误差情景分析。

输出为 JSON（不改写原始附件），包括 334 天逐日结果、四个表 3 日期的
明细以及全年汇总，可直接作为论文表格和敏感性分析的数据源。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import numpy as np
from scipy.optimize import linprog

from . import io_attachments as io
from . import paths


DT = paths.INTERVAL_MINUTES / 60.0
T = paths.INTERVALS_PER_DAY
ETA = paths.STORAGE.efficiency
XMAX = paths.STORAGE.max_energy_per_interval_charge
YMAX = paths.STORAGE.max_energy_per_interval_discharge

# Variable blocks: S[0:T+1], x[0:T], y[0:T], g[0:T], p[0:T], z[0:T].
IS = 0
IX = T + 1
IY = IX + T
IG = IY + T
IP = IG + T
IZ = IP + T
N = IZ + T


@dataclass(frozen=True)
class DayResult:
    date: str
    success: bool
    message: str
    purchase_kwh: float
    purchase_cost_yuan: float
    emergency_kwh: float
    emergency_cost_yuan: float
    curtail_kwh: float
    charge_kwh: float
    discharge_kwh: float
    soc_start_kwh: float
    soc_end_kwh: float
    soc_min_kwh: float
    soc_max_kwh: float
    max_balance_residual_kwh: float
    max_soc_residual_kwh: float


def _build_lp(price: np.ndarray, load_kw: np.ndarray, pv_kw: np.ndarray):
    """构造单日 LP，返回 scipy.optimize.linprog 所需的五元组。"""
    if not (price.size == load_kw.size == pv_kw.size == T):
        raise ValueError(f"单日输入必须均为 {T} 个时段")
    net_e = (load_kw - pv_kw) * DT
    pv_e = pv_kw * DT

    c = np.zeros(N)
    c[IP : IP + T] = price
    c[IZ : IZ + T] = 5.0 * price

    # 能量平衡：p + z + y - x - g = (load-pv) * DT
    a_balance = np.zeros((T, N))
    for t in range(T):
        a_balance[t, IX + t] = -1.0
        a_balance[t, IY + t] = 1.0
        a_balance[t, IG + t] = -1.0
        a_balance[t, IP + t] = 1.0
        a_balance[t, IZ + t] = 1.0

    # SOC 递推：S[t+1]-S[t]-eta*x+y/eta=0
    a_soc = np.zeros((T, N))
    for t in range(T):
        a_soc[t, IS + t + 1] = 1.0
        a_soc[t, IS + t] = -1.0
        a_soc[t, IX + t] = -ETA
        a_soc[t, IY + t] = 1.0 / ETA

    bounds = (
        [(paths.STORAGE.soc_init_kwh, paths.STORAGE.soc_init_kwh)]
        + [(paths.STORAGE.soc_min_kwh, paths.STORAGE.soc_max_kwh)] * (T - 1)
        + [(paths.STORAGE.soc_init_kwh, paths.STORAGE.soc_init_kwh)]
        + [(0.0, XMAX)] * T
        + [(0.0, YMAX)] * T
        + [(0.0, float(v)) for v in pv_e]
        + [(0.0, None)] * T  # normal planned purchase
        + [(0.0, None)] * T  # emergency purchase
    )
    return c, np.vstack((a_balance, a_soc)), np.concatenate((net_e, np.zeros(T))), bounds


def solve_day_solution(day: date, price: np.ndarray, load_kw: np.ndarray, pv_kw: np.ndarray):
    c, a_eq, b_eq, bounds = _build_lp(price, load_kw, pv_kw)
    result = linprog(c, A_eq=a_eq, b_eq=b_eq, bounds=bounds, method="highs")
    if not result.success:
        return DayResult(day.isoformat(), False, result.message, *(float("nan"),) * 13), None

    z = result.x
    s = z[IS : IS + T + 1]
    x = z[IX : IX + T]
    y = z[IY : IY + T]
    g = z[IG : IG + T]
    p = z[IP : IP + T]
    emergency = z[IZ : IZ + T]
    net_e = (load_kw - pv_kw) * DT
    balance = p + emergency + y - x - g - net_e
    soc = s[1:] - s[:-1] - ETA * x + y / ETA
    summary = DayResult(
        date=day.isoformat(), success=True, message="",
        purchase_kwh=float(p.sum()), purchase_cost_yuan=float(np.dot(price, p)),
        emergency_kwh=float(emergency.sum()), emergency_cost_yuan=float(np.dot(5 * price, emergency)),
        curtail_kwh=float(g.sum()), charge_kwh=float(x.sum()), discharge_kwh=float(y.sum()),
        soc_start_kwh=float(s[0]), soc_end_kwh=float(s[-1]),
        soc_min_kwh=float(s.min()), soc_max_kwh=float(s.max()),
        max_balance_residual_kwh=float(np.max(np.abs(balance))),
        max_soc_residual_kwh=float(np.max(np.abs(soc))),
    )
    return summary, {"purchase": p, "emergency": emergency, "charge": x, "discharge": y,
                     "curtail": g, "soc": s}


def solve_day(day: date, price: np.ndarray, load_kw: np.ndarray, pv_kw: np.ndarray) -> DayResult:
    """求解单日并返回摘要；需要逐时段决策量时使用 :func:`solve_day_solution`。"""
    summary, _ = solve_day_solution(day, price, load_kw, pv_kw)
    return summary


def run(output: Path | None = None) -> dict:
    a1, a2, _a3, _a4 = io.load_all()
    price = np.asarray(a1.price.values, dtype=float)
    results: list[DayResult] = []
    for day, load, pv in zip(a2.dates, a2.load, a2.pv_actual):
        results.append(solve_day(day, price, np.asarray(load), np.asarray(pv)))

    solved = [r for r in results if r.success]
    output_start = date.fromisoformat(paths.RESULT2_START)
    output_solved = [r for r in solved if date.fromisoformat(r.date) >= output_start]
    if not solved:
        raise RuntimeError("问题 2 没有可行的日解")
    summary = {
        "model": {
            "question": 2,
            "time_intervals": T,
            "dt_h": DT,
            "eta": ETA,
            "soc_bounds_kwh": [paths.STORAGE.soc_min_kwh, paths.STORAGE.soc_max_kwh],
            "soc_boundary_kwh": paths.STORAGE.soc_init_kwh,
            "power_limit_kwh_per_interval": XMAX,
            "emergency_multiplier": 5.0,
            "curtailment_allowed": True,
            "normal_purchase_unbounded": True,
        },
        "summary": {
            "n_days": len(results),
            "n_success": len(solved),
            "output_interval": [paths.RESULT2_START, paths.RESULT2_END],
            "output_n_days": len(output_solved),
            "total_purchase_kwh": float(sum(r.purchase_kwh for r in solved)),
            "total_purchase_cost_yuan": float(sum(r.purchase_cost_yuan for r in solved)),
            "total_emergency_kwh": float(sum(r.emergency_kwh for r in solved)),
            "total_emergency_cost_yuan": float(sum(r.emergency_cost_yuan for r in solved)),
            "total_curtail_kwh": float(sum(r.curtail_kwh for r in solved)),
            "total_charge_kwh": float(sum(r.charge_kwh for r in solved)),
            "total_discharge_kwh": float(sum(r.discharge_kwh for r in solved)),
            "max_balance_residual_kwh": float(max(r.max_balance_residual_kwh for r in solved)),
            "max_soc_residual_kwh": float(max(r.max_soc_residual_kwh for r in solved)),
            "days_with_curtailment": int(sum(r.curtail_kwh > 1e-7 for r in solved)),
            "days_with_emergency": int(sum(r.emergency_kwh > 1e-7 for r in solved)),
            "output_total_purchase_kwh": float(sum(r.purchase_kwh for r in output_solved)),
            "output_total_purchase_cost_yuan": float(sum(r.purchase_cost_yuan for r in output_solved)),
            "output_total_emergency_kwh": float(sum(r.emergency_kwh for r in output_solved)),
            "output_total_curtail_kwh": float(sum(r.curtail_kwh for r in output_solved)),
            "output_days_with_curtailment": int(sum(r.curtail_kwh > 1e-7 for r in output_solved)),
        },
        "representative_days": {
            d: asdict(next(r for r in solved if r.date == d))
            for d in ("2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21")
        },
        "daily": [asdict(r) for r in results],
    }
    destination = output or (paths.PROCESSED_DIR / "problem2_daily_solution.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    summary = run()
    s = summary["summary"]
    print(f"问题2求解完成：{s['n_success']}/{s['n_days']} 天")
    print(f"全年购电量 {s['total_purchase_kwh']:.6f} kWh，购电费 {s['total_purchase_cost_yuan']:.6f} 元")
    print(f"紧急购电 {s['total_emergency_kwh']:.6f} kWh，限光 {s['total_curtail_kwh']:.6f} kWh")
    print(f"最大平衡残差 {s['max_balance_residual_kwh']:.3e} kWh，最大 SOC 残差 {s['max_soc_residual_kwh']:.3e} kWh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
