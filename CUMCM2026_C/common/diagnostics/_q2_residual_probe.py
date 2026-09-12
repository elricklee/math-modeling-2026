"""残差 token 定位：报告 §二 引用的三个增量数字与三处章内行号，在 05:48:37 后的产物上是否仍成立。"""

import json
import pathlib
import re

ANAL = pathlib.Path("CUMCM2026_C/Q2/outputs/Q2_analysis.json")
DIAG = pathlib.Path("CUMCM2026_C/Q2/outputs/Q2_diagnostics.json")
CH = pathlib.Path("CUMCM2026_C/Q2/问题二模型的求解.md")

anal_text = ANAL.read_text(encoding="utf-8")
diag_text = DIAG.read_text(encoding="utf-8")
anal = json.loads(anal_text)

print("== 1) conclusions 条目（逐条前 200 字）==")
for i, c in enumerate(anal.get("conclusions", [])):
    print("   [%d] %s" % (i, json.dumps(c, ensure_ascii=False)[:200]))

print()
print("== 2) 原始文本里是否出现这些串 ==")
for s in ["1753305", "1 753 305", "322255", "322 255", "1431050", "1 431 050",
          "1753305.58", "322255.39", "322255.40", "5.4", "5.4 倍", "2.13"]:
    print("   anal:%-14s -> %d 次 | diag -> %d 次" % (s, anal_text.count(s), diag_text.count(s)))

print()
print("== 3) 章内三处引用的行号当前内容 ==")
lines = CH.read_text(encoding="utf-8").splitlines()
for n in (279, 338, 342, 442):
    body = lines[n - 1].strip()
    print("   L%-4d %s" % (n, body[:110]))

print()
print("== 4) 5.4 倍与两个增量的真实所在行 ==")
for pat in ["5.4 倍", "1 753 305", "322 255", "1 431 050", "零紧急购电", "紧急购电"]:
    hits = [i + 1 for i, ln in enumerate(lines) if pat in ln]
    print("   %-12s -> %s" % (pat, hits[:12]))

print()
print("== 5) 表 2 中 2025-09-23 的落盘精度 ==")
t2 = json.loads(diag_text).get("table2_tables")
blob = json.dumps(t2, ensure_ascii=False)
print("   含 6746.7732 ->", "6746.7732" in blob)
print("   含 6746.77   ->", "6746.77" in blob)
m = re.search(r".{0,80}6746\.77.{0,40}", blob)
print("   上下文:", m.group(0) if m else None)

print()
print("== 6) 残差 7.9580786405131221e-13 ==")
print("   diag 命中:", diag_text.count("7.9580786405131221e-13"), "| anal 命中:",
      anal_text.count("7.9580786405131221e-13"))
