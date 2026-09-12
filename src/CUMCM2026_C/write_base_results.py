"""把已验证的 LP 基线写入附件 5 模板，形成可验收的 result1/result2/result4-2。"""

from __future__ import annotations

import shutil
from datetime import date, datetime
from pathlib import Path

import numpy as np
import openpyxl

from . import io_attachments as io
from . import paths
from .solve_problem2 import solve_day_solution


def _copy_template(name: str) -> Path:
    paths.ensure_output_dirs()
    out = paths.result_path(name)
    shutil.copy2(paths.RESULT_TEMPLATES[name], out)
    return out


def build(include_scenarios: bool = True) -> dict[str, str]:
    a1, a2, _a3, a4 = io.load_all()
    p1 = np.asarray(a1.price.values, dtype=float)
    result1_day, result1_vec = solve_day_solution(date(2025, 1, 1), p1, a1.load.values, a1.pv_forecast.values)
    assert result1_vec is not None and result1_day.success

    # 问题 1：只填一个完整日。
    out1 = _copy_template("result1")
    wb = openpyxl.load_workbook(out1)
    ws = wb["计划购电量"]
    for row in range(2, 146):
        # result1 采用完整附件区间口径，首行即 t=1 的 0:00-0:10。
        ws.cell(row, 1).value = io.result1_row_labels_decision()[row - 2]
        ws.cell(row, 2).value = float(result1_vec["purchase"][row - 2])
    ws2 = wb["充放电量"]
    for row in range(2, 8):
        b = row - 2
        ws2.cell(row, 2).value = float(result1_vec["charge"][24*b:24*(b+1)].sum())
        ws2.cell(row, 3).value = float(result1_vec["discharge"][24*b:24*(b+1)].sum())
    ws2.cell(2, 5).value = float(result1_vec["soc"][0])
    ws2.cell(3, 5).value = float(result1_vec["soc"][-1])
    wb.save(out1)

    outputs = {"result1": str(out1)}
    if include_scenarios:
        from .dispatch import run
        from .export_results import export_scenario
        for question in ("2", "4-2"):
            outputs["result" + question] = str(export_scenario(run(question)))
    return outputs



def main() -> int:
    outputs = build()
    for key, path in outputs.items():
        print(f"{key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
