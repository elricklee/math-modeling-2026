"""版本锚与判据串的实测探针（只读，不写任何项目文件）。

用途：给《Q2_最终验收报告.md》的「版本锚」「判据串清单」「引用纪律」提供可复现的实测数字。
对每份文件输出四快照（行数 / 字节数 / CRLF 数 / mtime）与判据串命中数。

两种用法：
  1) 直接运行 —— 打印四快照 + 判据计数，并输出一行规范的 SNAPSHOT 行。
     `.venv\\Scripts\\python.exe CUMCM2026_C\\common\\diagnostics\\_q2_version_probe.py`
  2) 校验一条状态行 —— 把别处引用（或上一轮抄写）的 SNAPSHOT 行交给它比对：
     `... _q2_version_probe.py --expect "SNAPSHOT ..."`
     逐字段报 OK/MISMATCH，任一字段不符则 exit 1。

设计意图：把"引用纪律"从"要求人小心"变成"要求工具取数"——
引用的那一方贴 SNAPSHOT 行，任何人都能用 --expect 机械判定该引用是否仍是当前版本。
"""

import datetime
import pathlib
import re
import sys

FILES = [
    "CUMCM2026_C/Q2/问题二模型的建立.md",
    "CUMCM2026_C/Q2/问题二模型的求解.md",
    "CUMCM2026_C/Q2/Q2_最终验收报告.md",
]
# 第 4 份只进 SNAPSHOT 行（它是本报告的引用对象，但不适用两章的判据计数）
EXTRA = ["CUMCM2026_C/common/docs/C题_问题二契约缺陷留痕.md"]

NEG = ["乐观", "保守", "上界式", "乐观下界", "保守上界", "上界", "下界"]
SPAN = '<span style="color:red"'
SHORT = {0: "建立", 1: "求解", 2: "报告"}


def snapshot():
    """返回 [(短名, 行数, 字节数, mtime, path)]，顺序与 FILES 一致。"""
    out = []
    for i, rel in enumerate(FILES + EXTRA):
        path = pathlib.Path(rel)
        text = path.read_text(encoding="utf-8")
        raw = path.read_bytes()
        mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime("%H:%M:%S")
        name = SHORT.get(i, "留痕")
        out.append((name, len(text.splitlines()), len(raw), mtime, path))
    return out


def snapshot_line(stamp):
    parts = ["%s %d行/%dB/%s" % (n, ln, b, mt) for n, ln, b, mt, _ in snapshot()]
    return "SNAPSHOT %s | %s" % (stamp, " | ".join(parts))


def main():
    argv = sys.argv[1:]
    now = datetime.datetime.now().strftime("%H:%M:%S")

    if argv and argv[0] == "--expect":
        if len(argv) < 2:
            print("用法：--expect \"SNAPSHOT ... \"")
            return 2
        quoted = " ".join(argv[1:])
        want = {}
        for n, ln, b, mt in re.findall(r"([^\s|]+) (\d+)行/(\d+)B/(\d\d:\d\d:\d\d)", quoted):
            want[n] = (int(ln), int(b), mt)
        if not want:
            print("无法从给出文本里解析出任何 `名称 行数行/字节数B/mtime` 字段。")
            print("请使用本工具直接运行时输出的 SNAPSHOT 行格式。")
            return 2
        bad = 0
        print("校验引用（取数 %s）：" % now)
        for n, ln, b, mt, _ in snapshot():
            if n not in want:
                print("  %-4s 引用未包含该文件；当前为 %d行/%dB/%s" % (n, ln, b, mt))
                continue
            wln, wb, wmt = want[n]
            marks = []
            for label, got, exp in (("行数", ln, wln), ("字节", b, wb), ("mtime", mt, wmt)):
                marks.append("%s %s" % (label, "OK" if got == exp else "MISMATCH(引用 %s / 当前 %s)"
                                        % (exp, got)))
            if any("MISMATCH" in m for m in marks):
                bad += 1
            print("  %-4s %s" % (n, "；".join(marks)))
        print("结论：%s" % ("引用与当前版本一致" if bad == 0
                            else "**引用已过期**：%d 个文件不符，须按当前值重取" % bad))
        return 0 if bad == 0 else 1

    for rel in FILES:
        path = pathlib.Path(rel)
        text = path.read_text(encoding="utf-8")
        raw = path.read_bytes()
        tabs = sorted({int(m) for m in re.findall(r"表 2-(\d+)", text)})
        mtime = datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(rel)
        print("   lines=%d  bytes=%d  crlf=%d  mtime=%s"
              % (len(text.splitlines()), len(raw), raw.count(b"\r\n"), mtime))
        print("   表号=%s  (count %d)" % (tabs, len(tabs)))
        print("   占位符: 此处插入图=%d  span=%d" % (text.count("此处插入图"), text.count(SPAN)))
        print("   术语: 流水线=%d  本文结果=%d  本文的=%d"
              % (text.count("流水线"), text.count("本文结果"), text.count("本文的")))
        print("   负向判据: " + "  ".join("%s=%d" % (k, text.count(k)) for k in NEG))
        print()
    for rel in EXTRA:
        path = pathlib.Path(rel)
        text = path.read_text(encoding="utf-8")
        print("%s" % rel)
        print("   lines=%d  bytes=%d  mtime=%s"
              % (len(text.splitlines()), len(path.read_bytes()),
                 datetime.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")))
        print()

    print("── 状态行（可直接粘进汇报；用 --expect 校验他人引用）──")
    print(snapshot_line(now))
    print("取数命令：.venv\\Scripts\\python.exe CUMCM2026_C\\common\\diagnostics\\_q2_version_probe.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
