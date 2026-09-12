"""只读核验：Q1/Q2 的产物与求解脚本在本轮统稿中是否真的零改动。

用途：统稿承诺「只改正文与论文主稿，不碰产物与脚本」。
本脚本列出相关文件的 mtime 与 sha256_16 作为可核对的证据。
"""

from __future__ import annotations

import hashlib
import pathlib
from datetime import datetime

ROOT = pathlib.Path("CUMCM2026_C")
FILES = [
    "Q1/outputs/result1.xlsx",
    "Q2/outputs/result2.xlsx",
    "Q1/outputs/Q1_diagnostics.json",
    "Q1/outputs/Q1_analysis.json",
    "Q2/outputs/Q2_diagnostics.json",
    "Q2/outputs/Q2_analysis.json",
    "Q1/outputs/Q1_timeseries.csv",
    "Q2/outputs/Q2_timeseries.csv",
    "Q2/outputs/Q2_emergency_detail.csv",
    "Q1/Q1_solve_plan.py",
    "Q1/Q1_analysis.py",
    "Q2/Q2_solve_plan.py",
    "Q2/Q2_analysis.py",
]


def main() -> int:
    print(f"{'文件':<34}{'字节':>12}  {'mtime':<18}sha256_16")
    print("-" * 84)
    for rel in FILES:
        p = ROOT / rel
        if not p.exists():
            print(f"{rel:<34}{'MISSING':>12}")
            continue
        b = p.read_bytes()
        mt = datetime.fromtimestamp(p.stat().st_mtime).strftime("%m-%d %H:%M:%S")
        print(f"{rel:<34}{len(b):>12,}  {mt:<18}{hashlib.sha256(b).hexdigest()[:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
