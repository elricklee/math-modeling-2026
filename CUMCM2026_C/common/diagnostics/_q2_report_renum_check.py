"""报告「权威数值表」再对表：JSON 在 05:48:37 被重新生成后，报告 §一/§二 引用的数字是否仍成立。

做法（与 t13 的 688 token 对表同源，但只针对本报告 §一/§二）：
  1. 抽出报告指定行区间内的所有数值 token；
  2. 递归收集 Q2_diagnostics.json 与 Q2_analysis.json 内全部数值（含按 100 缩放的百分数）；
  3. 对每个 token，按其写出的小数位数在 JSON 数值集合里找四舍五入后相符的项。
未命中的 token 原样列出，供人工确认是否属于设计常数／日期。
只读，不写任何文件。
"""

import json
import pathlib
import re

REPORT = pathlib.Path("CUMCM2026_C/Q2/Q2_最终验收报告.md")
DIAG = pathlib.Path("CUMCM2026_C/Q2/outputs/Q2_diagnostics.json")
ANAL = pathlib.Path("CUMCM2026_C/Q2/outputs/Q2_analysis.json")
LO, HI = 11, 126  # §一 至 §二

TOKEN = re.compile(r"\d[\d ]*\.\d+|\d[\d ]*\d|\d")


def collect_numbers(obj, out):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.append(float(obj))
        out.append(float(obj) * 100.0)
    elif isinstance(obj, str):
        # 口径说明、结论叙述里也带数字，必须一并纳入，否则会误报「对不上表」
        for tok in TOKEN.findall(obj):
            raw = norm(tok)
            try:
                val = float(raw.replace("\u2212", "-"))
            except ValueError:
                continue
            out.append(val)
            out.append(val * 100.0)
    elif isinstance(obj, dict):
        for v in obj.values():
            collect_numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            collect_numbers(v, out)


def norm(tok):
    return tok.replace(" ", "")


def main():
    lines = REPORT.read_text(encoding="utf-8").splitlines()
    segment = lines[LO - 1:HI]

    pool = []
    sizes = []
    for path in (DIAG, ANAL):
        before = len(pool)
        collect_numbers(json.loads(path.read_text(encoding="utf-8")), pool)
        sizes.append((path.name, len(pool) - before,
                      __import__("datetime").datetime.fromtimestamp(path.stat().st_mtime)
                      .strftime("%Y-%m-%d %H:%M:%S")))

    hits, miss = [], []
    seen = set()
    neg = "\u2212\uff0d-"
    for lineno, line in enumerate(segment, start=LO):
        for tok in TOKEN.findall(line):
            raw = norm(tok)
            if raw in seen:
                continue
            seen.add(raw)
            try:
                val = float(raw)
            except ValueError:
                continue
            decimals = len(raw.split(".")[1]) if "." in raw else 0
            cands = [val]
            # 报告里的负号可能是 U+2212，JSON 里可能是普通负号（或反之）
            idx = line.find(tok)
            if idx > 0 and line[idx - 1] in neg:
                cands.append(-val)
            ok = any(round(f, decimals) == c for f in pool for c in cands)
            if ok:
                hits.append((lineno, raw))
            else:
                miss.append((lineno, raw))

    print("区间 L%d-%d，去重数值 token：命中 %d，未命中 %d" % (LO, HI, len(hits), len(miss)))
    print("未命中清单（需人工确认为设计常数／日期）：")
    for lineno, raw in miss:
        print("   L%-4d %s" % (lineno, raw))
    print()
    print("JSON 侧统计：")
    for name, cnt, mt in sizes:
        print("   %s = %d 个浮点（含 ×100），mtime %s" % (name, cnt, mt))


main()
