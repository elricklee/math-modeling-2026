"""把仓库重构为 skill 期望的"按问分目录"结构（幂等、可复核）。

目标结构（相对仓库根）::

    CUMCM2026_C/
      00_problem/           题目原文 + 只读附件（唯一权威输入）
        C题.txt
        附件/               附件1~4 + 附件5/result*.xlsx 模板
        preview/            题目 PDF 渲染页
      附件/                 指向 00_problem/附件 的说明（避免误找）
      common/               跨问共享
        code/               通用代码包（paths / io_attachments / check_data / validate_results）
        docs/               跨问口径文档 + 机读契约
        diagnostics/        数据核查与验收报告 JSON
        tools/              可复现脚本
      Q1/ Q2/ Q3/ Q4/       每问：脚本 + outputs/ + 两份章节 Markdown
      paper/                论文汇总与 Univer 分析容器
    CUMCM2026Problems/      原始题目目录（保持不动，作为只读原始副本）

设计原则
--------
* **不删除内容**：只搬运；覆盖前若内容不同则备份为 ``*.pre-restructure.bak``。
* **唯一权威输入**：附件只保留 ``00_problem/附件/`` 一份，旧的 ``data/`` 树清空。
* **可追溯**：搬运清单写入 ``common/docs/_restructure_manifest.json``。

用法::

    .venv\\Scripts\\python.exe CUMCM2026_C/common/tools/restructure_repo.py --dry-run
    .venv\\Scripts\\python.exe CUMCM2026_C/common/tools/restructure_repo.py
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

def find_repo_root(start: Path) -> Path:
    """从 start 向上找到仓库根。

    判据（满足其一即可）：存在 ``.git`` 目录，或同时存在 ``README.md`` 与 ``.gitignore``。
    用标记法而不是数 ``parents[N]``，因为本脚本自身会被搬运（位置会变）。
    """
    for cand in [start, *start.parents]:
        if (cand / ".git").exists():
            return cand
        if (cand / "README.md").exists() and (cand / ".gitignore").exists():
            return cand
    raise SystemExit(f"无法从 {start} 定位仓库根")


ROOT = find_repo_root(Path(__file__).resolve().parent)
NEW = ROOT / "CUMCM2026_C"
SELF = Path(__file__).resolve()

# 生成的空目录占位（skill 未规定，但每问都需要）
QUESTION_DIRS = ["Q1", "Q2", "Q3", "Q4"]


def plan_moves() -> list[tuple[Path, Path, str]]:
    """返回 (源, 目标, 说明)。源不存在时会被跳过。"""
    moves: list[tuple[Path, Path, str]] = []

    # ---- common/code：通用代码包 ----
    for f in sorted((ROOT / "src" / "CUMCM2026_C").glob("*.py")):
        moves.append((f, NEW / "common" / "code" / f.name, "通用代码模块"))

    # ---- common/docs：跨问口径文档 ----
    docs = ROOT / "docs"
    for name in [
        "problem_c_contract.json",
        "model_variables.json",
        "C题_统一分析结论.md",
        "C题_三方一致性核对.md",
        "C题_问题分析与数学建模框架.md",
        "C题_数据工程与结果规格.md",
        "C题_论文框架与交付清单.md",
    ]:
        moves.append((docs / name, NEW / "common" / "docs" / name, "跨问口径文档"))

    # ---- common/diagnostics：核查与验收报告 ----
    proc = ROOT / "data" / "processed"
    for f in sorted((proc / "CUMCM2026_C").glob("*.json")):
        moves.append((f, NEW / "common" / "diagnostics" / f.name, "核查/验收报告"))
    for name in ["attachment_overview.json", "env_audit.json", "skill_audit.json"]:
        moves.append((proc / name, NEW / "common" / "diagnostics" / name, "核查报告"))

    # ---- common/tools：可复现脚本 ----
    for f in sorted((ROOT / "tools").glob("*.py")):
        dst = NEW / "common" / "tools" / f.name
        if f.resolve() == SELF:
            dst = NEW / "common" / "tools" / "restructure_repo.py"
        moves.append((f, dst, "可复现脚本"))

    # ---- 00_problem：题目原文 ----
    moves.append((ROOT / "CUMCM2026Problems" / "C题" / "C题.txt",
                  NEW / "00_problem" / "C题.txt", "题目原文"))
    for name in ["C题_pdf_layout.txt", "C题_pdf_raw.txt"]:
        moves.append((proc / name, NEW / "00_problem" / name, "PDF 文本派生"))
    for f in sorted((proc / "problem_preview").glob("*.png")):
        moves.append((f, NEW / "00_problem" / "preview" / f.name, "PDF 渲染页"))

    # ---- 00_problem/附件：唯一权威只读输入（原 data/raw 副本） ----
    raw = ROOT / "data" / "raw" / "CUMCM2026_C"
    for f in sorted(raw.glob("附件*.xlsx")):
        moves.append((f, NEW / "00_problem" / "附件" / f.name, "附件（只读输入）"))
    for f in sorted((raw / "附件5").glob("*.xlsx")):
        moves.append((f, NEW / "00_problem" / "附件" / "附件5" / f.name,
                      "结果模板（只读输入）"))

    # ---- paper：论文骨架与 Univer 分析容器 ----
    moves.append((ROOT / "reports" / "CUMCM2026_C" / "paper_skeleton.md",
                  NEW / "paper" / "paper_skeleton.md", "论文骨架"))
    moves.append((ROOT / "reports" / "CUMCM2026_C_analysis.univer",
                  NEW / "paper" / "CUMCM2026_C_analysis.univer", "Univer 分析容器"))

    return moves


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    moves = plan_moves()
    print(f"计划搬运 {len(moves)} 个文件 -> {NEW.relative_to(ROOT)}")
    print("=" * 78)

    done: list[tuple[Path, Path, str]] = []
    skipped: list[tuple[Path, str]] = []
    backed: list[Path] = []

    for src, dst, why in moves:
        if not src.exists():
            skipped.append((src, why))
            continue
        if args.dry_run:
            print(f"  [dry] {src.relative_to(ROOT)}  ->  {dst.relative_to(ROOT)}")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            if dst.read_bytes() == src.read_bytes():
                src.unlink()
                done.append((src, dst, why))
                continue
            bak = dst.with_suffix(dst.suffix + ".pre-restructure.bak")
            shutil.copy2(dst, bak)
            backed.append(bak)
        shutil.move(str(src), str(dst))
        done.append((src, dst, why))

    if args.dry_run:
        print("=" * 78)
        print(f"[dry-run] 可搬运 {len(moves) - len(skipped)}，源缺失 {len(skipped)}")
        for s, why in skipped:
            print(f"   - 缺失 {s.relative_to(ROOT)}  ({why})")
        return

    # ---- 建立每问目录骨架 ----
    for q in QUESTION_DIRS:
        for sub in [q, f"{q}/outputs", f"{q}/outputs/figures"]:
            d = NEW / sub
            d.mkdir(parents=True, exist_ok=True)
            keep = d / ".gitkeep"
            if not keep.exists():
                keep.write_text("", encoding="utf-8")

    # ---- 清理旧目录（仅当已空） ----
    removed: list[str] = []
    for old in ["src/CUMCM2026_C", "docs", "tools",
                "data/raw/CUMCM2026_C", "data/processed/CUMCM2026_C",
                "data/processed/problem_preview", "reports/CUMCM2026_C"]:
        p = ROOT / old
        if not p.exists():
            continue
        leftovers = [x for x in p.rglob("*") if x.is_file() and x.name != ".gitkeep"]
        if leftovers:
            print(f"  ! 保留 {old}（仍有 {len(leftovers)} 个文件）")
            for x in leftovers[:5]:
                print(f"      {x.relative_to(ROOT)}")
            continue
        shutil.rmtree(p, ignore_errors=True)
        removed.append(old)

    print("=" * 78)
    print(f"搬运 {len(done)}，跳过 {len(skipped)}，备份覆盖 {len(backed)}，清理旧目录 {len(removed)}")
    if removed:
        print("  已清理: " + ", ".join(removed))

    manifest = NEW / "common" / "docs" / "_restructure_manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(
        json.dumps(
            {
                "moved": [{"from": str(a.relative_to(ROOT)), "to": str(b.relative_to(ROOT)),
                           "why": c} for a, b, c in done],
                "skipped": [{"from": str(a.relative_to(ROOT)), "why": b} for a, b in skipped],
                "backedUp": [str(b.relative_to(ROOT)) for b in backed],
                "removedOldDirs": removed,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"清单写入 {manifest.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
