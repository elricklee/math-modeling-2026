r"""问题二 · 字段路径解析检查（field-path resolution check）· v2

背景与 v1 的教训
================

建模手提出并两次验证的一类错误：**数字都在文件里，但引用的字段路径名不对**，
读者按路径解析会得到空值或读错条。v1（首版）把这条检查固化下来，但它**自己犯了
一个"宽容态"错误**——它把 ``variants[*].summary``（``variants`` 是 **dict**，
``[*]`` 是数组通配符）当作可解析，于是对验收报告给出 "UNRESOLVED 0" 的**假绿**；
同时也漏掉了 ``experiment_1`` / ``experiment_2``（那两个键在另一个产物里，
v1 只覆盖 2 个 JSON）。

v2 的修正
---------

1. **通配符语义从紧**：``[*]`` 与 ``[i]`` 只对 **list** 合法；用在 dict 上一律记为
   **TOLERATED**（= 靠宽容规则才解析，**不等于逐字可解析**），必须显式登记在
   ``ALLOWED_TOLERANCES`` 里才算通过。本文件 ``ALLOWED_TOLERANCES = []``
   （即：**当前一条都不豁免**）。
2. **覆盖面从 2 个产物扩到 7 个**：除 ``Q2_analysis.json`` / ``Q2_diagnostics.json``
   外，纳入 ``_q2_u4_multiple_optima.json``（其真实键名为
   ``experiment_1_execution_convention`` / ``experiment_2_multiple_optima_scan``，
   验收报告的 ``experiment_1`` / ``experiment_2`` **正错在这里**）、
   ``_q2_audit.json``、``_q2_audit_thirdparty.json``、``_q2_audit_thirdparty_probe.json``、
   ``_q2_paper_audit.json``。
3. **文档扫描给出逐类计数与逐条明细**（含行号），不再只给一个"失败列表为空"——
   那会被误读成"逐字可解析"。
4. **判定从紧**：``verdict = pass`` 当且仅当 **UNRESOLVED = 0 且非豁免的
   PARTIAL/TOLERATED = 0**；否则退出码 1。

状态定义
--------

* ``OK``          —— 严格解析成功。
* ``PARTIAL``     —— 前缀成功、**末段在更深层存在**（= 路径被缩写）。
* ``TOLERATED``   —— 靠宽容规则才解析（如 dict 上写 ``[*]``）。**≠ 逐字可解析。**
* ``UNRESOLVED``  —— 严格与模糊都找不到（**真错**）。

运行（仓库根目录）::

    $env:PYTHONIOENCODING="utf-8"
    .venv\Scripts\python.exe CUMCM2026_C\Q2\Q2_field_path_check.py

产物：``CUMCM2026_C/Q2/_q2_field_path_check.json``（诊断件，**不进 outputs/**）。
只读，不修改任何交付物；本脚本不绘图，故不涉及 matplotlib 后端。

取数纪律（2026-09-12 与建模手约定）
-----------------------------------

**一次读盘、三值同出**：行数、字节数、sha256_16 必须来自**同一次** ``read_bytes()``
（见 ``fingerprint()``），既不"两个字段取自两次读"，也不"写完先算、算完又写"。
对外报数时**直接粘贴脚本输出**，不要手抄——本轮曾把报告的 56 536 B 手抄成 56 535 B
（sha 与对方一致，说明是转写少 1，不是读盘差异）。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from datetime import datetime

ROOT = r"D:\MathModeling\math-modeling-2026"
TOOL_VERSION = "3.0"     # v2.9 后按建模手建议：增长型记录不参与 run_fingerprint（只扫描、只记录，不改指纹）
RULE_VERSION = 1         # 扫描规则版本：CITATIONS/NEGATIVE/CONTENT_ASSERTIONS/INDEX_RULES/ALLOWED_TOLERANCES 有改动时 +1
# 不参与 `run_fingerprint` 的输入（仍是扫描对象、仍在 `inputs` 里留痕）。
# 理由（建模手 2026-09-12）：**指纹是用来锚定"可被引用的东西"的**；一个本性就要增长的文件
#（本审计记录）不该参与锚定——否则"正常追加记录"就会让指纹跳动，并连带把同一条消息里的其它值拖旧。
FINGERPRINT_EXCLUDED = {"_q2_paper_audit.md"}
C = os.path.join(ROOT, "CUMCM2026_C")
OUT = os.path.join(C, "Q2", "outputs")
DIAG = os.path.join(C, "common", "diagnostics")

ARTIFACTS = {
    "Q2_analysis.json": os.path.join(OUT, "Q2_analysis.json"),
    "Q2_diagnostics.json": os.path.join(OUT, "Q2_diagnostics.json"),
    "_q2_u4_multiple_optima.json": os.path.join(DIAG, "_q2_u4_multiple_optima.json"),
    "_q2_audit.json": os.path.join(DIAG, "_q2_audit.json"),
    "_q2_audit_thirdparty.json": os.path.join(DIAG, "_q2_audit_thirdparty.json"),
    "_q2_audit_thirdparty_probe.json": os.path.join(DIAG, "_q2_audit_thirdparty_probe.json"),
    "_q2_paper_audit.json": os.path.join(DIAG, "_q2_paper_audit.json"),
}

# 显式豁免清单：只有列在这里的 (artifact, path) 才允许以 PARTIAL/TOLERATED 通过。
# 当前为空 —— 任何缩写或宽容写法都算未通过，必须改路径或在此登记理由。
ALLOWED_TOLERANCES: list = []

TOKEN_OK = re.compile(r"^[A-Za-z_][\w]*(?:\[[^\]]*\])?(?:\.[\w\[\]\*]+){0,6}$")
NUM = re.compile(r"\d[\d,]*(?:\.\d+)?")
FILE_IN_SPAN = re.compile(r"([\w\-.]+\.json)")
FILEY = re.compile(r"\.(json|csv|xlsx|png|md|py|txt)$", re.I)
# 行内豁免标记：审计/复核记录里**引用已知错误路径**（例如"报告 L307 写了 experiment_1，
# 应为 experiment_1_execution_convention"）不应被算作引用缺陷。带该标记的行整行跳过，
# 并在计数里单列，保持"豁免显式可见"。
EXEMPT_TAG = "【路径豁免】"

CITATIONS = [
    ("Q2_analysis.json", "conclusions", "结论列表（0-based）"),
    ("Q2_analysis.json", "conclusions[4]", "0-based 第 5 条 = 成对单因子分解（锚点 ②）"),
    ("Q2_analysis.json", "conclusions[8]", "0-based 第 9 条 = 5 倍电价作用"),
    ("Q2_analysis.json", "variants.③ 仅光伏不可知（负载已知）.summary", "具名口径汇总（正确写法）"),
    ("Q2_analysis.json", "mae_layers.full_day", "两层 MAE：全天口径"),
    ("Q2_analysis.json", "mae_layers.actual_positive", "两层 MAE：实际光伏 > 0"),
    ("Q2_analysis.json", "mae_layers.zero_actual_interval_share", "零光伏时段占比"),
    ("Q2_analysis.json", "forecast_errors.mae_definition", "MAE 口径定义"),
    ("Q2_analysis.json", "forecast_errors.cross_release_comparable_subset", "共同覆盖窗"),
    ("Q2_analysis.json", "forecast_errors.by_release_hour", "各发布时刻（不可横向排序）"),
    ("Q2_analysis.json", "main_vs_control.control_convention_label", "主线对照标签"),
    ("Q2_analysis.json", "main_vs_control.cost_gap_reference_variant", "代价参照变体"),
    ("Q2_analysis.json", "main_vs_control.cost_gap_reference_note", "代价参照说明"),
    ("Q2_analysis.json", "dispatch_bounds.committed_label", "承诺调度口径"),
    ("Q2_analysis.json", "pcap_sensitivity.note", "p^cap 灵敏度与早期记录差异说明"),
    ("Q2_analysis.json", "pcap_sensitivity.scenarios", "α 各档结果"),
    ("Q2_analysis.json", "spreading_rule_comparison.all_year", "错位一格对照规则"),
    ("Q2_analysis.json", "convention_correction.before", "口径订正前"),
    ("Q2_analysis.json", "convention_correction.after", "口径订正后"),
    ("Q2_analysis.json", "convention_correction.additional_corrections", "附带订正"),
    ("Q2_analysis.json", "loop_check", "回环校验"),
    ("Q2_analysis.json", "baseline_no_storage", "不装储能基线"),
    ("Q2_analysis.json", "control_convention_independent_check", "对照口径独立核查"),
    ("Q2_analysis.json", "limitations", "局限"),
    ("Q2_diagnostics.json", "solver.elapsed_seconds", "批量求解耗时（A-6）"),
    ("Q2_diagnostics.json", "solver.nit", "单纯形迭代次数"),
    ("Q2_diagnostics.json", "independent_recompute.elapsed_seconds", "逐日复算耗时（A-6）"),
    ("Q2_diagnostics.json", "emergency_purchase.worksheet_shape_rows_cols", "工作表形状"),
    ("Q2_diagnostics.json", "emergency_purchase.worksheet_header_only", "仅表头"),
    ("Q2_diagnostics.json", "emergency_purchase.worksheet_layout_note", "版式留痕"),
    ("Q2_diagnostics.json", "emergency_purchase.counterfactual_check", "反事实检查"),
    ("Q2_diagnostics.json", "baseline_B0_purchase_kwh", "B0 基线购电"),
    ("Q2_diagnostics.json", "baseline_B0_mean_price_yuan_per_kwh", "B0 均价"),
    ("Q2_diagnostics.json", "purchase_reduction_vs_B0_kwh", "相对 B0 的购电减少"),
    ("_q2_u4_multiple_optima.json", "experiment_1_execution_convention", "U4 实验一（真实键名）"),
    ("_q2_u4_multiple_optima.json", "experiment_2_multiple_optima_scan", "U4 实验二（真实键名）"),
    ("_q2_audit_thirdparty.json", "n_checks", "第三方复核检查项数"),
    ("_q2_paper_audit.json", "post_closure_notes", "收口补记"),
]

NEGATIVE = [
    ("Q2_diagnostics.json", "emergency_purchase.worksheet_has_explanation_row_only", "旧字段名应已删除"),
]
# 内容断言：**路径能解析 ≠ 引对了条目**。索引写错但仍在范围内时，路径解析会是绿的，
# 只有比对条目内容才能发现（建模手被 `conclusions[7]` 绊倒正是这一类）。
CONTENT_ASSERTIONS = [
    ("Q2_analysis.json", "conclusions[4]", "成对单因子分解", "0-based 第 5 条应为成对分解"),
    ("Q2_analysis.json", "conclusions[7]", "预报误差", "0-based 第 8 条应为『决定因素是预报误差』"),
    ("Q2_analysis.json", "conclusions[8]", "4.46", "0-based 第 9 条应为 5 倍电价作用（含 4.46）"),
    ("Q2_analysis.json", "mae_layers.actual_positive.mae_kw", "657.5", "两层 MAE 的正样本口径值"),
    ("Q2_diagnostics.json", "emergency_purchase.worksheet_shape_rows_cols", "1", "工作表形状应为 [1,3]"),
]
RAW_NEGATIVE = [
    ("Q2_analysis.json", "387.36", 0, "作废的 MAE 变体应 0 命中"),
    ("Q2_analysis.json", "covered_only", 0, "作废字段应 0 命中"),
    ("Q2_analysis.json", "448.3124", 6, "错位一格对照值应 6 处"),
]

SCANNED = [
    ("求解章", os.path.join(C, "Q2", "问题二模型的求解.md")),
    ("建立章", os.path.join(C, "Q2", "问题二模型的建立.md")),
    ("验收报告", os.path.join(C, "Q2", "Q2_最终验收报告.md")),
    ("本审计记录", os.path.join(DIAG, "_q2_paper_audit.md")),
]

# STAGE E：索引语义断言。**路径能解析 ≠ 引对了条目**——若某行同时出现"数值锚点"与
# `conclusions[k]`，则 k 必须是该数值真正所属的 0-based 索引，否则判 SEMANTIC_MISMATCH。
INDEX_RULES = [
    ("Q2_analysis.json", "conclusions", "4.46", 8, "4.46 元/kWh 属 0-based 第 9 条"),
    ("Q2_analysis.json", "conclusions", "0.6148", 8, "0.6148 元/kWh 属 0-based 第 9 条"),
    ("Q2_analysis.json", "conclusions", "成对单因子分解", 4, "成对分解属 0-based 第 5 条"),
    ("Q2_analysis.json", "conclusions", "预报误差", 7, "『决定因素是预报误差』属 0-based 第 8 条"),
    ("Q2_analysis.json", "conclusions", "5.4 倍", 4, "5.4 倍属成对分解条目（0-based 第 5 条）"),
]

DATA = {}


def fingerprint(path):
    """一次读盘、三值同出：(splitlines 行数, 字节数, sha256_16)。"""
    b = open(path, "rb").read()
    return len(b.decode("utf-8").splitlines()), len(b), hashlib.sha256(b).hexdigest()[:16]


def input_snapshot():
    """记录**本次扫描实际消费的输入版本**（五元组）。

    动机（建模手 2026-09-12）：诊断件是**派生件**——输入（尤其是被扫文档）一变，
    重跑就会产出不同的 JSON。故"脚本冻结"不等于"输出冻结"；输出必须自描述
    "它当时扫的是哪一版"，否则 `frozen` 会被误读成"这份诊断件不再变"。
    """
    snap = {}
    groups = (("artifact", {k: v for k, v in ARTIFACTS.items()}),
              ("scanned_doc", {os.path.basename(p): p for _, p in SCANNED}))
    for role, mapping in groups:
        for name, path in mapping.items():
            if not os.path.exists(path):
                snap[name] = {"role": role, "exists": False, "path": path}
                continue
            lines, size, dig = fingerprint(path)
            snap[name] = {"role": role, "exists": True, "path": path,
                          "splitlines": lines, "bytes": size,
                          "mtime": datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M:%S"),
                          "sha256_16": dig,
                          "fingerprint_excluded": name in FINGERPRINT_EXCLUDED,
                          "fingerprint_role": ("record（增长型；不参与 run_fingerprint）"
                                               if name in FINGERPRINT_EXCLUDED else "anchor_input")}
    return snap


def resolve(obj, path):
    """严格解析 ``a.b[i]`` / ``a.b[*]``；返回 (status, value, note)。"""
    cur = obj
    for seg in [s for s in path.split(".") if s != ""]:
        m = re.match(r"^([^\[]*)(?:\[([^\]]*)\])?$", seg)
        name, idx = m.group(1), m.group(2)
        if name == "*":
            if isinstance(cur, dict) and cur:
                cur = next(iter(cur.values()))
            elif isinstance(cur, list) and cur:
                cur = cur[0]
            else:
                return "UNRESOLVED", None, "`.*` 需要非空容器"
        elif name:
            if not isinstance(cur, dict) or name not in cur:
                found = _deep_find(cur, name)
                if found is not None:
                    return "PARTIAL", found[0], "末段在 %s 下（缩写引用）" % found[1]
                return "UNRESOLVED", None, "缺少键 %r" % name
            cur = cur[name]
        if idx is not None:
            if idx == "*":
                if isinstance(cur, list) and cur:
                    cur = cur[0]
                elif isinstance(cur, dict) and cur:
                    return "TOLERATED", next(iter(cur.values())), \
                        "`[*]` 用在 dict 上（应写 `.*` 或具体键名），非逐字可解析"
                else:
                    return "UNRESOLVED", None, "`[*]` 需要非空容器"
            else:
                if not isinstance(cur, list):
                    return "UNRESOLVED", None, "`[%s]` 需要 list，实际 %s" % (idx, type(cur).__name__)
                i = int(idx)
                if i >= len(cur):
                    return "UNRESOLVED", None, "索引 %s 越界" % idx
                cur = cur[i]
    return "OK", cur, ""


def _deep_find(obj, key, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = "%s.%s" % (prefix, k) if prefix else k
            if k == key:
                return v, here
            got = _deep_find(v, key, here)
            if got:
                return got
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            got = _deep_find(v, key, "%s[%d]" % (prefix, i))
            if got:
                return got
    return None


def extract_citations(line):
    """文档一行 -> [(artifact, path, raw)]。

    只认**文件锚定**写法：代码段里出现 ``<某个已登记产物>.json`` 后跟 ``→`` 再接
    路径/键名。**不做裸 token 猜测**——v2 试过"任何像路径的代码段都拿去解析"，
    结果把 `scipy.optimize.linprog`、`statistics.quantiles`、`load_e[i]` 这类
    Python 标识符全报成 UNRESOLVED（假阳），故该分支已移除。
    """
    out = []
    last_art = None
    for span in re.findall(r"`([^`]{3,200})`", line):
        fm = FILE_IN_SPAN.search(span)
        if fm and fm.group(1) in ARTIFACTS:
            art = fm.group(1)
            rest = re.sub(r"^\s*(?:→|->|:|：)\s*", "", span[fm.end():]).strip()
            for cand in [rest] + [p.strip() for p in re.split(r"[，,、；;]", rest)]:
                cand = cand.rstrip("：:，,。；;、")
                if not cand or " " in cand or FILEY.search(cand):
                    continue
                if TOKEN_OK.match(cand):
                    out.append((art, cand, span))
                    last_art = art
                    break
        elif last_art and " " not in span and not FILEY.search(span) \
                and TOKEN_OK.match(span) and ("." in span or "[" in span):
            # 同一行内紧随其后的裸路径代码段（如 `… → conclusions[4]` 与 `variants[*].summary` 并列）
            out.append((last_art, span, span + "（同行前文锚定 %s）" % last_art))
    return out


def sample(v):
    if isinstance(v, str):
        return v[:90].replace("\n", " ")
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, list):
        return "list(len=%d)" % len(v)
    if isinstance(v, dict):
        return "dict(keys=%s)" % ",".join(list(v)[:4])
    return type(v).__name__


def main() -> int:
    # 控制台编码兜底：即使调用者忘了设 PYTHONIOENCODING，也不因中文/符号崩在 GBK 下。
    # （建模手 2026-09-12 报告过同型事故：一次性核验命令里的 '⇒' 在默认 GBK 控制台崩溃；
    #  更早还有 Q2_audit.py 崩在 '\u207b'。这里是脚本侧的兜底，不是替代环境变量。）
    for stream in (sys.stdout, sys.stderr):
        try:
            # errors='backslashreplace' 而非 'replace'：不可编码字符变成 \uXXXX，**信息不丢**；
            # 'replace' 会变成 '?'，若某个数字恰落在被替换字符上，输出会失真（建模手 2026-09-12 指出）。
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except Exception:
            pass
    print("=" * 100)
    print("问题二 · 字段路径解析检查 v%s（STAGE A：载入 %d 个产物）" % (TOOL_VERSION, len(ARTIFACTS)))
    print("=" * 100)
    for name, path in ARTIFACTS.items():
        b = open(path, "rb").read()
        DATA[name] = json.loads(b.decode("utf-8"))
        print("  %-32s %8d B  mtime=%s  sha256_16=%s"
              % (name, len(b),
                 datetime.fromtimestamp(os.path.getmtime(path)).strftime("%H:%M:%S"),
                 hashlib.sha256(b).hexdigest()[:16]))

    print()
    print("=" * 100)
    print("STAGE B：逐条解析定量引用（%d 条）" % len(CITATIONS))
    print("=" * 100)
    results, stat = [], {"OK": 0, "PARTIAL": 0, "TOLERATED": 0, "UNRESOLVED": 0}
    for art, path, why in CITATIONS:
        status, val, note = resolve(DATA[art], path)
        stat[status] += 1
        results.append({"artifact": art, "path": path, "why": why, "status": status,
                        "note": note, "sample": None if val is None else sample(val)})
        print("  [%-10s] %-32s %-52s %s" % (status, art, path,
                                            (sample(val) if val is not None else note)[:60]))

    print()
    print("=" * 100)
    print("STAGE C：否定断言与内容断言（路径能解析 ≠ 引对了条目）")
    print("=" * 100)
    neg, n_neg_bad = [], 0
    for art, path, why in NEGATIVE:
        status, _, _ = resolve(DATA[art], path)
        good = status == "UNRESOLVED"
        n_neg_bad += 0 if good else 1
        neg.append({"artifact": art, "path": path, "why": why, "expect": "absent",
                    "got": status, "ok": good})
        print("  [%s] %-28s %-52s %s" % ("PASS" if good else "FAIL", art, path, why))
    for art, token, expect, why in RAW_NEGATIVE:
        got = json.dumps(DATA[art], ensure_ascii=False).count(token)
        good = got == expect
        n_neg_bad += 0 if good else 1
        neg.append({"artifact": art, "token": token, "why": why,
                    "expect": expect, "got": got, "ok": good})
        print("  [%s] %-28s %-52s 期望 %d 实测 %d" % ("PASS" if good else "FAIL", art, token, expect, got))
    content = []
    for art, path, needle, why in CONTENT_ASSERTIONS:
        status, val, _ = resolve(DATA[art], path)
        s = "" if val is None else (val if isinstance(val, str) else json.dumps(val, ensure_ascii=False))
        good = status == "OK" and needle in s
        n_neg_bad += 0 if good else 1
        content.append({"artifact": art, "path": path, "needle": needle, "why": why,
                        "status": status, "ok": good})
        print("  [%s] %-28s %-52s 需含 %r" % ("PASS" if good else "FAIL", art, path, needle))

    print()
    print("=" * 100)
    print("STAGE D：文档扫描（逐类计数 + 明细；PARTIAL/TOLERATED ≠ 逐字可解析）")
    print("=" * 100)
    doc_scan = {}
    for label, path in SCANNED:
        if not os.path.exists(path):
            print("  [skip] %s（不存在）" % label)
            continue
        bucket = {"file": path, "hits": 0, "ok": 0, "partial": 0,
                  "tolerated": 0, "unresolved": 0, "exempt": 0, "items": [], "all": []}
        for ln, line in enumerate(open(path, encoding="utf-8").read().splitlines(), 1):
            if EXEMPT_TAG in line:
                bucket["exempt"] += 1
                continue
            for art, cand, raw in extract_citations(line):
                bucket["hits"] += 1
                if art == "?":
                    status, note = "UNRESOLVED", "裸路径在 7 个产物中都解析不到"
                else:
                    status, _, note = resolve(DATA[art], cand)
                bucket[status.lower()] += 1
                bucket["all"].append({"line": ln, "artifact": art, "path": cand, "status": status})
                if status != "OK":
                    bucket["items"].append({"line": ln, "artifact": art, "path": cand,
                                            "status": status, "note": note,
                                            "text": line.strip()[:150]})
                    print("  [%s] %-8s L%-5d %-32s %-42s ← %s"
                          % (status, label, ln, art, cand, line.strip()[:58]))
        doc_scan[label] = bucket
        print("  [scan] %-8s 命中 %2d ｜ OK %2d ｜ PARTIAL %d ｜ TOLERATED %d ｜ UNRESOLVED %d ｜ 豁免行 %d"
              % (label, bucket["hits"], bucket["ok"], bucket["partial"],
                 bucket["tolerated"], bucket["unresolved"], bucket["exempt"]))

    print()
    print("=" * 100)
    print("STAGE E：索引语义断言（数值锚点 vs conclusions[k]；专治'路径对、条目错'）")
    print("=" * 100)
    semantic = []
    for label, path in SCANNED:
        if not os.path.exists(path):
            continue
        for ln, line in enumerate(open(path, encoding="utf-8").read().splitlines(), 1):
            if EXEMPT_TAG in line:
                continue
            for art, cand, raw in extract_citations(line):
                m = re.match(r"^conclusions\[(\d+)\]$", cand)
                if not (m and art == "Q2_analysis.json"):
                    continue
                idx = int(m.group(1))
                for r_art, r_field, token, expect, why in INDEX_RULES:
                    if r_art == art and r_field == "conclusions" and token in line and idx != expect:
                        semantic.append({"doc": label, "line": ln, "path": cand,
                                         "token": token, "expected_index": expect, "why": why,
                                         "text": line.strip()[:150]})
                        n_neg_bad += 1
                        print("  [SEMANTIC_MISMATCH] %-8s L%-5d 引 `%s` 但该行含 %r（应 `conclusions[%d]`：%s）"
                              % (label, ln, cand, token, expect, why))
    if not semantic:
        print("  （无）")

    print()
    print("=" * 100)
    print("STAGE E2：数值重合检查（被引条目的内容里应能看到本行所引的数值；advisory）")
    print("  豁免依据：① 一行可能同时引用**多个来源**的数值（如 L309 的 219.04 引自其它产物，属正常引法）；")
    print("            ② **历史值引用应当允许**——引用口径订正前的数值（如本记录 L108 的 322,255.40）")
    print("               属留痕性质，与队长 §7.3『历史留痕豁免』同类。故 E2 只提示、不计入 verdict。")
    print("=" * 100)
    warnings = []
    for label, path in SCANNED:
        if not os.path.exists(path):
            continue
        for ln, line in enumerate(open(path, encoding="utf-8").read().splitlines(), 1):
            if EXEMPT_TAG in line:
                continue
            cits = extract_citations(line)
            if len(cits) != 1:
                continue
            art, cand, _ = cits[0]
            status, val, _ = resolve(DATA[art], cand)
            if status != "OK" or val is None:
                continue
            nums = [n for n in NUM.findall(line) if len(n) >= 4
                    and not re.fullmatch(r"(19|20)\d\d", n.replace(",", ""))]
            if not nums:
                continue
            field_nums = []
            for n in NUM.findall(json.dumps(val, ensure_ascii=False)):
                try:
                    field_nums.append(float(n.replace(",", "")))
                except ValueError:
                    pass
            hit = []
            for n in nums:
                a_str = n.replace(",", "")
                if re.fullmatch(r"(19|20)\d\d", a_str):     # 年份不算数值锚点
                    continue
                dec = len(a_str.split(".")[1]) if "." in a_str else 0
                try:
                    a = float(a_str)
                except ValueError:
                    continue
                tol = 0.5 * 10 ** (-dec) + 1e-9
                if any(abs(b - a) <= tol for b in field_nums):
                    hit.append(n)
            if not hit:
                warnings.append({"doc": label, "line": ln, "artifact": art, "path": cand,
                                 "numbers_on_line": nums[:6], "text": line.strip()[:150]})
                print("  [NO_OVERLAP] %-8s L%-5d %-34s 该行数值 %s 在被引条目内容中一个都不出现"
                      % (label, ln, cand, nums[:3]))
    if not warnings:
        print("  （无）")

    n_doc_bad = sum(b["unresolved"] + b["partial"] + b["tolerated"] for b in doc_scan.values())
    doc_sites = {(b["file"], i["line"], i["path"]) for b in doc_scan.values() for i in b["items"]}
    sem_sites = {(s["doc"], s["line"], s["path"]) for s in semantic}
    n_sites = len(doc_sites | sem_sites)
    n_not_allowlisted = stat["UNRESOLVED"] + stat["PARTIAL"] + stat["TOLERATED"] + n_doc_bad
    for art, path in ALLOWED_TOLERANCES:
        for r in results:
            if r["artifact"] == art and r["path"] == path and r["status"] != "OK":
                n_not_allowlisted -= 1
    verdict = "pass" if (n_not_allowlisted == 0 and n_neg_bad == 0) else "fail"

    print()
    print("=" * 100)
    print("结论：定量 %d 条（OK %d / PARTIAL %d / TOLERATED %d / UNRESOLVED %d）；"
          "**非 OK 引用位点 %d 处**（文档 %d + 索引语义 %d）；语义断言 %d 次；"
          "否定断言失败 %d；豁免清单 %d 条 ⇒ verdict = %s"
          % (len(CITATIONS), stat["OK"], stat["PARTIAL"], stat["TOLERATED"], stat["UNRESOLVED"],
             n_sites, len(doc_sites), len(sem_sites), len(semantic), n_neg_bad,
             len(ALLOWED_TOLERANCES), verdict))
    print("=" * 100)

    # 幂等输出：不使用挂钟时间戳，改用**内容决定的运行指纹**。
    # 动机（建模手 2026-09-12）：输出里带挂钟时间戳 ⇒ "为了引用而取数"这个动作本身会改写被引用对象
    #（观测者效应），冻结因此不可能成立。改为内容指纹后：**输入不变 ⇒ 重跑产出的文件逐字节相同**。
    inputs = input_snapshot()
    rules_sig = "|".join(str(x) for x in (len(CITATIONS), len(NEGATIVE), len(RAW_NEGATIVE),
                                          len(CONTENT_ASSERTIONS), len(INDEX_RULES),
                                          len(ALLOWED_TOLERANCES)))
    fp_payload = "|".join([TOOL_VERSION, "rule_v%d" % RULE_VERSION, rules_sig] +
                          ["%s:%s" % (k, v.get("sha256_16", "NA")) for k, v in sorted(inputs.items())
                           if not v.get("fingerprint_excluded")])
    fp_inputs = [k for k, v in sorted(inputs.items()) if not v.get("fingerprint_excluded")]
    run_fingerprint = hashlib.sha256(fp_payload.encode("utf-8")).hexdigest()[:16]
    print("运行指纹 run_fingerprint = %s（内容决定；同输入 ⇒ 同输出）" % run_fingerprint)

    out = {
        "script": "CUMCM2026_C/Q2/Q2_field_path_check.py",
        "version": TOOL_VERSION,
        "run_fingerprint": run_fingerprint,
        "rule_version": RULE_VERSION,
        "run_fingerprint_rule": ("sha256(TOOL_VERSION + rule_version + 规则签名 + 各**参与锚定**的输入 sha256_16)[:16]；"
                                 "**不含挂钟时间**；**增长型记录不参与**（见 `fingerprint_excluded`）。"),
        "run_fingerprint_inputs": fp_inputs,
        "verify_hint": ("**可被对方当场复现**：跑 `--dry-run` 并比对其 stdout 的 `run_fingerprint` 与本字段；"
                        "相同 ⇒ 参与锚定的输入未变；不同 ⇒ 由 `inputs` 快照定位是哪一份变了。"),
        "script_frozen": True,
        "inputs_frozen": False,
        "inputs_note": ("本诊断件是**派生件**：脚本冻结不等于输出冻结——输入（尤其是被扫文档）一变，"
                        "重跑即产出不同 JSON。故 `script_frozen` 只描述脚本，`inputs` 给出"
                        "**本次扫描实际消费的输入五元组**，供读者判断『它当时扫的是哪一版』。"),
        "inputs": inputs,
        "artifacts": {k: {"path": v, "sha256_16": hashlib.sha256(open(v, "rb").read()).hexdigest()[:16]}
                      for k, v in ARTIFACTS.items()},
        "citations": results,
        "negative": neg,
        "content_assertions": content,
        "doc_scan": doc_scan,
        "semantic_mismatch": semantic,
        "numeric_overlap_warnings": warnings,
        "counts": {"citations": len(CITATIONS), **stat, "negative_failed": n_neg_bad,
                   "doc_non_ok": n_doc_bad, "allowlisted": len(ALLOWED_TOLERANCES),
                   "doc_non_ok_sites": len(doc_sites), "semantic_sites": len(sem_sites),
                   "semantic_assertions": len(semantic), "non_ok_sites_total": n_sites,
                   "numeric_overlap_warnings": len(warnings)},
        "verdict": verdict,
        "counting_convention": ("口径：`non_ok_sites_total` = **非 OK 引用位点数**（按 doc+line+path "
                                "去重；同一位点可产生多条断言，如 L138 的 4.46 与 0.6148 算 1 个位点、"
                                "2 次断言）；`negative_failed` = 断言失败次数；`doc_non_ok` = 文档扫描中 "
                                "UNRESOLVED+PARTIAL+TOLERATED 的项数（= 位点数）；`numeric_overlap_warnings` "
                                "为 advisory，不计入 verdict。"),
        "note": ("PARTIAL = 路径被缩写（末段在更深层存在）；TOLERATED = 靠宽容规则才解析"
                 "（如 dict 上写 `[*]`）。**两者都不等于逐字可解析**，未登记在 "
                 "ALLOWED_TOLERANCES 里即判不通过。"),
    }
    dst = os.path.join(C, "Q2", "_q2_field_path_check.json")
    if "--dry-run" in sys.argv:
        print("DRY RUN：只打印、未写盘（把『引用』与『改写』解耦）｜诊断件路径：%s" % dst)
        return 0 if verdict == "pass" else 1
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print("诊断 JSON 写出：%s" % dst)
    return 0 if verdict == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
