"""把 markdown 母本转换为"Univer Doc 友好"的规范化大纲。

设计取舍：
  * 表格：转成**等宽 ASCII 网格**（保留全部单元格内容与行列结构），
    避免依赖 insertTableFromData 的位置语义；文档仍完整可读。
  * 代码块 ```：转成以 "│ " 前缀的等宽段落，保留内容与顺序。
  * 引用 > ：保留 "▸ " 前缀，形成视觉层次。
  * 标题：`# ` → `█ `、`## ` → `■ `、`### ` → `▸▸ `、`#### ` → `▸▸▸ `，
    便于在 Univer Doc 中按前缀识别层级。
  * 去掉 markdown 强调标记 ** ` 与链接语法，保留纯文本。

输出：docs/_doc_outline.txt（UTF-8），并打印统计。

用法：
    python tools/md_to_outline.py
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "C题_问题分析与数学建模框架.md"
OUT = ROOT / "docs" / "_doc_outline.txt"

HEAD_PREFIX = {1: "█ ", 2: "■ ", 3: "▸▸ ", 4: "▸▸▸ "}


def strip_inline(text: str) -> str:
    """去掉行内 markdown 标记，保留可读纯文本。"""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"\1", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1", text)
    text = text.replace("\\|", "|")
    return text.rstrip()


def parse_table(lines: list[str], start: int) -> tuple[list[list[str]], int]:
    """从 start 起解析一张 GFM 表格，返回 (rows, next_index)。"""
    rows: list[list[str]] = []
    i = start
    while i < len(lines) and lines[i].strip().startswith("|"):
        raw = lines[i].strip()
        if re.match(r"^\|[\s:\-|]+\|$", raw):      # 分隔行
            i += 1
            continue
        cells = [c.strip() for c in raw.strip("|").split("|")]
        rows.append([strip_inline(c) for c in cells])
        i += 1
    return rows, i


def render_ascii_table(rows: list[list[str]]) -> list[str]:
    """把表格渲染成等宽 ASCII 网格。"""
    if not rows:
        return []
    ncol = max(len(r) for r in rows)
    norm = [r + [""] * (ncol - len(r)) for r in rows]
    widths = [max(len(r[c]) for r in norm) for c in range(ncol)]
    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"

    def fmt(row: list[str]) -> str:
        return "|" + "|".join(f" {row[c].ljust(widths[c])} " for c in range(ncol)) + "|"

    out = [sep, fmt(norm[0]), sep]
    out += [fmt(r) for r in norm[1:]]
    out.append(sep)
    return out


def main() -> None:
    lines = SRC.read_text(encoding="utf-8").splitlines()
    out: list[str] = []

    i = 0
    stats = {"heading": 0, "table": 0, "tableRows": 0, "codeBlock": 0,
             "quote": 0, "bullet": 0, "para": 0}
    in_code = False

    while i < len(lines):
        raw = lines[i]
        s = raw.strip()

        # ---------- 代码块 ----------
        if s.startswith("```"):
            if not in_code:
                in_code = True
                stats["codeBlock"] += 1
                out.append("")                      # 代码块前留白
            else:
                in_code = False
                out.append("")                      # 代码块后留白
            i += 1
            continue
        if in_code:
            out.append("│ " + raw.rstrip())
            i += 1
            continue

        # ---------- 空行 ----------
        if not s:
            if out and out[-1] != "":
                out.append("")
            i += 1
            continue

        # ---------- 水平线 ----------
        if re.match(r"^-{3,}$|^\*{3,}$|^_{3,}$", s):
            out.append("─" * 60)
            i += 1
            continue

        # ---------- 标题 ----------
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            lvl = len(m.group(1))
            title = strip_inline(m.group(2))
            if out and out[-1] != "":
                out.append("")
            out.append(HEAD_PREFIX[lvl] + title)
            stats["heading"] += 1
            i += 1
            continue

        # ---------- 表格 ----------
        if s.startswith("|"):
            rows, nxt = parse_table(lines, i)
            blocks = render_ascii_table(rows)
            if out and out[-1] != "":
                out.append("")
            out.extend(blocks)
            out.append("")
            stats["table"] += 1
            stats["tableRows"] += len(rows)
            i = nxt
            continue

        # ---------- 引用 ----------
        if s.startswith(">"):
            body = strip_inline(re.sub(r"^>\s?", "", s))
            out.append("▸ " + body)
            stats["quote"] += 1
            i += 1
            continue

        # ---------- 列表 ----------
        m = re.match(r"^([-*+]|\d+\.)\s+(.*)$", s)
        if m:
            body = strip_inline(m.group(2))
            marker = "• " if not m.group(1)[0].isdigit() else m.group(1) + " "
            out.append("  " + marker + body)
            stats["bullet"] += 1
            i += 1
            continue

        # ---------- 普通段落 ----------
        out.append(strip_inline(s))
        stats["para"] += 1
        i += 1

    # 收尾：去掉尾部多余空行
    while out and out[-1] == "":
        out.pop()

    OUT.write_text("\n".join(out), encoding="utf-8")

    print(f"源文件: {SRC.name}  ({len(lines)} 行)")
    print(f"输出  : {OUT.name}  ({len(out)} 行, {OUT.stat().st_size:,} 字节)")
    print()
    print("转换统计:")
    for k, v in stats.items():
        print(f"  {k:12s} = {v}")
    print()
    print("前 12 行预览:")
    for line in out[:12]:
        print("   ", line[:96])
    print("...")
    print("末 6 行预览:")
    for line in out[-6:]:
        print("   ", line[:96])


if __name__ == "__main__":
    main()
