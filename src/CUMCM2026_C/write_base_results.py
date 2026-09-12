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


def _write_plan_sheet(ws, rows: list[tuple[date, dict]], prices: dict[date, np.ndarray]) -> None:
    """写入宽表；B:EQ 按附件时间序号 t=1..144 写入，汇总列由直接数值重算。"""
    for excel_row, (day, vec) in enumerate(rows, start=2):
        ws.cell(excel_row, 1).value = datetime(day.year, day.month, day.day)
        p = vec["purchase"]
        for t in range(io.N_TIME_COLUMNS):
            # 附件 5 宽表表头从 0:10-0:20 开始，末列为次日首时段；
            # 因而按模板原始列语义写入 p[1],...,p[143],p[0]。
            ws.cell(excel_row, 2 + t).value = float(p[(t + 1) % io.N_TIME_COLUMNS])
        ws.cell(excel_row, 146).value = float(p.sum())
        ws.cell(excel_row, 147).value = float(np.dot(prices[day], p))


def _write_charge_rows(ws, solved: dict[date, dict]) -> None:
    for row in range(2, ws.max_row + 1):
        raw_day = ws.cell(row, 1).value
        if not isinstance(raw_day, (datetime, date)):
            continue
        day = raw_day.date() if isinstance(raw_day, datetime) else raw_day
        if day not in solved:
            continue
        vec = solved[day]
        block = row - 2
        b = block % 6
        if block // 6 >= 3:
            continue
        charge = vec["charge"][24 * b : 24 * (b + 1)].sum()
        discharge = vec["discharge"][24 * b : 24 * (b + 1)].sum()
        ws.cell(row, 3).value = float(charge)
        ws.cell(row, 4).value = float(discharge)
        if b == 0:
            ws.cell(row, 6).value = float(vec["soc"][0])
        elif b == 1:
            ws.cell(row, 6).value = float(vec["soc"][-1])


def _write_empty_emergency(ws) -> None:
    # 无紧急购电日期按模板约定留空，不伪造 0 行。
    for row in range(2, ws.max_row + 1):
        for col in range(1, ws.max_column + 1):
            if ws.cell(row, col).value in (None, ""):
                ws.cell(row, col).value = None


def build() -> dict[str, str]:
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

    # 问题 2：全年求解，但结果表只输出题面要求的 334 天。
    start = date.fromisoformat(paths.RESULT2_START)
    days = [d for d in a2.dates if d >= start]
    fixed: dict[date, dict] = {}
    realtime: dict[date, dict] = {}
    prices_fixed: dict[date, np.ndarray] = {}
    prices_rt: dict[date, np.ndarray] = {}
    p4_index = {d: i for i, d in enumerate(a4.dates)}
    for day in days:
        i = a2.dates.index(day)
        fixed[day] = solve_day_solution(day, p1, a2.load[i], a2.pv_actual[i])[1]
        prices_fixed[day] = p1
        rt_price = np.asarray(a4.price[p4_index[day]], dtype=float)
        realtime[day] = solve_day_solution(day, rt_price, a2.load[i], a2.pv_actual[i])[1]
        prices_rt[day] = rt_price
    for name, vectors, price_map in [("result2", fixed, prices_fixed), ("result4-2", realtime, prices_rt)]:
        out = _copy_template(name)
        wb = openpyxl.load_workbook(out)
        plan_rows = [(d, vectors[d]) for d in days]
        _write_plan_sheet(wb["计划购电量"], plan_rows, price_map)
        _write_charge_rows(wb["充放电量"], vectors)
        _write_empty_emergency(wb["紧急购电量"])
        wb.save(out)
    return {"result1": str(out1), "result2": str(paths.result_path("result2")), "result4-2": str(paths.result_path("result4-2"))}


def main() -> int:
    outputs = build()
    for key, path in outputs.items():
        print(f"{key}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
