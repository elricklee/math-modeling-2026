"""问题 4（波动电价）对应问题 2 的逐日 LP。

与 :mod:`solve_problem2` 完全相同的储能、限光和紧急购电约束下，
仅把每天的价格向量替换为附件 4 的实时 10 分钟价格。输出 JSON，
用于和问题 2 的固定典型日电价结果做逐日、全年费用对照。
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date
from pathlib import Path

import numpy as np

from . import io_attachments as io
from . import paths
from .solve_problem2 import solve_day


def run(output: Path | None = None) -> dict:
    _a1, a2, _a3, a4 = io.load_all()
    price_index = {d: i for i, d in enumerate(a4.dates)}
    results = []
    for day, load, pv in zip(a2.dates, a2.load, a2.pv_actual):
        price = np.asarray(a4.price[price_index[day]], dtype=float)
        results.append(solve_day(day, price, np.asarray(load), np.asarray(pv)))
    solved = [r for r in results if r.success]
    if len(solved) != len(results):
        raise RuntimeError("波动电价模型存在不可行日期")
    output_start = date.fromisoformat(paths.RESULT2_START)
    output_solved = [r for r in solved if date.fromisoformat(r.date) >= output_start]

    payload = {
        "model": {
            "question": "4-2",
            "price_source": "附件4逐日实时电价",
            "load_pv_source": "附件2实际负荷与光伏",
            "dt_h": paths.INTERVAL_MINUTES / 60.0,
            "eta": paths.STORAGE.efficiency,
            "soc_boundary_kwh": paths.STORAGE.soc_init_kwh,
            "emergency_multiplier": 5.0,
            "normal_purchase_unbounded": True,
        },
        "summary": {
            "n_days": len(solved),
            "output_interval": [paths.RESULT2_START, paths.RESULT2_END],
            "output_n_days": len(output_solved),
            "total_purchase_kwh": float(sum(r.purchase_kwh for r in solved)),
            "total_purchase_cost_yuan": float(sum(r.purchase_cost_yuan for r in solved)),
            "total_emergency_kwh": float(sum(r.emergency_kwh for r in solved)),
            "total_curtail_kwh": float(sum(r.curtail_kwh for r in solved)),
            "output_total_purchase_kwh": float(sum(r.purchase_kwh for r in output_solved)),
            "output_total_purchase_cost_yuan": float(sum(r.purchase_cost_yuan for r in output_solved)),
            "output_total_emergency_kwh": float(sum(r.emergency_kwh for r in output_solved)),
            "output_total_curtail_kwh": float(sum(r.curtail_kwh for r in output_solved)),
            "days_with_curtailment": int(sum(r.curtail_kwh > 1e-7 for r in solved)),
            "max_balance_residual_kwh": float(max(r.max_balance_residual_kwh for r in solved)),
            "max_soc_residual_kwh": float(max(r.max_soc_residual_kwh for r in solved)),
        },
        "representative_days": {
            d: asdict(next(r for r in solved if r.date == d))
            for d in ("2025-03-20", "2025-06-21", "2025-09-23", "2025-12-21")
        },
        "daily": [asdict(r) for r in results],
    }
    destination = output or (paths.PROCESSED_DIR / "problem4_2_daily_solution.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def main() -> int:
    payload = run()
    s = payload["summary"]
    print(f"问题4-2求解完成：{s['n_days']} 天")
    print(f"全年购电费 {s['total_purchase_cost_yuan']:.6f} 元，限光 {s['total_curtail_kwh']:.6f} kWh")
    print(f"最大平衡残差 {s['max_balance_residual_kwh']:.3e} kWh，最大 SOC 残差 {s['max_soc_residual_kwh']:.3e} kWh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

