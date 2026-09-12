"""把重构后残留的旧路径/旧包名引用统一替换为新结构（幂等）。

只改文本，不改逻辑。替换映射：
  src.CUMCM2026_C.<mod> / src/CUMCM2026_C/<mod>
      -> CUMCM2026_C.common.code.<mod> / CUMCM2026_C/common/code/<mod>
  CUMCM2026_C.common.code.paths.ROOT -> CUMCM2026_C.common.code.paths.ROOT
  data/processed（作为输出目录） -> CUMCM2026_C/common/diagnostics
  results/CUMCM2026_C / figures/CUMCM2026_C -> CUMCM2026_C/Qn/outputs[/figures]
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def replacements(text: str) -> tuple[str, int]:
    n = 0
    subs = [
        (r"src\.CUMCM2026_C\.(\w+)", r"CUMCM2026_C.common.code.\1"),
        (r"src/CUMCM2026_C/(\w+)", r"CUMCM2026_C/common/code/\1"),
        (r"src\.config\.ROOT", "CUMCM2026_C.common.code.paths.ROOT"),
        (r"src\.config", "CUMCM2026_C.common.code.paths"),
        # 输出目录口径
        (r"``CUMCM2026_C/common/diagnostics/", "``CUMCM2026_C/common/diagnostics/"),
        (r"CUMCM2026_C/Q1/outputs/_envtest/", "CUMCM2026_C/Q1/outputs/_envtest/"),
        (r"输出到 CUMCM2026_C/common/diagnostics 供后续引用", "输出到 CUMCM2026_C/common/diagnostics 供后续引用"),
        (r"data/processed/(\w+\.json)", r"CUMCM2026_C/common/diagnostics/\1"),
    ]
    for pat, rep in subs:
        text, k = re.subn(pat, rep, text)
        n += k
    return text, n


def main() -> None:
    targets = sorted((ROOT / "CUMCM2026_C" / "common" / "code").glob("*.py"))
    targets += sorted((ROOT / "CUMCM2026_C" / "common" / "tools").glob("*.py"))
    total = 0
    for f in targets:
        if f.name == "restructure_repo.py":
            continue  # 它必须保留旧目录名（清理用）
        src = f.read_text(encoding="utf-8")
        out, n = replacements(src)
        if n and out != src:
            f.write_text(out, encoding="utf-8")
            print(f"  {f.name}: 替换 {n} 处")
            total += n
    print(f"合计替换 {total} 处")


if __name__ == "__main__":
    main()
