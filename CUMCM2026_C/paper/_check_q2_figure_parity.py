"""只读核验：Q2 求解章图号引用的最终一致性（局部编号 1..13）。

## 采用的判据（经队长 2026-09-12 裁定：不重跑流水线，只改正文）

  1. 图位按出现顺序编号 1..13；
  2. 正文引用序列必须**非降**（阅读顺序），且**去重后恰为 1..13**（无跳号、无越界）；
  3. 第 i 个图位的图号 = i，且其**解说**（含该图内容描述的那段）须引用 图 i；
  4. 同一图号被引用多次是**允许**的（复合图在引出句与解说处各点一次），
     但重复的引用之间不得夹入更大的图号（即不得乱序）；
  5. 每个图位至少被引用一次（无孤儿图）。

## 已知的保留不一致

PNG **图内标题**仍是生成脚本 set_title 的旧编号，本修法不重跑流水线，故保留，
在此列出以便复核者知情。
"""

from __future__ import annotations

import pathlib
import re

TARGET = pathlib.Path("CUMCM2026_C/Q2/问题二模型的求解.md")
PAT_PH = re.compile(r"此处插入图：(\S+?\.png)")
PAT_FIG = re.compile(r"图 (\d+)")

TITLE_OLD = {
    "Q2_fig1_daily_energy.png": "图1",
    "Q2_fig2_plan_heatmap.png": "图9",
    "Q2_fig6_price_vs_profile.png": "图6",
    "Q2_fig8_blocks_and_soc.png": "图8",
    "Q2_fig5_daily_cost.png": "图12",
    "Q2_fig9_economics.png": "图16",
    "Q2_fig3_target_days.png": "图10",
    "Q2_fig4_target_days_soc.png": "图11",
    "Q2_fig10_forecast_error.png": "图17",
    "Q2_fig11_emergency_daily.png": "图18",
    "Q2_fig12_variant_target_days.png": "图19",
    "Q2_fig13_cost_comparison.png": "图20",
    "Q2_fig7_monthly.png": "图14",
}


def main() -> int:
    lines = TARGET.read_text(encoding="utf-8").splitlines()

    ph = []
    for i, line in enumerate(lines, 1):
        m = PAT_PH.search(line)
        if m:
            ph.append((i, m.group(1).split("/")[-1]))

    refs = [(i, int(m.group(1))) for i, line in enumerate(lines, 1)
            for m in PAT_FIG.finditer(line)]
    seq = [n for _, n in refs]

    checks: list[tuple[str, bool, str]] = []
    n_ph = len(ph)
    checks.append((f"图位数 13", n_ph == 13, str(n_ph)))
    checks.append(("引用序列非降（阅读顺序）",
                   all(b >= a for a, b in zip(seq, seq[1:])), str(seq)))
    checks.append(("去重后恰为 1..13（无跳号/越界）",
                   sorted(set(seq)) == list(range(1, n_ph + 1)), str(sorted(set(seq)))))
    # 每个图位都应有引用落在其位置附近（该图位之前或之后 6 行内出现其图号）
    orphan = []
    for idx, (ln, name) in enumerate(ph, 1):
        near = [n for l, n in refs if abs(l - ln) <= 6]
        if idx not in near:
            orphan.append((idx, name))
    checks.append(("无孤儿图（每个图位邻域内被引用）", not orphan, str(orphan)))

    print(f"图位 {n_ph} 个，引用 {len(refs)} 处")
    print(f"引用序列：{seq}\n")
    for label, ok, extra in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  -> {extra}" if extra else ""))

    print("\n【已知保留不一致】图内标题仍为旧编号（不重跑流水线）：")
    n_bad = 0
    for idx, (ln, name) in enumerate(ph, 1):
        old = TITLE_OLD.get(name, "?")
        if old != f"图{idx}":
            n_bad += 1
            print(f"  图位 {idx:>2}（正文 图{idx}）  图内印 {old:<4} {name}")
    print(f"  共 {n_bad} 处（已登记于《统稿映射与改动记录》§6.4）")

    n_fail = sum(1 for _, ok, _ in checks if not ok)
    print(f"\n小计：{len(checks) - n_fail}/{len(checks)} 通过")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
