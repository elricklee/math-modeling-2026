"""深挖附件 5 模板的行列标签，确定时间标签约定与尾列含义。

关注点：
  * `result1.xlsx` 的"计划购电量"共 145 行，但一天只有 144 个 10 分钟区间
    —— 列 A 的 144 个标签究竟是哪 144 个区间？
  * `result2.xlsx` 的"计划购电量"共 147 列，但一天只有 144 个 10 分钟区间
    —— 末尾多出的 2 列是什么？
"""

from __future__ import annotations

import sys
from pathlib import Path

from openpyxl import load_workbook

from src.config import RAW_DIR, RESULTS_DIR

T = RAW_DIR / "C题" / "附件5"


def col_a(path: Path, sheet: str) -> list[object]:
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        return [r[0] for r in wb[sheet].iter_rows(min_col=1, max_col=1, values_only=True)]
    finally:
        wb.close()


def row1(path: Path, sheet: str) -> list[object]:
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        return list(next(wb[sheet].iter_rows(min_row=1, max_row=1, values_only=True)))
    finally:
        wb.close()


def compact(label: str, values: list[object], head: int = 6, tail: int = 6) -> list[str]:
    out = [f"{label}  len={len(values)}"]
    shown = list(values[:head])
    out.append("  head: " + " | ".join("·" if v is None else str(v) for v in shown))
    out.append("  tail: " + " | ".join("·" if v is None else str(v) for v in values[-tail:]))
    nonempty = [v for v in values if v is not None]
    out.append(f"  非空个数 = {len(nonempty)}")
    return out


def main() -> None:
    lines: list[str] = []
    add = lines.append

    add("## result1.xlsx / 计划购电量 列A（时间段标签）")
    add("")
    add("\n".join(compact("列A", col_a(T / "result1.xlsx", "计划购电量"), head=8, tail=4)))
    add("")

    add("## result1.xlsx / 充放电量 全表")
    wb = load_workbook(T / "result1.xlsx", read_only=True, data_only=True)
    try:
        for r in wb["充放电量"].iter_rows(values_only=True):
            add("  " + " | ".join("·" if v is None else str(v) for v in r))
    finally:
        wb.close()
    add("")

    for f in ("result2.xlsx", "result3.xlsx", "result4-2.xlsx", "result4-3.xlsx"):
        for sh in ("计划购电量", "调整购电量"):
            p = T / f
            wb = load_workbook(p, read_only=True, data_only=True)
            try:
                if sh not in wb.sheetnames:
                    continue
            finally:
                wb.close()
            add(f"## {f} / {sh} 第1行（147 列的表头）")
            add("")
            add("\n".join(compact("表头", row1(p, sh), head=8, tail=8)))
            add("")

    # 相邻标签差：确认真的是 10 分钟一档
    a = [v for v in col_a(T / "result1.xlsx", "计划购电量") if v is not None]
    add("## result1 列A 相邻标签（前 4 个，后 4 个）")
    add("")
    add("  " + " | ".join(str(v) for v in a[1:5]))
    add("  " + " | ".join(str(v) for v in a[-4:]))
    add("")

    text = "\n".join(lines)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    dest = RESULTS_DIR / "template_labels.md"
    dest.write_text(text, encoding="utf-8")
    sys.stdout.write(text + "\n")


if __name__ == "__main__":
    main()
