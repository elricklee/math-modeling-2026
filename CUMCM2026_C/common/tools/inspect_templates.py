"""检查附件5模板文件与附件1的工作表结构，输出到 CUMCM2026_C/common/diagnostics 供后续引用。"""

from __future__ import annotations

import json
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parents[1]
ATTACH = ROOT / "CUMCM2026Problems" / "C题" / "附件"
OUT = ROOT / "data" / "processed"
OUT.mkdir(parents=True, exist_ok=True)


def first_nonempty(ws, col: int, limit: int = 12) -> list[object]:
    vals: list[object] = []
    for row in ws.iter_rows(min_row=1, max_row=limit, min_col=col, max_col=col, values_only=True):
        vals.append(row[0])
    return vals


def last_nonempty(ws, col: int, limit: int = 6) -> list[object]:
    vals: list[object] = []
    start = max(1, ws.max_row - limit + 1)
    for row in ws.iter_rows(min_row=start, max_row=ws.max_row, min_col=col, max_col=col,
                            values_only=True):
        vals.append(row[0])
    return vals


def describe_file(path: Path) -> dict:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    info: dict = {"file": path.name, "sheets": []}
    for ws in wb.worksheets:
        sheet_info: dict = {
            "name": ws.title,
            "max_row": ws.max_row,
            "max_col": ws.max_column,
        }
        # 每个工作表取前 4 行做表头/样例行
        head = []
        for row in ws.iter_rows(min_row=1, max_row=min(4, ws.max_row),
                                max_col=min(8, ws.max_column), values_only=True):
            head.append(["" if c is None else c for c in row])
        sheet_info["head"] = head
        tail = []
        for row in ws.iter_rows(min_row=max(1, ws.max_row - 2), max_row=ws.max_row,
                                max_col=min(8, ws.max_column), values_only=True):
            tail.append(["" if c is None else c for c in row])
        sheet_info["tail"] = tail
        info["sheets"].append(sheet_info)
    wb.close()
    return info


def main() -> None:
    report: dict = {"templates": [], "attachment1": None}

    for path in sorted((ATTACH / "附件5").glob("*.xlsx")):
        report["templates"].append(describe_file(path))
    report["attachment1"] = describe_file(ATTACH / "附件1.xlsx")

    dest = OUT / "attachment_structure.json"
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {dest}")

    for item in report["templates"]:
        print("=" * 76)
        print(f"FILE {item['file']}")
        for sheet in item["sheets"]:
            print(f"  SHEET {sheet['name']!r}  rows={sheet['max_row']} cols={sheet['max_col']}")
            for row in sheet["head"]:
                print(f"    head: {row}")
            for row in sheet["tail"]:
                print(f"    tail: {row}")

    a1 = report["attachment1"]
    print("=" * 76)
    print(f"FILE {a1['file']}")
    for sheet in a1["sheets"]:
        print(f"  SHEET {sheet['name']!r}  rows={sheet['max_row']} cols={sheet['max_col']}")
        for row in sheet["head"]:
            print(f"    head: {row}")
        for row in sheet["tail"]:
            print(f"    tail: {row}")


if __name__ == "__main__":
    main()
