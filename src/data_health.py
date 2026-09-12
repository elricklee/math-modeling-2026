"""附件结构体检（只读表头与时间轴，不参与建模）。

对应《01_题面歧义裁定与符号约定.md》第 4 节"待读附件后必须回填的清单"：
    Q-1 附件 1 的时间点数量与起止时刻
    Q-2 附件 2 的时间点数量与起止时刻
    Q-3 附件 3 的存储结构
    Q-4 附件 4 的时间粒度
    Q-5 ~ Q-8 附件 5 各模板的表头与日期格式
    Q-9 缺失值 / 负值 / 异常值
    Q-10 负载与光伏的实际峰值（供 P9 使用）

运行：
    python -m src.data_health
"""

from __future__ import annotations

import sys
from datetime import datetime, time
from pathlib import Path

from openpyxl import load_workbook

from src.config import RAW_DIR, RESULTS_DIR

ATTACH_DIR = RAW_DIR / "C题"
TEMPLATE_DIR = ATTACH_DIR / "附件5"

# 预览行/列上限（体检只看结构，不看全量数值）
PREVIEW_ROWS = 6
PREVIEW_COLS = 12


def _fmt(v: object) -> str:
    """完整精度格式化：浮点用 repr，避免 %g 丢精度。"""
    if v is None:
        return "·"
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M")
    if isinstance(v, time):
        return v.strftime("%H:%M")
    if isinstance(v, float):
        return repr(v)
    return str(v)


def describe_workbook(path: Path, preview_rows: int = PREVIEW_ROWS,
                      preview_cols: int = PREVIEW_COLS) -> list[str]:
    """返回一个工作簿的结构描述（逐工作表：维度 + 表头 + 前若干行）。"""
    lines: list[str] = []
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        lines.append(f"文件：{path.name}   工作表数 = {len(wb.worksheets)}")
        for ws in wb.worksheets:
            lines.append(f"  [{ws.title}]  max_row={ws.max_row}  max_col={ws.max_column}")
            n = 0
            for row in ws.iter_rows(min_row=1, max_row=min(preview_rows, ws.max_row or 1),
                                    max_col=min(preview_cols, ws.max_column or 1),
                                    values_only=True):
                n += 1
                lines.append(f"    R{n:02d} | " + " | ".join(_fmt(v) for v in row))
            if (ws.max_row or 0) > preview_rows:
                lines.append(f"    ... 共 {ws.max_row} 行")
    finally:
        wb.close()
    return lines


def describe_sheets(path: Path) -> list[str]:
    """只看工作表名与维度，不读单元格（用于大文件）。"""
    lines: list[str] = []
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            lines.append(f"  [{ws.title}]  max_row={ws.max_row}  max_col={ws.max_column}")
    finally:
        wb.close()
    return lines


def describe_time_axis(path: Path, sheet: str | None = None,
                       label: str = "") -> list[str]:
    """读取第 1 列作为时间轴，报告点数、起止、步长与首尾样本。"""
    lines: list[str] = []
    wb = load_workbook(path, read_only=True, data_only=True)
    try:
        ws = wb[sheet] if sheet else wb.worksheets[0]
        col = [r[0] for r in ws.iter_rows(min_col=1, max_col=1, values_only=True)]
        lines.append(f"  时间轴列（工作表 {ws.title}，共 {len(col)} 个单元格）：")
        head = col[:3]
        tail = col[-3:]
        lines.append("    首 3：" + " | ".join(_fmt(v) for v in head))
        lines.append("    末 3：" + " | ".join(_fmt(v) for v in tail))
        first_dt = next((v for v in col if isinstance(v, (datetime, time))), None)
        last_dt = next((v for v in reversed(col) if isinstance(v, (datetime, time))), None)
        if first_dt is not None and last_dt is not None:
            lines.append(f"    起 = {_fmt(first_dt)}   止 = {_fmt(last_dt)}")
    finally:
        wb.close()
    if label:
        lines.insert(0, label)
    return lines


def main() -> None:
    out: list[str] = []
    add = out.append

    add("# C 题附件结构体检报告")
    add("")
    add("> 本文件由 `python -m src.data_health` 自动生成，仅用于回填《01_题面歧义裁定与符号约定.md》第 4 节。")
    add("> 原则：只读表头与时间轴，不读数值用于建模。")
    add("")

    # ---------- 附件 1 ----------
    add("## Q-1 附件 1（电价 + 负载 + 光伏预测）")
    add("")
    add("```")
    add("\n".join(describe_workbook(ATTACH_DIR / "附件1.xlsx", preview_rows=8)))
    add("```")
    add("")

    # ---------- 附件 2 / 3 / 4 ----------
    for name, q in (("附件2.xlsx", "Q-2 附件 2（负载 + 光伏实际）"),
                    ("附件3.xlsx", "Q-3 附件 3（光伏预报）"),
                    ("附件4.xlsx", "Q-4 附件 4（电价）")):
        p = ATTACH_DIR / name
        add(f"## {q}")
        add("")
        add("```")
        add("\n".join(describe_sheets(p)))
        add("\n".join(describe_time_axis(p)))
        add("```")
        add("")
        add("前 4 行预览：")
        add("")
        add("```")
        add("\n".join(describe_workbook(p, preview_rows=4, preview_cols=6)[1:]))
        add("```")
        add("")

    # ---------- 附件 5 模板 ----------
    add("## Q-5 ~ Q-8 附件 5 结果模板（完整表头，文件很小故全读）")
    add("")
    for f in sorted(TEMPLATE_DIR.glob("result*.xlsx")):
        add(f"### {f.name}")
        add("")
        add("```")
        add("\n".join(describe_workbook(f, preview_rows=8, preview_cols=14)))
        add("```")
        add("")

    text = "\n".join(out)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    dest = RESULTS_DIR / "attachment_structure.md"
    dest.write_text(text, encoding="utf-8")
    print(text)
    print(f"\n[written] {dest}", file=sys.stderr)


if __name__ == "__main__":
    main()
