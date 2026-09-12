"""环境体检：逐项核对 skill 与后续阶段所需的一切。

覆盖：
  1. Python 解释器与 requirements.txt 逐包检查
  2. 建模/绘图/优化常用的额外包
  3. matplotlib 后端能力（skill 要求 TkAgg，禁止 Agg）
  4. 数据读写与文档解析能力（openpyxl / python-docx / PDF 提取）
  5. 中文绘图字体（论文出图必需）
  6. 输出到 JSON，便于汇总

用法：
    .venv\\Scripts\\python.exe tools\\env_audit.py
"""

from __future__ import annotations

import importlib
import importlib.metadata as md
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "processed" / "env_audit.json"

# requirements.txt 声明的包
REQUIRED = [
    "pandas", "numpy", "scipy", "scikit-learn", "statsmodels", "matplotlib",
    "seaborn", "jupyter", "openpyxl", "xlrd", "sympy", "networkx", "tqdm",
    "joblib", "pyyaml", "python-dotenv", "plotly", "black", "ruff",
]

# 后续阶段（求解 / 出图 / 论文）很可能用到的
EXTRA = [
    "highspy",              # 建模手已在用
    "pulp", "cvxpy",        # 备用 LP/MILP 建模层
    "python-docx",          # DOCX 论文输出
    "pypdf", "pdfplumber", "PyMuPDF",   # PDF 读取/文本层
    "Pillow",               # 图像
    "lxml",                 # openpyxl / pandas 加速
    "numba",                # 加速（可选）
    "python-dateutil", "pytz", "tzdata",
    "tabulate",             # markdown 表格
    "markdown",             # md 处理
    "jinja2",               # 模板渲染
    "chardet", "charset-normalizer",   # 中文编码嗅探（附件可能 GBK）
    "matplotlib-venn",      # 可选
    "openpyxl",             # 重复但无害
]

IMPORT_NAME = {
    "scikit-learn": "sklearn",
    "python-docx": "docx",
    "PyMuPDF": "fitz",
    "python-dotenv": "dotenv",
    "PyYAML": "yaml",
    "Pillow": "PIL",
    "python-dateutil": "dateutil",
    "markdown": "markdown",
    "matplotlib-venn": "matplotlib_venn",
}

results: dict = {"python": {}, "packages": {}, "matplotlib": {}, "fonts": {}, "external": {}}


def check_pkg(name: str) -> dict:
    mod = IMPORT_NAME.get(name, name.replace("-", "_"))
    info: dict = {"import_name": mod}
    try:
        m = importlib.import_module(mod)
        info["importable"] = True
        info["module_version"] = getattr(m, "__version__", None)
    except Exception as exc:  # noqa: BLE001
        info["importable"] = False
        info["import_error"] = f"{type(exc).__name__}: {exc}"
    try:
        info["dist_version"] = md.version(name)
    except Exception:  # noqa: BLE001
        info["dist_version"] = None
    info["ok"] = bool(info["importable"])
    return info


def main() -> None:
    results["python"] = {
        "executable": sys.executable,
        "version": sys.version.split()[0],
        "prefix": sys.prefix,
    }

    for name in dict.fromkeys(REQUIRED):
        results["packages"][name] = {**check_pkg(name), "group": "requirements"}
    for name in dict.fromkeys(EXTRA):
        results["packages"].setdefault(name, {**check_pkg(name), "group": "extra"})

    # ---------- matplotlib 后端 ----------
    try:
        import matplotlib
        mpl: dict = {"version": matplotlib.__version__}
        mpl["default_backend"] = matplotlib.get_backend()
        # 检查 TkAgg 是否可用（不真正切换，避免弹窗）
        try:
            import tkinter  # noqa: F401
            mpl["tkinter_importable"] = True
            try:
                tcl = tkinter.Tcl()
                mpl["tcl_version"] = tcl.eval("info patchlevel")
            except Exception as exc:  # noqa: BLE001
                mpl["tcl_version"] = f"error: {type(exc).__name__}"
        except Exception as exc:  # noqa: BLE001
            mpl["tkinter_importable"] = False
            mpl["tkinter_error"] = f"{type(exc).__name__}: {exc}"
        results["matplotlib"] = mpl
    except Exception as exc:  # noqa: BLE001
        results["matplotlib"] = {"error": f"{type(exc).__name__}: {exc}"}

    # ---------- 中文字体 ----------
    fonts: dict = {}
    try:
        from matplotlib import font_manager
        available = {f.name for f in font_manager.fontManager.ttflist}
        for cand in ["Microsoft YaHei", "SimHei", "SimSun", "KaiTi", "FangSong",
                     "Noto Sans CJK SC", "Source Han Sans SC", "DengXian"]:
            fonts[cand] = cand in available
        fonts["_total_fonts"] = len(available)
    except Exception as exc:  # noqa: BLE001
        fonts["_error"] = f"{type(exc).__name__}: {exc}"
    results["fonts"] = fonts

    # ---------- 外部工具 ----------
    tools = ["matlab", "octave", "octave-cli", "Rscript", "R", "pandoc", "git",
             "node", "pnpm", "npm", "pdflatex", "xelatex", "tectonic",
             "libreoffice", "soffice", "magick", "gswin64c", "pdftotext",
             "pdftoppm", "pdfinfo", "typst", "quarto"]
    for t in tools:
        p = shutil.which(t)
        results["external"][t] = {"found": bool(p), "path": p}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------- 控制台摘要 ----------
    print("=" * 78)
    print(f"Python: {results['python']['version']}  @ {results['python']['executable']}")
    print("=" * 78)
    miss_req = [k for k, v in results["packages"].items()
                if v.get("group") == "requirements" and not v.get("ok")]
    miss_extra = [k for k, v in results["packages"].items()
                  if v.get("group") == "extra" and not v.get("ok")]
    print(f"requirements.txt 缺失 : {miss_req if miss_req else '无 ✓'}")
    print(f"额外建议包缺失       : {miss_extra if miss_extra else '无 ✓'}")
    print()
    print("matplotlib:", json.dumps(results["matplotlib"], ensure_ascii=False))
    print()
    cn = {k: v for k, v in results["fonts"].items() if not k.startswith("_")}
    print(f"中文字体: {[k for k, v in cn.items() if v] or '无可用中文字体 ⚠'}"
          f"   (字体总数 {results['fonts'].get('_total_fonts')})")
    print()
    found = [k for k, v in results["external"].items() if v["found"]]
    print(f"外部工具可用: {found}")
    print(f"外部工具缺失: {[k for k, v in results['external'].items() if not v['found']]}")
    print()
    print(f"明细写入 {OUT}")


if __name__ == "__main__":
    main()
