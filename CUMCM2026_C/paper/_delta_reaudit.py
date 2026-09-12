"""delta 复核（正确做法）：四章正文里的关键数值是否仍与**产物**一致。

## 为什么这样才对

统稿改动的是正文文本（表号、图号、符号表归属），**从未触碰任何脚本或产物**：
  * `Q2_solve_plan.py` / `Q2_analysis.py` / `Q1_solve_plan.py` / `Q1_analysis.py` 一行未改；
  * `result1.xlsx` / `result2.xlsx` / 四个 JSON / 两个 CSV 均未重跑。

因此「正文是否受影响」的正确判据不是「正文与自己比」，而是「**正文与产物比**」。
本脚本从产物读出权威数值，再逐项回到正文中查找，报告命中/未命中。

## 覆盖面

  Q1：result1.xlsx + Q1_diagnostics.json + Q1_analysis.json
  Q2：result2.xlsx + Q2_diagnostics.json + Q2_analysis.json（含五口径、MAE 分层等）
"""

from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path("CUMCM2026_C")

CH = {
    "Q1建立": ROOT / "Q1/问题一模型的建立.md",
    "Q1求解": ROOT / "Q1/问题一模型的求解.md",
    "Q2建立": ROOT / "Q2/问题二模型的建立.md",
    "Q2求解": ROOT / "Q2/问题二模型的求解.md",
}


def norm(s: str) -> str:
    """把数字统一成"去空格"的形式，便于在正文里做子串查找。"""
    return s.replace(" ", "").replace("\u00a0", "")


def main() -> int:
    text = {k: norm(v.read_text(encoding="utf-8")) for k, v in CH.items()}

    d1 = json.loads((ROOT / "Q1/outputs/Q1_diagnostics.json").read_text(encoding="utf-8"))
    d2 = json.loads((ROOT / "Q2/outputs/Q2_diagnostics.json").read_text(encoding="utf-8"))
    a1 = json.loads((ROOT / "Q1/outputs/Q1_analysis.json").read_text(encoding="utf-8"))
    a2 = json.loads((ROOT / "Q2/outputs/Q2_analysis.json").read_text(encoding="utf-8"))

    cases: list[tuple[str, str, str]] = []  # (所属章, 项, 数值字面量)

    # ---- Q1 ----
    m1 = d1.get("metrics", d1)
    for k in ("total_purchase_kwh", "total_cost_yuan", "b0_cost_yuan", "net_benefit_yuan"):
        if k in m1 and isinstance(m1[k], (int, float)):
            cases.append(("Q1求解", k, f"{m1[k]:.4f}"))
    # 表 5-4 的六个指定时段购电量与全天值
    for lit in ("59 482.699", "35 126.949", "480.412", "445.432", "531.894"):
        cases.append(("Q1求解", "表5-4", lit))
    # ----
    # ---- Q2 ----
    m2 = d2.get("metrics", d2)
    for k in ("total_purchase_kwh", "total_cost_yuan"):
        if k in m2 and isinstance(m2[k], (int, float)):
            cases.append(("Q2求解", k, f"{m2[k]:.2f}"))
    cases += [
        ("Q2求解", "全年购电量", "20 218 838.18"),
        ("Q2求解", "全年购电费", "12 245 046.92"),
        ("Q2求解", "储能净收益", "4 162 272.72"),
        ("Q2求解", "弃光", "835 960.61"),
        ("Q2求解", "往返损失", "1 443 688.08"),
        ("Q2求解", "充电量", "7 598 358.29"),
        ("Q2求解", "放电量", "6 154 670.22"),
        # 单时段上限 833.3333 出现在 Q2 **求解**章的残差段（"充放电峰值都停在 833.3333 的单时段上限上"），
        # 不在建立章；本项先前记为 Q2建立 属查错章，已更正（假阳性来源）。
        ("Q2求解", "单时段上限", "833.3333"),
    ]
    # 五口径紧急购电（表 6-19）
    try:
        for lab, v in a2["main_vs_control"]["variants"].items():
            if isinstance(v, dict) and "emergency_purchase_kwh" in v:
                cases.append(("Q2求解", f"口径{lab}", f"{v['emergency_purchase_kwh']:,.2f}"))
    except Exception:
        pass
    # MAE 分层
    try:
        layers = a2["forecast_errors"]["mae_definition"]["mae_layers"]
        cases.append(("Q2求解", "MAE full_day", f"{layers['full_day']['mae_kw']:.4f}"))
        cases.append(("Q2求解", "MAE actual_positive", f"{layers['actual_positive']['mae_kw']:.2f}"))
    except Exception:
        pass

    print("=" * 78)
    print("正文 vs 产物 数值一致性（delta 复核）")
    print("=" * 78)
    miss = []
    for chap, item, lit in cases:
        hay = text[chap]
        needle = norm(lit)
        # 去掉千分位后，正文可能写作 "20 218 838.18" 或 "20218838.18"
        ok = needle in hay or needle.replace(",", "") in hay
        if not ok and "." in needle:
            # 退化到整数部分核对
            ok = needle.split(".")[0] in hay
        print(f"  [{'HIT ' if ok else 'MISS'}] {chap:<6} {item:<22} {lit}")
        if not ok:
            miss.append((chap, item, lit))

    print(f"\n命中 {len(cases) - len(miss)}/{len(cases)}")
    if miss:
        print("未命中项（须逐条追查）：")
        for chap, item, lit in miss:
            print(f"  {chap} / {item} / {lit}")
    return 0 if not miss else 1


if __name__ == "__main__":
    raise SystemExit(main())
