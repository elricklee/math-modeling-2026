"""一次性脚本：Q2 求解章的表号整体平移（前缀 2 -> 6）。

背景：论文合并统稿后，问题二落在论文第 6 节，故表号前缀由 2 改为 6。
本脚本只改「表 2-N」（N 为数字）这一种形态，不动：
  * 「题目表 1/2/3/4」（题面模板表，属另一命名空间）
  * 「表 6-1」（建立章已改好的符号增补表）
  * 图片路径中的 Q2_figN（是文件名，与正文编号无关）

幂等性：脚本可重复运行；第二次运行时「表 2-N」已为 0 处，不产生变化。
"""

from __future__ import annotations

import hashlib
import pathlib
import re
import sys

TARGET = pathlib.Path("CUMCM2026_C/Q2/问题二模型的求解.md")
PATTERN = re.compile(r"表 2-(\d+)")


def fingerprint(path: pathlib.Path) -> tuple[int, int, str]:
    b = path.read_bytes()
    return len(b.decode("utf-8").splitlines()), len(b), hashlib.sha256(b).hexdigest()[:16]


def main() -> int:
    text = TARGET.read_text(encoding="utf-8")
    before = PATTERN.findall(text)

    if not before:
        print("未发现「表 2-N」形态，无需改动（脚本已幂等）。")
        return 0

    numbers = sorted({int(n) for n in before})
    labels = re.findall(r"(?m)^\*\*表 2-\d+", text)
    print(f"待改「表 2-N」出现 {len(before)} 处，涉及表号 {numbers[0]}..{numbers[-1]}")
    print(f"标签行（行首 **表 2-N）{len(labels)} 处")
    print(f"题面模板表引用（本文件内）：{sorted(set(re.findall(r'题目表 ?\\d', text)))}")
    print(f"指纹（改前）：{fingerprint(TARGET)}")

    new_text = PATTERN.sub(lambda m: f"表 6-{m.group(1)}", text)

    # 核验 1：改后不应再有任何「表 2-N」
    leftover = PATTERN.findall(new_text)
    assert not leftover, f"仍有残留：{leftover}"

    # 核验 2：表 6-N 的个数应等于改动前表 2-N 的个数（一一对应，不增不删）
    gained = re.findall(r"表 6-(\d+)", new_text)
    assert len(gained) == len(before), f"数量不符：改前 {len(before)} -> 改后 {len(gained)}"

    # 核验 3：题面模板表引用（题目表 N）必须原样保留，一字未动
    tmpl_before = re.findall(r"题目表 ?\d", text)
    tmpl_after = re.findall(r"题目表 ?\d", new_text)
    assert tmpl_before == tmpl_after, f"题面模板表引用被误改：{tmpl_before} -> {tmpl_after}"

    # 核验 4：行数不得变化（纯字符替换，不应增删行）
    assert len(text.splitlines()) == len(new_text.splitlines()), "行数发生变化"

    TARGET.write_text(new_text, encoding="utf-8")
    print(f"已写入。表 6-N 共 {len(gained)} 处，表号 {sorted({int(n) for n in gained})}")
    print(f"指纹（改后）：{fingerprint(TARGET)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
