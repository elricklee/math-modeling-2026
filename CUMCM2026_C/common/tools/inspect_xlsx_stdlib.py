"""仅用标准库检查 C题 附件的结构与关键内容，输出结构化摘要。

不依赖 openpyxl / pandas，可在依赖安装完成前先行使用。
用法：
    python tools/inspect_xlsx_stdlib.py            # 全部附件概览
    python tools/inspect_xlsx_stdlib.py 附件2      # 只查名字匹配的文件
"""

from __future__ import annotations

import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
ATTACH = ROOT / "CUMCM2026Problems" / "C题" / "附件"
OUT = ROOT / "data" / "processed"
NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships"}


def shared_strings(zf: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    out: list[str] = []
    for si in root.findall("m:si", NS):
        out.append("".join(t.text or "" for t in si.iter(
            "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t")))
    return out


def sheet_names(zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    """返回 [(sheet 名, zip 内路径)]，按 workbook 顺序。"""
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    rid_map = {rel.get("Id"): rel.get("Target") for rel in rels}
    out: list[tuple[str, str]] = []
    for sheet in wb.find("m:sheets", NS):
        rid = sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        target = rid_map.get(rid, "")
        if not target.startswith("xl/"):
            target = "xl/" + target.lstrip("/")
        out.append((sheet.get("name"), target))
    return out


def col_to_index(ref: str) -> int:
    letters = re.match(r"([A-Z]+)", ref)
    if not letters:
        return 0
    value = 0
    for ch in letters.group(1):
        value = value * 26 + (ord(ch) - 64)
    return value - 1


def read_rows(zf: zipfile.ZipFile, path: str, sst: list[str],
              max_rows: int | None = None) -> tuple[list[list[object]], int, int]:
    """流式解析工作表，返回 (行列表, max_row, max_col)。"""
    rows: list[list[object]] = []
    max_col_seen = 0
    max_row_seen = 0
    with zf.open(path) as fh:
        for event, elem in ET.iterparse(fh, events=("end",)):
            if elem.tag != "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row":
                continue
            row_index = int(elem.get("r", len(rows) + 1))
            max_row_seen = max(max_row_seen, row_index)
            cells: dict[int, object] = {}
            for cell in elem:
                ref = cell.get("r", "")
                idx = col_to_index(ref)
                ctype = cell.get("t")
                value_elem = cell.find("m:v", NS)
                inline = cell.find("m:is", NS)
                raw: object = None
                if ctype == "s" and value_elem is not None and value_elem.text is not None:
                    raw = sst[int(value_elem.text)]
                elif ctype == "inlineStr" and inline is not None:
                    raw = "".join(t.text or "" for t in inline.iter(
                        "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"))
                elif value_elem is not None:
                    text = value_elem.text
                    if text is None:
                        raw = None
                    else:
                        try:
                            raw = float(text)
                            if raw == int(raw):
                                raw = int(raw)
                        except ValueError:
                            raw = text
                if raw is not None:
                    cells[idx] = raw
                    max_col_seen = max(max_col_seen, idx + 1)
            if cells:
                width = max(cells) + 1
                rows.append([cells.get(i) for i in range(width)])
            else:
                rows.append([])
            elem.clear()
            if max_rows is not None and len(rows) >= max_rows:
                break
    return rows, max_row_seen, max_col_seen


def describe(path: Path, preview: int = 5) -> dict:
    with zipfile.ZipFile(path) as zf:
        sst = shared_strings(zf)
        info: dict = {"file": path.name, "size_kb": round(path.stat().st_size / 1024, 1),
                      "sheets": []}
        for name, target in sheet_names(zf):
            rows, max_row, max_col = read_rows(zf, target, sst, max_rows=None)
            sheet: dict = {"name": name, "max_row": max_row, "max_col": max_col}
            sheet["head"] = rows[:preview]
            sheet["tail"] = rows[-2:] if len(rows) > preview else []
            info["sheets"].append(sheet)
    return info


def main(argv: list[str]) -> None:
    targets = sorted(ATTACH.glob("*.xlsx")) + sorted((ATTACH / "附件5").glob("*.xlsx"))
    if argv:
        targets = [p for p in targets if any(a in p.name for a in argv)]
    OUT.mkdir(parents=True, exist_ok=True)
    report = []
    for path in targets:
        info = describe(path)
        report.append(info)
        print("=" * 78)
        print(f"FILE {info['file']}  ({info['size_kb']} KB)")
        for sheet in info["sheets"]:
            print(f"  SHEET {sheet['name']!r}  max_row={sheet['max_row']}  max_col={sheet['max_col']}")
            for row in sheet["head"]:
                print(f"    head: {row}")
            for row in sheet["tail"]:
                print(f"    tail: {row}")
    dest = OUT / "attachment_overview.json"
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结构化结果写入 {dest}")


if __name__ == "__main__":
    main(sys.argv[1:])
