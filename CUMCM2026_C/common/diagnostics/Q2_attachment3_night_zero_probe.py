r"""只读探针：核对附件 3 的**夜间零值重合**与逐位相等样本的性质（中性表述）。

结论（本脚本的实测）::

    * 四个发布时刻 r ∈ {0,6,12,18} 各有一段预报值与附件 2 实际**逐位相等**，
      位置都落在夜间钟点（约 0:00–4:00 与 19:00–24:00）；
    * 这些相等样本的**实际光伏也恰好为 0 kW** ⇒ 属 0 == 0 的**平凡相等**，
      不携带白天信息；
    * 逐时段看，「逐位相等且实际 > 1 kW」的只有 36/48 096 = 0.0749%，
      且**全部**落在整点的最后一个 10 分钟格（附件 3 该列 = 该小时末瞬时读数）；
    * 精度指标必须是**两层并列**：主指标 = 全天 144 个时段（MAE 371.2208 kW）；
      参考层 = 只统计实际光伏 > 0 的 26 880 个时段（MAE 657.55 kW），
      夜间零值时段占全天 44.11%、会稀释全天指标。

做法：对四个发布时刻的 24 列逐列比对（列 k ↔ 绝对小时块 r+k−1 ↔ 目标日钟点），
统计逐位相等的样本并**区分这些样本里实际值是否为 0**；再按钟点给出时段级分布。

约定：本探针导入流水线模块以复现其数据读入口径，**不是**独立审计；
独立审计见 ``Q2_audit.py``（其 U5 条目对同一事实做了独立复算）。

运行（仓库根目录）::

    $env:PYTHONIOENCODING="utf-8"
    .venv\Scripts\python.exe CUMCM2026_C\common\diagnostics\Q2_attachment3_night_zero_probe.py
"""

from __future__ import annotations

import sys
from datetime import timedelta

import numpy as np

ROOT = r"D:\MathModeling\math-modeling-2026"
sys.path.insert(0, ROOT)

from CUMCM2026_C.common.code import io_attachments as io  # noqa: E402
from CUMCM2026_C.Q2 import Q2_solve_plan as sp  # noqa: E402

att2 = io.load_attachment_2()
att3 = io.load_attachment_3()
pv = att2.pv_actual
day_index = {d: i for i, d in enumerate(att2.dates)}
data = sp.load_data()
dates = data["dates"]

print("=" * 84)
print("逐发布时刻、逐列的『精确相等』统计（残差阈值 1e-9 kW）")
print("=" * 84)
summary: dict[int, dict] = {}
for r in (0, 6, 12, 18):
    print(f"\n--- 发布时刻 {r:02d}:00（第 k 列 ↔ 目标日钟点 (r+k-1)%24）---")
    exact_cols, part_cols = [], []
    for k in range(1, 25):
        n_try = n_exact = n_nonzero = 0
        max_act_exact = 0.0
        for d in dates:
            release_day = d - timedelta(days=1) if r == 18 else d
            abs_block = r + k - 1
            src = release_day + timedelta(days=abs_block // 24)
            if src not in day_index:
                continue
            hour = abs_block % 24
            try:
                row = att3.row_index(release_day, r)
            except KeyError:
                continue
            f = float(att3.forecast[row, k - 1])
            seg = pv[day_index[src], hour * 6:(hour + 1) * 6]
            n_try += 1
            if np.max(np.abs(seg - f)) < 1e-9:
                n_exact += 1
                max_act_exact = max(max_act_exact, float(np.max(seg)))
                if float(np.max(seg)) > 1e-6:
                    n_nonzero += 1
        frac = n_exact / n_try if n_try else 0.0
        if frac > 0.99:
            exact_cols.append(k)
        elif frac > 0.5:
            part_cols.append(k)
        if frac > 0.5:
            print(f"  k={k:2d}（钟点 {((r + k - 1) % 24):2d}:00）：精确 {n_exact}/{n_try} 天"
                  f"（{frac:.1%}）；其中**实际值 > 0 的样本 {n_nonzero} 个**；"
                  f"精确样本里实际值最大值 {max_act_exact:.6f} kW")
    hours = sorted({(r + k - 1) % 24 for k in exact_cols})
    summary[r] = {"exact_cols": exact_cols, "hours": hours,
                  "part_cols": part_cols}
    print(f"  ⇒ 完全精确列 k = {exact_cols}，对应钟点 {hours}"
          f"（共 {len(exact_cols)} 列 = {len(exact_cols)} 个小时块）")
    if part_cols:
        print(f"  ⇒ 部分精确列 k = {part_cols}")

print("=" * 84)
print("MAE（kW）在不同统计口径下（以 2025-02-01..12-31 共 334 天为目标）")
print("=" * 84)
pv_target = data["pv_kw"]
r0 = 0
pred = np.zeros_like(pv_target)
for i, d in enumerate(dates):
    row = att3.row_index(d, r0)
    pred[i] = np.repeat(np.asarray(att3.forecast[row], dtype=float), 6)
err = np.abs(pred - pv_target)
print(f"全 144 时段 MAE                      = {err.mean():,.4f} kW（{err.size} 个时段）")
pos = pv_target > 1e-6
print(f"仅实际光伏 > 0 的时段 MAE            = {err[pos].mean():,.4f} kW（{int(pos.sum())} 个时段）")
print(f"实际光伏 = 0 的时段占比              = {float((~pos).mean()):.1%}"
      f"；这些时段的平均绝对误差 = {err[~pos].mean():,.6f} kW")
exact_mask = err < 1e-9
print(f"预测与实际逐位相等（<1e-9）的时段数   = {int(exact_mask.sum())}"
      f"（{exact_mask.mean():.1%}）；这些时段的实际光伏最大值 = "
      f"{float(pv_target[exact_mask].max()) if exact_mask.any() else 0.0:.6f} kW")
print(f"剔除上述精确时段后的 MAE             = {err[~exact_mask].mean():,.4f} kW"
      f"（剩余 {int((~exact_mask).sum())} 个时段）")
night_hours = [0, 1, 2, 3, 19, 20, 21, 22, 23]
night_mask = np.zeros_like(pv_target, dtype=bool)
for h in night_hours:
    night_mask[:, h * 6:(h + 1) * 6] = True
print(f"剔除『夜段 0-3 与 19-23 共 9 个小时块』后的 MAE = {err[~night_mask].mean():,.4f} kW"
      f"（剩余 {int((~night_mask).sum())} 个时段）")

print()
print("--- 0:00 发布：逐钟点的『精确相等』分布（残差 < 1e-9）---")
for h in range(24):
    seg_f = pred[:, h * 6:(h + 1) * 6]
    seg_a = pv_target[:, h * 6:(h + 1) * 6]
    m = np.max(np.abs(seg_f - seg_a), axis=1) < 1e-9
    n = int(m.sum())
    if n:
        print(f"  钟点 {h:2d}:00：精确 {n}/334 天；这些天下该钟点实际值 最大 "
              f"{float(seg_a[m].max()):,.3f} kW、均值 {float(seg_a[m].mean()):,.3f} kW；"
              f"**实际值 > 1 kW 的样本 {int((seg_a[m].max(axis=1) > 1.0).sum())} 个**")

print()
print("--- 0:00 发布：**逐时段（10 分钟粒度）**精确相等的分布 ---")
for h in range(24):
    seg_f = pred[:, h * 6:(h + 1) * 6]
    seg_a = pv_target[:, h * 6:(h + 1) * 6]
    m = np.abs(seg_f - seg_a) < 1e-9
    n = int(m.sum())
    if n:
        ax = seg_a[m]
        print(f"  钟点 {h:2d}:00：时段级精确 {n}/2004；这些时段实际值 最大 {float(ax.max()):,.3f} kW、"
              f"均值 {float(ax.mean()):,.3f} kW；**实际值 > 1 kW 的时段 {int((ax > 1.0).sum())} 个**")
print()
big = exact_mask & (pv_target > 1.0)
print(f"时段级精确且实际 > 1 kW 的时段数 = {int(big.sum())}")
if big.any():
    idx = np.argwhere(big)
    seen = set()
    for di, ti in idx[:12]:
        key = (int(di), int(ti // 6))
        if key in seen:
            continue
        seen.add(key)
        d = dates[int(di)]
        h = int(ti // 6)
        print(f"  样本：{d} 钟点 {h:02d}:00 预报 {pred[di, ti]:,.4f} kW，"
              f"实际该小时 6 段 = {list(np.round(pv_target[di, h * 6:(h + 1) * 6], 4))}")
