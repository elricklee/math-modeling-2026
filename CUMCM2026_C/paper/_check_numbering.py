"""只读核验：统稿改动后的编号一致性检查。可重复运行。"""

from __future__ import annotations

import hashlib
import pathlib
import re

ROOT = pathlib.Path("CUMCM2026_C")
FILES = {
    "Q1建立": ROOT / "Q1/问题一模型的建立.md",
    "Q1求解": ROOT / "Q1/问题一模型的求解.md",
    "Q2建立": ROOT / "Q2/问题二模型的建立.md",
    "Q2求解": ROOT / "Q2/问题二模型的求解.md",
    "骨架": ROOT / "paper/paper_skeleton.md",
}

PAT_LABEL = re.compile(r"(?m)^\*\*表 ([\d-]+)")
PAT_REF_TBL = re.compile(r"表 ([\d]+-[\d]+)")
PAT_REF_TMPL = re.compile(r"题目表 ?([\d]+)")
PAT_REF_FIG = re.compile(r"图 ([\d]+)")
PAT_PLACEHOLDER = re.compile(r"此处插入图：(\S+)")


def fp(path: pathlib.Path) -> tuple[int, int, str]:
    b = path.read_bytes()
    return len(b.decode("utf-8").splitlines()), len(b), hashlib.sha256(b).hexdigest()[:16]


def main() -> int:
    print("=" * 78)
    print("四章 + 骨架：指纹与编号清单")
    print("=" * 78)
    for name, path in FILES.items():
        t = path.read_text(encoding="utf-8")
        lines, size, sha = fp(path)
        labels = PAT_LABEL.findall(t)
        refs = PAT_REF_TBL.findall(t)
        tmpl = PAT_REF_TMPL.findall(t)
        figs = PAT_REF_FIG.findall(t)
        ph = PAT_PLACEHOLDER.findall(t)
        print(f"\n[{name}] {path.name}")
        print(f"  五元组: {lines} 行 / {size} B / sha16 {sha}")
        print(f"  表标签 ({len(labels)}): {labels}")
        print(f"  表引用 ({len(refs)}): 去重 {sorted(set(refs), key=lambda s: (len(s), s))}")
        print(f"  题目表引用: {sorted(set(tmpl))}")
        print(f"  图引用 ({len(figs)}): 去重 {sorted({int(x) for x in figs})}")
        print(f"  插图占位符: {len(ph)}")

    print("\n" + "=" * 78)
    print("跨章核验")
    print("=" * 78)
    q1 = FILES["Q1求解"].read_text(encoding="utf-8")
    q2b = FILES["Q2建立"].read_text(encoding="utf-8")
    q2s = FILES["Q2求解"].read_text(encoding="utf-8")
    sk = FILES["骨架"].read_text(encoding="utf-8")

    checks: list[tuple[str, bool, str]] = []

    # 1. Q1 无旧编号残留
    checks.append((
        "Q1 两章无 表 1-x 残留",
        not re.search(r"表 1-\d", q1 + FILES["Q1建立"].read_text(encoding="utf-8")),
        "",
    ))
    # 2. Q2 无旧编号残留
    checks.append(("Q2 两章无 表 2-x 残留", not re.search(r"表 2-\d", q2b + q2s), ""))
    # 3. 表 1-1 撞号已消除：Q1 建立章只剩「表 5-0」，不再有符号表 1-1
    q1b_labels = PAT_LABEL.findall(FILES["Q1建立"].read_text(encoding="utf-8"))
    checks.append((
        "Q1 建立章表标签仅 表 5-0（符号表 1-1 撞号已消除）",
        q1b_labels == ["5-0"],
        str(q1b_labels),
    ))
    # 4. 骨架符号表小节齐备（编号表 + 五小节，小节为 #### 层级）
    checks.append((
        "骨架 §四 含 表 4-1 与 4.1-4.5 五小节",
        "**表 4-1" in sk and all(f"#### 4.{i}" in sk for i in range(1, 6)),
        "",
    ))
    # 5. 骨架旧符号已清除。
    #    例外：在「禁用说明」语境中允许出现旧符号（如「勿写作 $g_t^{em}$」）——
    #    这类出现是**规则本身**，不是残留。判据须区分「作为符号使用」与「作为禁例引用」，
    #    否则判据会把正确的写法判成缺陷（与 D3b(e) 同类的假阳性）。
    forbidden_ctx = re.compile(r"勿写作|不要写作|弃用|不得写作")
    stale = []
    for m in re.finditer(r"g_t\^\{em\}|\\lambda_\{em\}|\$E_\{\\max\}\$", sk):
        line_start = sk.rfind("\n", 0, m.start()) + 1
        line_end = sk.find("\n", m.end())
        line = sk[line_start: line_end if line_end != -1 else len(sk)]
        if not forbidden_ctx.search(line):
            stale.append(m.group(0))
    checks.append(("骨架 §四 旧符号已清除（禁例引用除外）", not stale, str(stale)))
    # 6. 图号。
    #    注意：Q2 求解章的图号引用**存在原章固有的损坏**（13 图位 vs 14 引用、图 5 重号），
    #    已登记于《统稿映射与改动记录》§六。故此处只核「集合范围」，不核「与图位一一对应」。
    q1_figs = sorted({int(x) for x in PAT_REF_FIG.findall(q1)})
    q2_figs = sorted({int(x) for x in PAT_REF_FIG.findall(q2s)})
    sk_figs = sorted({int(x) for x in PAT_REF_FIG.findall(sk)})
    checks.append(("Q1 图号恰为 1-7", q1_figs == list(range(1, 8)), str(q1_figs)))
    checks.append((
        "Q2 图号落在 1-14（原章状态；损坏已登记待裁）",
        min(q2_figs) >= 1 and max(q2_figs) <= 14,
        str(q2_figs),
    ))
    checks.append((
        "Q2 图位数为 13",
        len(PAT_PLACEHOLDER.findall(q2s)) == 13,
        str(len(PAT_PLACEHOLDER.findall(q2s))),
    ))
    # 6b. 骨架的 Q3/Q4 提示图号须 >= 21（避开 Q1 的 1-7 与 Q2 的 1-14）
    q34_hint_figs = sorted({n for n in sk_figs if n >= 21})
    clash = sorted({n for n in sk_figs if 1 <= n <= 20})
    checks.append((
        "骨架 Q3/Q4 图号提示 >= 21（不与 Q1/Q2 冲突）",
        bool(q34_hint_figs) and min(q34_hint_figs) >= 21,
        str(q34_hint_figs),
    ))
    # 6c. 骨架 §五 合法继承 Q1 的 图 1-7（合并时并入），故不判「1-20 一律冲突」——
    #     那会把合法继承判成缺陷（判据过宽 = 假阳性）。只须确认继承的恰是 1-7。
    q1_in_sk = sorted({n for n in sk_figs if n <= 7})
    checks.append(("骨架 §五 继承的 Q1 图号恰为 1-7", q1_in_sk == list(range(1, 8)), str(q1_in_sk)))
    # 7. 表号连续性：Q2 建立 6-1 + 求解 6-2..6-21
    q2b_labels2 = PAT_LABEL.findall(q2b)
    q2s_labels2 = PAT_LABEL.findall(q2s)
    expect_q2 = ["6-1"] + [f"6-{i}" for i in range(2, 22)]
    checks.append((
        "Q2 表号连续 6-1..6-21（建立 1 张 + 求解 20 张）",
        q2b_labels2 + q2s_labels2 == expect_q2,
        f"{q2b_labels2} + {len(q2s_labels2)} 张",
    ))
    # 8. Q1 表号：5-0（建立）+ 5-2..5-7（求解），5-1 保留给统一符号表 4-1 之后的位置
    q1s_labels2 = PAT_LABEL.findall(q1)
    checks.append((
        "Q1 表号 5-2..5-7（求解 6 张）",
        q1s_labels2 == [f"5-{i}" for i in range(2, 8)],
        str(q1s_labels2),
    ))

    for label, ok, extra in checks:
        mark = "PASS" if ok else "FAIL"
        print(f"  [{mark}] {label}" + (f"  -> {extra}" if extra else ""))

    n_fail = sum(1 for _, ok, _ in checks if not ok)
    print(f"\n小计：{len(checks) - n_fail}/{len(checks)} 通过")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
