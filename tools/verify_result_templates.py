"""精确核对附件5 五个结果模板的行列结构（用于收敛阶段的裁定）。

输出：每个工作表的真实维度、时间标签序列（首尾各若干）、列名全序列（用于核验列错位）。

用法：
    python -c "..."  # 或直接 python tools/verify_result_templates.py
"""

from __future__ import annotations

import json
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "data" / "raw" / "CUMCM2026_C" / "附件5"


def norm(value: object) -> str:
    """把 Excel 时间序列号转成 H:MM，其余原样转字符串。"""
    if value is None:
        return ""
    if isinstance(value, float) and 0 <= value < 1:
        minutes = round(value * 24 * 60)
        return f"{minutes // 60}:{minutes % 60:02d}"
    return str(value).strip()


def describe(path: Path) -> dict:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    info: dict = {"file": path.name, "sheets": []}
    for ws in wb.worksheets:
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue
        header = [norm(c) for c in rows[0]]
        # 第一列的表标签（去掉表头）
        first_col = [norm(r[0]) for r in rows[1:] if r and r[0] is not None]
        sheet = {
            "name": ws.title,
            "max_row": ws.max_row,
            "max_col": ws.max_column,
            "header_len": len(header),
            "header_head": header[:6],
            "header_tail": header[-6:],
            "first_col_count": len(first_col),
            "first_col_head": first_col[:4],
            "first_col_tail": first_col[-4:],
        }
        info["sheets"].append(sheet)
    wb.close()
    return info


def main() -> None:
    report = [describe(p) for p in sorted(TEMPLATES.glob("*.xlsx"))]
    out = ROOT / "data" / "processed" / "CUMCM2026_C"
    out.mkdir(parents=True, exist_ok=True)
    dest = out / "template_structure.json"
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    for item in report:
        print("=" * 78)
        print(f"FILE {item['file']}")
        for sheet in item["sheets"]:
            print(f"  SHEET {sheet['name']!r}  max_row={sheet['max_row']} "
                  f"max_col={sheet['max_col']}")
            print(f"    header_len={sheet['header_len']}")
            print(f"    header      head={sheet['header_head']}")
            print(f"    header      tail={sheet['header_tail']}")
            print(f"    first_col({sheet['first_col_count']}) head={sheet['first_col_head']}")
            print(f"    first_col({sheet['first_col_count']}) tail={sheet['first_col_tail']}")
    print(f"\n结构化结果写入 {dest}")


if __name__ == "__main__":
    main()
