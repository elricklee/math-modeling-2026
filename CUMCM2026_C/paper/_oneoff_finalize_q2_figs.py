"""一次性脚本：按「图位顺序」把 Q2 求解章的全部图号引用改成单调序列。

## 原则（唯一判据，无需推测）

正文里第 i 处「图 N」引用（按出现顺序）对应**第 i 个图位**，因此应改成 图 i。
其中同一张复合图被引用两次的情形（如 2×2 布局的四日期图分两处解说）会产生重复号，
故最终把引用序列规整为**非降**，并保持「每个图位在其解说处被点到」。

本脚本以**当前磁盘状态**为输入（幂等：已是单调且与图位对齐则不动）。
"""

from __future__ import annotations

import hashlib
import pathlib
import re
import sys

TARGET = pathlib.Path("CUMCM2026_C/Q2/问题二模型的求解.md")
PAT_PH = re.compile(r"此处插入图：(\S+?\.png)")
PAT_FIG = re.compile(r"图 (\d+)")

# 逐处目标值（按行号），由「图位顺序 = 阅读顺序」推出：
#   L61  图位1 fig1_daily_energy      -> 1
#   L89  引出句（热力图的铺垫，前瞻引用）-> 2
#   L93  热力图解说  = 图位2           -> 2
#   L97  图位3 fig6_price_vs_profile  -> 3
#   L121 图位4 fig8_blocks_and_soc    -> 4
#   L148 图位5 fig5_daily_cost        -> 5
#   L152 图位6 fig9_economics         -> 6
#   L215 图位7 fig3_target_days       -> 7
#   L263 图位8 fig4_target_days_soc   -> 8
#   L362 图位9  fig10_forecast_error  -> 9
#   L366 图位10 fig11_emergency_daily -> 10
#   L370 图位11 fig12_variant_target_days -> 11
#   L374 图位12 fig13_cost_comparison -> 12
#   L409 图位13 fig7_monthly          -> 13
TARGET_BY_LINE: dict[int, int] = {
    61: 1, 89: 2, 93: 2, 97: 3, 121: 4, 148: 5, 152: 6,
    215: 7, 263: 8, 362: 9, 366: 10, 370: 11, 374: 12, 409: 13,
}


def fingerprint(path: pathlib.Path) -> tuple[int, int, str]:
    b = path.read_bytes()
    return len(b.decode("utf-8").splitlines()), len(b), hashlib.sha256(b).hexdigest()[:16]


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    print("逐处改写（目标值由『图位顺序 = 阅读顺序』推出）:")
    n = 0
    for ln, want in TARGET_BY_LINE.items():
        line = lines[ln - 1]
        found = [int(m.group(1)) for m in PAT_FIG.finditer(line)]
        if not found:
            print(f"  L{ln}: 无引用，跳过")
            continue
        cur = found[0]
        if cur == want:
            print(f"  L{ln}: 图 {cur} 已正确")
            continue
        lines[ln - 1] = PAT_FIG.sub(lambda m: f"图 {want}", line, count=1)
        n += 1
        print(f"  L{ln}: 图 {cur} -> 图 {want}")

    new_text = "".join(lines)

    # 核验 1：图位逐字不变
    assert list(PAT_PH.findall(new_text)) == list(PAT_PH.findall(text)), "占位符被改动"
    # 核验 2：行数不变
    assert len(new_text.splitlines()) == len(text.splitlines()), "行数变化"
    # 核验 3：引用序列必须非降，且首项为 1
    seq = [int(m.group(1)) for m in PAT_FIG.finditer(new_text)]
    assert seq[0] == 1, f"首项不是 1：{seq}"
    assert all(b >= a for a, b in zip(seq, seq[1:])), f"引用序列非单调：{seq}"
    # 核验 4：去重后应覆盖 1..13
    assert sorted(set(seq)) == list(range(1, 14)), f"去重集合不符：{sorted(set(seq))}"

    print(f"\n改后引用序列：{seq}")
    print(f"去重：{sorted(set(seq))}")
    print(f"改写 {n} 处")
    if n == 0:
        print("无需改动（脚本已幂等）。")
        return 0
    print(f"指纹（改前）：{fingerprint(TARGET)}")
    TARGET.write_text(new_text, encoding="utf-8")
    print(f"指纹（改后）：{fingerprint(TARGET)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
