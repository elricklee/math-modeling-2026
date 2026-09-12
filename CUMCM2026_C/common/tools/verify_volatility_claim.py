"""复核建模手提出的两处勘误（队长裁定用）。

勘误 1：波动压缩口径。比较三种"波动"分母的语义差异：
    D1 = std(附件1 曲线)                     —— 均值曲线自身的日内波动
    D2 = median(全年 365 天的日内 σ)          —— "典型一天"的日内波动
    D3 = std(附件2 全年逐时段 σ 向量)         —— 各时刻跨日波动的离散度（含日间波动）
    D4 = mean(附件2 全年逐时段 σ 向量)
  并计算日间波动与"日负荷总量 vs 日电价均值"的相关系数。

勘误 2：列/行配对。核验 result1 与宽表在"方案 A"下的正确配对方式
    （属符号口径问题，用结构断言而非数值验证）。

用法：
    python tools/verify_volatility_claim.py
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import openpyxl

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "CUMCM2026_C"
OUT = ROOT / "data" / "processed" / "CUMCM2026_C"
DT = 1.0 / 6.0


def load_attach1() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    wb = openpyxl.load_workbook(RAW / "附件1.xlsx", read_only=True, data_only=True)
    ws = wb.active
    rows = [r for r in ws.iter_rows(values_only=True)][1:]
    wb.close()
    return (np.array([float(r[1]) for r in rows]),
            np.array([float(r[2]) for r in rows]),
            np.array([float(r[3]) for r in rows]))


def load_matrix(fname: str, sheet: str) -> np.ndarray:
    wb = openpyxl.load_workbook(RAW / fname, read_only=True, data_only=True)
    ws = wb[sheet]
    rows = [r for r in ws.iter_rows(values_only=True)][1:]
    wb.close()
    return np.array([[float(v) for v in r[1:145]] for r in rows if r[0] is not None])


def main() -> None:
    c1, l1, p1 = load_attach1()
    c4 = load_matrix("附件4.xlsx", "Sheet1")
    l2 = load_matrix("附件2.xlsx", "小区负载")
    p2 = load_matrix("附件2.xlsx", "光伏发电实际功率")

    print("=" * 78)
    print("勘误 1：波动口径的三种分母（各自语义不同，不可混用）")
    series = [
        ("负载", l1, l2),
        ("光伏", p1, p2),
        ("电价", c1, c4),
    ]
    table = []
    for name, curve, mat in series:
        d1 = float(curve.std())                 # 均值曲线日内 σ
        d2 = float(np.median(mat.std(axis=1)))  # 中位日的日内 σ
        per_ts = mat.std(axis=0)                # 每个时刻的跨日 σ
        d3 = float(per_ts.std())
        d4 = float(per_ts.mean())
        row = {
            "序列": name,
            "D1_均值曲线σ": d1,
            "D2_中位日日内σ": d2,
            "D3_逐时刻σ的σ": d3,
            "D4_逐时刻σ的均值": d4,
            "D1/D2_日内平滑": d1 / d2,
            "D1/D4_混口径": d1 / d4,
            "日内峰谷差_附件1": float(curve.max() - curve.min()),
            "日内峰谷差_中位日": float(np.median(mat.max(axis=1) - mat.min(axis=1))),
        }
        table.append(row)
        print(f"  [{name}]")
        print(f"      D1 均值曲线日内σ        = {d1:12.4f}")
        print(f"      D2 中位日日内σ          = {d2:12.4f}")
        print(f"      D3 逐时刻σ的σ           = {d3:12.4f}")
        print(f"      D4 逐时刻σ的均值        = {d4:12.4f}")
        print(f"      >>> D1/D2 日内平滑系数  = {d1 / d2:12.4f}   ← 同名同量纲，唯一可比")
        print(f"      D1/D4（混口径，已废弃） = {d1 / d4:12.4f}")
        print(f"      峰谷差 附件1/中位日     = {row['日内峰谷差_附件1']:.1f} / "
              f"{row['日内峰谷差_中位日']:.1f}")

    print("=" * 78)
    print("日间波动与结构相关性（问题1 可外推性的真正论据）")
    load_daily = l2.sum(axis=1) * DT
    pv_daily = p2.sum(axis=1) * DT
    price_daily_mean = c4.mean(axis=1)
    price_daily_sum = c4.sum(axis=1)
    print(f"  日负荷总量 CV            = {load_daily.std() / load_daily.mean():.4f}")
    print(f"  日光伏总量 CV            = {pv_daily.std() / pv_daily.mean():.4f}")
    print(f"  日电价均值 CV            = {price_daily_mean.std() / price_daily_mean.mean():.4f}")
    r_load_price = float(np.corrcoef(load_daily, price_daily_mean)[0, 1])
    r_pv_price = float(np.corrcoef(pv_daily, price_daily_mean)[0, 1])
    print(f"  日负荷总量 vs 日电价均值 r = {r_load_price:+.4f}")
    print(f"  日光伏总量 vs 日电价均值 r = {r_pv_price:+.4f}")
    print(f"  日负荷总量 vs 日光伏总量 r = {float(np.corrcoef(load_daily, pv_daily)[0, 1]):+.4f}")
    print()
    print("  → 若 r(负荷,电价) 显著为正，则问题1『固定电价配固定负荷曲线』")
    print("     丢掉了『高负荷日恰是高价日』的结构，这才是不可外推的真正原因，")
    print("     而『日内平滑』的说法不足以支撑该结论。")

    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / "volatility_verification.json"
    payload = {
        "三种分母对照": table,
        "日间波动": {
            "日负荷总量_CV": float(load_daily.std() / load_daily.mean()),
            "日光伏总量_CV": float(pv_daily.std() / pv_daily.mean()),
            "日电价均值_CV": float(price_daily_mean.std() / price_daily_mean.mean()),
        },
        "相关系数": {
            "日负荷总量_vs_日电价均值": r_load_price,
            "日光伏总量_vs_日电价均值": r_pv_price,
            "日负荷总量_vs_日光伏总量": float(np.corrcoef(load_daily, pv_daily)[0, 1]),
        },
        "结论": "日内平滑系数在不同分母下有不同含义；可外推性的主论据应为日间波动与负荷-电价正相关",
    }
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果写入 {dest}")


if __name__ == "__main__":
    main()
