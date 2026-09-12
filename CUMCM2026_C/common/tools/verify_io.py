"""全面功能验证：PDF / XLSX 的读与写是否流畅，以及中文路径处理。

只写测试产物到 CUMCM2026_C/Q1/outputs/_envtest/，不碰任何原始附件。

用法：
    .venv\\Scripts\\python.exe tools\\verify_io.py
"""

from __future__ import annotations

import json
import shutil
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "CUMCM2026Problems" / "C题" / "附件"
WORK = ROOT / "data" / "processed" / "_envtest"

results: dict = {"pdf": {}, "xlsx": {}, "writer": {}, "errors": []}


def record(section: str, key: str, ok: bool, detail: object = None) -> None:
    results[section][key] = {"ok": ok, "detail": detail}
    mark = "✓" if ok else "✗"
    print(f"  {mark} {key}" + (f"  — {detail}" if detail is not None else ""))


def main() -> None:
    if WORK.exists():
        shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir(parents=True, exist_ok=True)
    print("=" * 78)
    print("STAGE 1  PDF 读取")
    # --- pymupdf ---
    try:
        import pymupdf
        doc = pymupdf.open(RAW.parent / "C题.pdf")
        text = "".join(p.get_text() for p in doc)
        record("pdf", "pymupdf 读文本", len(text) > 2000,
               f"{doc.page_count} 页 / {len(text)} 字符")
        # 渲染成图（论文/核对用）
        pix = doc[0].get_pixmap(dpi=110)
        out_png = WORK / "page1.png"
        pix.save(out_png)
        record("pdf", "pymupdf 渲染 PNG", out_png.exists() and out_png.stat().st_size > 5000,
               f"{out_png.stat().st_size} bytes")
        doc.close()
    except Exception as exc:  # noqa: BLE001
        results["errors"].append(f"pymupdf: {traceback.format_exc(limit=2)}")
        record("pdf", "pymupdf", False, f"{type(exc).__name__}: {exc}")

    # --- pypdf ---
    try:
        from pypdf import PdfReader
        r = PdfReader(str(RAW.parent / "C题.pdf"))
        t = "".join((p.extract_text() or "") for p in r.pages)
        record("pdf", "pypdf 读文本", len(t) > 2000, f"{len(r.pages)} 页 / {len(t)} 字符")
    except Exception as exc:  # noqa: BLE001
        record("pdf", "pypdf", False, f"{type(exc).__name__}: {exc}")

    # --- pdfplumber（表格提取）---
    try:
        import pdfplumber
        with pdfplumber.open(RAW.parent / "C题.pdf") as pdf:
            tables = pdf.pages[0].extract_tables() or []
        record("pdf", "pdfplumber 抽表", True, f"第1页抽到 {len(tables)} 个表")
    except Exception as exc:  # noqa: BLE001
        record("pdf", "pdfplumber", False, f"{type(exc).__name__}: {exc}")

    print("=" * 78)
    print("STAGE 2  XLSX 读取（含中文路径与宽表）")
    try:
        import pandas as pd
        # 附件1：窄表
        df1 = pd.read_excel(RAW / "附件1.xlsx", sheet_name=0)
        record("xlsx", "pandas 读附件1", df1.shape == (144, 4), f"shape={df1.shape}")
        # 附件2：宽表（365×145）
        xl = pd.ExcelFile(RAW / "附件2.xlsx")
        record("xlsx", "列出附件2 sheet", len(xl.sheet_names) == 2, str(xl.sheet_names))
        df2 = pd.read_excel(RAW / "附件2.xlsx", sheet_name="小区负载", header=0)
        record("xlsx", "pandas 读宽表(365×145)", df2.shape[0] == 365 and df2.shape[1] == 145,
               f"shape={df2.shape}")
    except Exception as exc:  # noqa: BLE001
        record("xlsx", "pandas 读", False, f"{type(exc).__name__}: {exc}")

    try:
        import openpyxl
        wb = openpyxl.load_workbook(RAW / "附件3.xlsx", read_only=True, data_only=True)
        ws = wb.active
        record("xlsx", "openpyxl 读附件3", ws.max_row == 1461 and ws.max_column == 26,
               f"max_row={ws.max_row} max_col={ws.max_column}")
        wb.close()
    except Exception as exc:  # noqa: BLE001
        record("xlsx", "openpyxl 读", False, f"{type(exc).__name__}: {exc}")

    print("=" * 78)
    print("STAGE 3  XLSX 写入（含中文 sheet 名与多 sheet）")
    out_xlsx = WORK / "写入测试_中文名.xlsx"
    try:
        import openpyxl
        from openpyxl.styles import Font
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "计划购电量"
        ws.append(["时间段", "购电量"])
        for i in range(1, 11):
            ws.append([f"{i}:00-{i}:10", i * 123.456])
        ws["A1"].font = Font(bold=True)
        ws2 = wb.create_sheet("充放电量")
        ws2.append(["时间段", "充电量", "放电量", "时刻", "储电量"])
        ws2.append(["0:00-4:00", 1.5, 2.5, "0:00", 6000])
        wb.save(out_xlsx)
        record("writer", "openpyxl 写多 sheet 中文 xlsx", out_xlsx.exists(),
               f"{out_xlsx.stat().st_size} bytes")
        # 回读校验
        wb2 = openpyxl.load_workbook(out_xlsx)
        ok = wb2.sheetnames == ["计划购电量", "充放电量"] and wb2["计划购电量"]["A1"].value == "时间段"
        record("writer", "回读校验(中文 sheet 名+内容)", ok, str(wb2.sheetnames))
        wb2.close()
    except Exception as exc:  # noqa: BLE001
        results["errors"].append(f"xlsx write: {traceback.format_exc(limit=2)}")
        record("writer", "openpyxl 写", False, f"{type(exc).__name__}: {exc}")

    # --- pandas 写 ---
    try:
        import pandas as pd
        out_csv = WORK / "写入测试.csv"
        pd.DataFrame({"a": [1, 2], "b": ["中文", "测试"]}).to_csv(out_csv, index=False, encoding="utf-8-sig")
        back = pd.read_csv(out_csv, encoding="utf-8-sig")
        record("writer", "pandas 写读 CSV(中文)", list(back["b"]) == ["中文", "测试"])
    except Exception as exc:  # noqa: BLE001
        record("writer", "pandas CSV", False, f"{type(exc).__name__}: {exc}")

    # --- docx 写 ---
    try:
        from docx import Document
        d = Document()
        d.add_heading("测试标题", level=1)
        d.add_paragraph("中文段落测试。")
        out_docx = WORK / "写入测试.docx"
        d.save(out_docx)
        record("writer", "python-docx 写 DOCX", out_docx.exists(), f"{out_docx.stat().st_size} bytes")
    except Exception as exc:  # noqa: BLE001
        record("writer", "python-docx", False, f"{type(exc).__name__}: {exc}")

    print("=" * 78)
    print("STAGE 4  matplotlib 绘图（含中文字体）")
    try:
        import matplotlib
        record("writer", "matplotlib 后端", True, matplotlib.get_backend())
        import matplotlib.pyplot as plt
        plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
        plt.rcParams["axes.unicode_minus"] = False
        fig, ax = plt.subplots(figsize=(5, 3))
        ax.plot([0, 1, 2], [1, 2, 3], label="电价曲线")
        ax.set_title("中文标题测试：电价与负载")
        ax.set_xlabel("时间")
        ax.legend()
        out_png = WORK / "fig_test.png"
        fig.savefig(out_png, dpi=100, bbox_inches="tight")
        plt.close(fig)
        record("writer", "matplotlib 出图(中文)", out_png.exists() and out_png.stat().st_size > 5000,
               f"{out_png.stat().st_size} bytes")
    except Exception as exc:  # noqa: BLE001
        results["errors"].append(f"matplotlib: {traceback.format_exc(limit=2)}")
        record("writer", "matplotlib", False, f"{type(exc).__name__}: {exc}")

    # --- 汇总 ---
    dest = WORK / "verify_io.json"
    dest.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print("=" * 78)
    total = sum(len(v) for k, v in results.items() if k != "errors")
    failed = sum(1 for k, v in results.items() if k != "errors"
                 for item in v.values() if not item["ok"])
    print(f"共 {total} 项检查，失败 {failed} 项")
    if results["errors"]:
        print("异常栈（前 2 条）:")
        for e in results["errors"][:2]:
            print("   ", e.splitlines()[-1][:120])
    print(f"产物目录: {WORK}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
