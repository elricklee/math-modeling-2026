"""收敛阶段关键裁定计算（队长用）。

回答三个必须裁定的问题：
  Q1 附件1 的净负荷极值在"功率(kW)"与"能量(kWh)"两种口径下的量级 —— 是否真的需要"限光"松弛？
  Q2 结果模板的时间列到底是 144 个还是 145 个？语义是"区间终点"还是"区间起点"？
  Q3 排除限光后问题1 是否严格不可行（即限光是数学必需还是可选口径）？

用法：
    python tools/convergence_checks.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import openpyxl

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "CUMCM2026_C"
OUT = ROOT / "data" / "processed" / "CUMCM2026_C"

DT = 1.0 / 6.0            # 时段长度（h）
XMAX = 5000.0 * DT        # 单时段最大充/放电量（kWh） = 833.3333
S_LO, S_HI, S_INIT = 1200.0, 10800.0, 6000.0
ETA = 0.9


def load_attach1() -> dict[str, np.ndarray]:
    wb = openpyxl.load_workbook(RAW / "附件1.xlsx", read_only=True, data_only=True)
    ws = wb.active
    rows = [r for r in ws.iter_rows(values_only=True)][1:]
    wb.close()
    return {
        "time": [r[0] for r in rows],
        "price": np.array([float(r[1]) for r in rows]),
        "load": np.array([float(r[2]) for r in rows]),
        "pv": np.array([float(r[3]) for r in rows]),
    }


def q1_netload_scale(a1: dict[str, np.ndarray]) -> dict:
    net_kw = a1["load"] - a1["pv"]                    # kW
    net_kwh = net_kw * DT                             # kWh
    surplus_kwh = np.maximum(-net_kwh, 0.0)           # 需要吸收的光伏余量（kWh）
    blocks = np.ceil(surplus_kwh / XMAX).astype(int)  # 需要几个满功率时段才能吸收
    return {
        "net_power_min_kw": float(net_kw.min()),
        "net_power_max_kw": float(net_kw.max()),
        "net_energy_min_kwh": float(net_kwh.min()),
        "net_energy_max_kwh": float(net_kwh.max()),
        "xmax_kwh": XMAX,
        "surplus_periods": int((net_kwh < 0).sum()),
        "surplus_total_kwh": float(surplus_kwh.sum()),
        "max_surplus_kwh_in_one_period": float(surplus_kwh.max()),
        "periods_exceeding_xmax": int((blocks > 1).sum()),
        "note": "periods_exceeding_xmax>0 表示单时段余量超过储能吸收能力，必须限光或上网",
    }


def q3_feasibility_without_curtailment(a1: dict[str, np.ndarray]) -> dict:
    """无储能、无上网、无限光时，是否存在可行解？

    约束：p_t = net_t、且 p_t >= 0 且储能须吸收全部负余量。
    用"能量守恒 + 单时段功率上限"给出必要性检验：
      总余量必须能被储能在其可用容量窗口内吸收。
    """
    net_kwh = (a1["load"] - a1["pv"]) * DT
    surplus = np.maximum(-net_kwh, 0.0)
    deficit = np.maximum(net_kwh, 0.0)
    # 最强必要条件：单时段余量不得超过储能单时段可吸收能量
    max_absorb = XMAX
    return {
        "total_surplus_kwh": float(surplus.sum()),
        "total_deficit_kwh": float(deficit.sum()),
        "max_single_period_surplus_kwh": float(surplus.max()),
        "max_single_period_absorb_kwh": max_absorb,
        "single_period_violations": int((surplus > max_absorb + 1e-9).sum()),
        "verdict": ("需要限光/上网：存在单时段余量超过储能吸收上限的时刻"
                    if (surplus > max_absorb + 1e-9).any()
                    else "单时段可行；仍需检验全时段累计可行性"),
    }


def q2_template_columns() -> dict:
    """核对结果模板的时间列个数与首尾标签。"""
    res: dict = {"files": []}
    for name in ["result1.xlsx", "result2.xlsx", "result3.xlsx"]:
        wb = openpyxl.load_workbook(RAW / "附件5" / name, read_only=True, data_only=True)
        info: dict = {"file": name, "sheets": []}
        for ws in wb.worksheets:
            rows = list(ws.iter_rows(values_only=True))
            header = [c for c in rows[0]] if rows else []
            if ws.title in ("计划购电量", "调整购电量"):
                labels = [str(c) for c in header[1:] if c is not None]
                # 末尾两个是汇总列
                summary = [lab for lab in labels if lab in ("全天购电量", "全天购电费")]
                intervals = [lab for lab in labels if lab not in ("全天购电量", "全天购电费")]
                info["sheets"].append({
                    "name": ws.title,
                    "total_header_cols": len(header),
                    "interval_cols": len(intervals),
                    "first_interval": intervals[0] if intervals else None,
                    "last_interval": intervals[-1] if intervals else None,
                    "second_last_interval": intervals[-2] if len(intervals) > 1 else None,
                    "has_bare_000_010": "0:00-0:10" in intervals,
                    "summary_cols": summary,
                })
            elif ws.title == "计划购电量" or True:
                first_col = [str(r[0]) for r in rows[1:] if r and r[0] is not None]
                info["sheets"].append({
                    "name": ws.title,
                    "max_row": ws.max_row,
                    "max_col": ws.max_column,
                    "first_col_n": len(first_col),
                    "first_col_head": first_col[:2],
                    "first_col_tail": first_col[-2:],
                })
        wb.close()
        res["files"].append(info)
    return res


def main() -> None:
    a1 = load_attach1()
    print("=" * 78)
    print("Q1  附件1 净负荷量级（功率 vs 能量）")
    q1 = q1_netload_scale(a1)
    for key, value in q1.items():
        print(f"    {key:38s} = {value}")

    print("=" * 78)
    print("Q3  无限光/无上网时的严格可行性")
    q3 = q3_feasibility_without_curtailment(a1)
    for key, value in q3.items():
        print(f"    {key:38s} = {value}")

    print("=" * 78)
    print("Q2  结果模板时间列个数与首尾标签")
    q2 = q2_template_columns()
    for item in q2["files"]:
        print(f"  FILE {item['file']}")
        for sheet in item["sheets"]:
            if "interval_cols" in sheet:
                print(f"    {sheet['name']}: interval_cols={sheet['interval_cols']} "
                      f"first={sheet['first_interval']!r} last={sheet['last_interval']!r} "
                      f"second_last={sheet['second_last_interval']!r} "
                      f"裸0:00-0:10={sheet['has_bare_000_010']} summary={sheet['summary_cols']}")
            else:
                print(f"    {sheet['name']}: max_row={sheet['max_row']} "
                      f"max_col={sheet['max_col']} rows={sheet['first_col_n']} "
                      f"head={sheet['first_col_head']} tail={sheet['first_col_tail']}")

    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / "convergence_checks.json"
    dest.write_text(json.dumps({"q1_netload": q1, "q2_templates": q2, "q3_feasibility": q3},
                               ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果写入 {dest}")


if __name__ == "__main__":
    main()
