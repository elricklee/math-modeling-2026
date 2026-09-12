"""``result*.xlsx`` 验收校验：按题目表 1~表 4 与附件 5 模板逐项核对。

设计要点
--------
* **缺失即提示，不抛异常**：本轮结果文件尚未生成，所有校验函数都通过
  :func:`validate_all` 容忍文件不存在，返回 ``status="missing"`` 的条目。
* 校验口径与 ``docs/C题_数据工程与结果规格.md`` 中的"验收检查清单"逐条对应。
* 校验所需的数据（电价、负载、光伏）来自 :mod:`CUMCM2026_C.common.code.io_attachments`，
  不重新解析原始 xlsx。

覆盖的验收项
------------
A. 结构：工作表名、行列数、表头、时间段标签序列、日期范围。
B. 数值：非负性、量程、储能电量上下界、首末电量相等。
C. 功率平衡：``购电量 + 放电量 + (光伏-负载) * 10/60 >= 0`` 的残差。
D. 储能递推：``E[t+1] = E[t] + eta*充 - 放/eta`` 的闭合残差。
E. 费用复算：``全天购电量`` 与 ``全天购电费`` 与逐时段明细的一致性。
"""

from __future__ import annotations

import json
import math
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

import numpy as np
import openpyxl

from . import io_attachments as io
from . import paths

# --------------------------------------------------------------------------- #
# 校验结果容器
# --------------------------------------------------------------------------- #
Status = str  # "passed" | "failed" | "missing" | "skipped"


@dataclass
class CheckResult:
    """单条校验的结果。

    Attributes:
        criterion: 验收判据的简短描述（与文档清单一一对应）。
        status: ``"passed"`` / ``"failed"`` / ``"missing"`` / ``"skipped"``。
        detail: 人类可读的说明，包含实测数字。
        residual: 关键数值残差（若适用）。
    """

    criterion: str
    status: Status
    detail: str = ""
    residual: float | None = None

    def to_dict(self) -> dict[str, Any]:
        """转为可 JSON 序列化的字典。"""
        return {
            "criterion": self.criterion,
            "status": self.status,
            "detail": self.detail,
            "residual": None if self.residual is None else float(self.residual),
        }


@dataclass
class FileReport:
    """单个结果文件的校验报告。

    Attributes:
        name: 逻辑名，如 ``"result1"``。
        path: 目标路径。
        exists: 文件是否存在。
        checks: 该文件下的全部校验项。
    """

    name: str
    path: Path
    exists: bool
    checks: list[CheckResult] = field(default_factory=list)

    def add(self, result: CheckResult) -> None:
        """追加一条校验结果。"""
        self.checks.append(result)

    @property
    def failed(self) -> list[CheckResult]:
        """返回所有失败项。"""
        return [c for c in self.checks if c.status == "failed"]

    @property
    def passed(self) -> list[CheckResult]:
        """返回所有通过项。"""
        return [c for c in self.checks if c.status == "passed"]

    def to_dict(self) -> dict[str, Any]:
        """转为可 JSON 序列化的字典。"""
        return {
            "name": self.name,
            "path": str(self.path),
            "exists": self.exists,
            "n_checks": len(self.checks),
            "n_passed": len(self.passed),
            "n_failed": len(self.failed),
            "checks": [c.to_dict() for c in self.checks],
        }


# --------------------------------------------------------------------------- #
# 模板结构规格（实测自附件 5，见 docs）
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class SheetSpec:
    """某个结果工作表的期望结构。

    Attributes:
        header: 期望表头（逐字符比较）。
        n_body_rows: 期望数据行数；``None`` 表示动态。
        label_column: 承载时间段标签的列号（1-based）。
    """

    header: tuple[str, ...]
    n_body_rows: int | None
    label_column: int


PLAN_HEADER: tuple[str, ...] = (
    "日期\\时间",
    *io.plan_purchase_labels_as_template(),
    "全天购电量",
    "全天购电费",
)
"""``计划购电量``（宽表）的 147 列表头。

第 43 列（1-based）是模板拼写瑕疵 ``7:0-7:10``（规范写法应为 ``7:00-7:10``），
由 :data:`CUMCM2026_C.common.code.io_attachments.TEMPLATE_LABEL_QUIRKS` 显式记录并
**建议原样保留**，校验时不做纠正。
"""

_ADJUST_HEADER: tuple[str, ...] = PLAN_HEADER
"""``调整购电量`` 表头与计划购电量相同。"""

PLAN_HEADER_DECISION: tuple[str, ...] = (
    "日期\\时间",
    *[label for _slot, label in io.write_plan_columns("decision")],
    "全天购电量",
    "全天购电费",
)
"""**方案 A 口径**的 ``计划购电量`` 147 列表头（队长裁定 A18 / 问题二契约 §4.1 决议 2）。

与 :data:`PLAN_HEADER` 的差别只在 144 个时间段列：第 ``(i + 1)`` 列装**时段 ``t = i``**
的值，表头 = :func:`CUMCM2026_C.common.code.io_attachments.interval_label`\\ ``(i)``，
即 ``0:00-0:10`` … ``23:50-0:00+1``（不含模板的 ``7:0-7:10`` 笔误，末列不再是次日首区间）。

.. note::
   两种表头口径**只影响标签文本**，不改变数值列的位置：数据位 ``i`` 与业务时段
   ``t = i`` 的对应关系在两种口径下都由调用方选定，本模块只负责按调用方声明的
   口径做**真实**比较，绝不放宽比较或删除校验项。
"""

PLAN_HEADER_VARIANTS: dict[str, tuple[str, ...]] = {
    "template": PLAN_HEADER,
    "decision": PLAN_HEADER_DECISION,
}
"""``计划购电量`` / ``调整购电量`` 可接受的两套表头口径。

* ``"template"``（**默认**，模板原样，含 ``7:0-7:10`` 笔误与末列 ``0:00-0:10+1``）
* ``"decision"``（**本队基准**，方案 A：``interval_label(1..144)``）
"""

CHARGE_DISCHARGE_HEADER: tuple[str, ...] = (
    "日期",
    "时间段",
    "充电量",
    "放电量",
    "时刻",
    "储电量",
)
"""``result2/3/4-*`` ``充放电量`` 表头（6 列，含日期列）。"""

CHARGE_DISCHARGE_HEADER_RESULT1: tuple[str, ...] = (
    "时间段",
    "充电量",
    "放电量",
    "时刻",
    "储电量",
)
"""``result1.xlsx`` ``充放电量`` 表头（5 列，无日期列——只有单日）。"""

EMERGENCY_HEADER: tuple[str, ...] = ("日期", "购电时间段", "购电量")
"""``紧急购电量`` 表头。"""

RESULT1_PLAN_LABELS: list[str] = io.result1_row_labels_decision()
"""``result1.xlsx/计划购电量`` 的 144 行标签（**队长裁定 R8 默认口径**）。

即附件 1 口径 ``0:00-0:10`` … ``23:50-0:00+1``；模板原样序列见
:data:`RESULT1_LABEL_VARIANTS` 的 ``"template"`` 项。
"""

PLAN_TIME_LABELS: list[str] = io.plan_purchase_labels_as_template()
"""``result2/3/4-*`` ``计划购电量`` 的 144 个时间列表头（**含** ``7:0-7:10`` 瑕疵）。"""

PLAN_TIME_LABELS_CANONICAL: list[str] = io.plan_purchase_labels()
"""同上，但使用规范化写法 ``7:00-7:10``（仅在确认评审接受纠正时使用）。"""

BLOCK_LABELS: list[str] = io.half_hour_block_labels()
"""``充放电量`` 的 6 个 4 小时时段标签。"""

PLANNED_RESULT_DATES: list[date] = [
    date(2025, 2, 1) + timedelta(days=i)
    for i in range((date(2025, 12, 31) - date(2025, 2, 1)).days + 1)
]
"""``result2/3/4-*`` 计划购电量应覆盖的 334 天（2025-02-01..2025-12-31）。"""

TEMPLATE_TYPOS: dict[str, str] = {
    "计划购电量!N43(1-based 列 43)": "7:0-7:10",
    "计划购电量!末列": (
        "0:00-0:10+1，语义为【次日首个区间】，非当日 0:00-0:10"
        "（队长裁定 R7：原样保留模板 144 列，该列填次日 0:00-0:10 的值）"
    ),
    "result1.计划购电量!行标签": (
        "模板原为 0:10-0:20 … 0:00+1-0:10+1（整体左移一格），"
        "队长裁定 R8：改用附件 1 口径 0:00-0:10 … 23:50-0:00+1"
    ),
}
"""模板中的已知拼写/命名瑕疵与已裁定差异，写盘时按下述口径执行。"""

RESULT1_LABEL_VARIANTS: dict[str, list[str]] = {
    "decision": io.result1_row_labels_decision(),
    "template": io.result1_row_labels(),
}
"""``result1.计划购电量`` 行标签的两种可接受口径。

* ``decision``（**默认、队长裁定 R8**）：附件 1 口径，``0:00-0:10`` … ``23:50-0:00+1``。
* ``template``：模板原样，``0:10-0:20`` … ``0:00+1-0:10+1``（仅在其批次明确要求
  逐字符照模板时使用）。
"""

# 数值容差
ENERGY_TOL: float = 1e-6
"""kWh 级数值比较容差。"""

POWER_BALANCE_TOL: float = 1e-4
"""功率平衡残差容差（kWh）。"""


# --------------------------------------------------------------------------- #
# 基础读取工具
# --------------------------------------------------------------------------- #
def _load_rows(path: Path, sheet: str) -> list[list[Any]]:
    """读入工作表全部单元格值。

    Args:
        path: xlsx 路径。
        sheet: 工作表名。

    Returns:
        行列表。
    """
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=False)
    try:
        worksheet = workbook[sheet]
        return [list(row) for row in worksheet.iter_rows(values_only=True)]
    finally:
        workbook.close()


def _as_float(value: Any) -> float:
    """单元格值 → float；空值/非数值返回 ``nan``。"""
    if value is None:
        return float("nan")
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return float("nan")


def _sheet_names(path: Path) -> list[str]:
    """返回工作簿内工作表名列表。"""
    workbook = openpyxl.load_workbook(path, read_only=True)
    try:
        return list(workbook.sheetnames)
    finally:
        workbook.close()


def _fmt_date(value: Any) -> str:
    """把日期单元格渲染成 ISO 字符串，供比较与报告使用。"""
    parsed = io.coerce_date(value)
    return parsed.isoformat() if parsed else "<none>"


def _is_placeholder(value: Any) -> bool:
    """判断是否是模板中的"省略号"占位行（``⁝``）。"""
    return value is not None and str(value).strip() in {"⁝", "...", "…"}


# --------------------------------------------------------------------------- #
# A. 结构校验
# --------------------------------------------------------------------------- #
def check_sheets(path: Path, expected: Sequence[str]) -> CheckResult:
    """校验工作表名与顺序完全一致。

    Args:
        path: 结果文件路径。
        expected: 期望的工作表名序列。

    Returns:
        校验结果。
    """
    actual = _sheet_names(path)
    ok = actual == list(expected)
    return CheckResult(
        criterion=f"工作表序列 == {list(expected)}",
        status="passed" if ok else "failed",
        detail=f"实测 {actual}",
    )


def check_plan_sheet(
    path: Path,
    sheet: str,
    *,
    label_mode: str,
    label_variant: str = "decision",
    header_variant: str = "template",
) -> CheckResult:
    """校验 ``计划购电量`` / ``调整购电量`` 宽表（147 列 = 日期 + 144 时段 + 2 汇总列）。

    Args:
        path: 结果文件路径。
        sheet: 工作表名。
        label_mode: ``"header"``（result2/3/4-*，标签在表头）或
            ``"row"``（result1，标签在首列）。
        label_variant: ``result1``（``label_mode="row"``）时的行标签口径，
            ``"decision"``（默认，附件 1 口径）或 ``"template"``。
        header_variant: ``label_mode="header"`` 时的**表头**口径（队长裁定 A18）：

            * ``"template"``（**默认**，保持既有行为）：模板原样 147 列表头，
              含第 43 列 ``7:0-7:10`` 笔误与末列 ``0:00-0:10+1``。
            * ``"decision"``（**本队基准，方案 A**）：144 个时间列表头为
              ``0:00-0:10`` … ``23:50-0:00+1``，与 :func:`io.write_plan_columns`
              的 ``mode="decision"`` 逐字符一致；数据位 ``i`` 仍装时段 ``t = i``。

            两个口径**禁止混用**，且本参数不改变校验严格程度——表头仍逐字符比较、
            日期序列仍与 :data:`PLANNED_RESULT_DATES` 全等比较。

    Returns:
        校验结果。

    Raises:
        ValueError: ``header_variant`` 不是 ``"template"`` / ``"decision"``。
    """
    rows = _load_rows(path, sheet)
    header = ["" if v is None else str(v).strip() for v in rows[0]]
    body = [r for r in rows[1:] if not _is_placeholder(r[0] if r else None)]

    if label_mode == "header":
        if header_variant not in PLAN_HEADER_VARIANTS:
            raise ValueError(
                f"header_variant 必须是 {sorted(PLAN_HEADER_VARIANTS)} 之一，"
                f"收到 {header_variant!r}"
            )
        expected = PLAN_HEADER_VARIANTS[header_variant]
        problems: list[str] = []
        if header != list(expected):
            for i, (got, want) in enumerate(zip(header, expected)):
                if got != want:
                    problems.append(f"列{i + 1}: 实测{got!r} 期望{want!r}")
            if len(header) != len(expected):
                problems.append(f"表头列数 实测{len(header)} 期望{len(expected)}")
        ok_head = not problems
        dates = [io.coerce_date(r[0]) for r in body]
        ok_dates = dates == PLANNED_RESULT_DATES
        detail = (
            f"表头口径={header_variant}; 表头 {'一致' if ok_head else '不一致: ' + '; '.join(problems[:5])}; "
            f"数据行 {len(body)} 行(期望 334); "
            f"日期 {_fmt_date(body[0][0]) if body else '<empty>'}.."
            f"{_fmt_date(body[-1][0]) if body else '<empty>'}"
        )
        ok = ok_head and ok_dates and len(body) == len(PLANNED_RESULT_DATES)
        return CheckResult(
            criterion=f"{sheet}: 147 列表头({header_variant} 口径) + 334 天(2025-02-01..12-31)",
            status="passed" if ok else "failed",
            detail=detail,
        )

    # label_mode == "row"：result1
    expected = RESULT1_LABEL_VARIANTS.get(label_variant, RESULT1_LABEL_VARIANTS["decision"])
    labels = ["" if (r[0] if r else None) is None else str(r[0]).strip() for r in body]
    ok_labels = labels == expected
    ok_cols = len(header) == 2 and header[:2] == ["时间段", "购电量"]
    detail = (
        f"列数 {len(header)}(期望 2); 行数 {len(body)}(期望 144); "
        f"标签口径={label_variant}; 标签 {'匹配' if ok_labels else '不匹配'}"
    )
    if not ok_labels and labels:
        diff = [
            f"行{i + 1}: 实测{labels[i]!r} 期望{expected[i]!r}"
            for i in range(min(len(labels), len(expected)))
            if labels[i] != expected[i]
        ]
        detail += "; " + ("; ".join(diff[:3]) if diff else "")
        # 若实测与另一种口径吻合，给出明确提示而非单纯报错
        for alt_name, alt in RESULT1_LABEL_VARIANTS.items():
            if alt_name != label_variant and labels == alt:
                detail += (
                    f"（实测与 {alt_name!r} 口径一致：模板原样标签整体左移一格，"
                    "队长裁定 R8 要求采用 decision 口径）"
                )
    return CheckResult(
        criterion=f"{sheet}: 2 列 + 144 行标签({expected[0]}..{expected[-1]})",
        status="passed" if (ok_labels and ok_cols) else "failed",
        detail=detail,
    )


def charge_discharge_columns(header: Sequence[Any]) -> tuple[int, int, int, int, int] | None:
    """识别 ``充放电量`` 的列布局，返回 0-based 列下标。

    模板存在两种布局：

    * ``result2/3/4-*``：6 列 ``日期 | 时间段 | 充电量 | 放电量 | 时刻 | 储电量``
    * ``result1``：5 列 ``时间段 | 充电量 | 放电量 | 时刻 | 储电量``（无日期列）

    Args:
        header: 表头行。

    Returns:
        ``(时间段, 充电量, 放电量, 时刻, 储电量)`` 的 0-based 列下标；
        无法识别时返回 ``None``。
    """
    names = ["" if v is None else str(v).strip() for v in header]
    try:
        return (
            names.index("时间段"),
            names.index("充电量"),
            names.index("放电量"),
            names.index("时刻"),
            names.index("储电量"),
        )
    except ValueError:
        return None


def _is_midnight_stamp(value: Any) -> bool:
    """判断 ``时刻`` 列单元格是否表示 0:00（兼容 ``datetime.time`` 与字符串）。"""
    if isinstance(value, (time, datetime)):
        return value.hour == 0 and value.minute == 0
    text = "" if value is None else str(value).strip()
    return text in {"0:00", "0:0", "0:00:00"}


def _is_end_of_day_stamp(value: Any) -> bool:
    """判断 ``时刻`` 列单元格是否表示 24:00（模板写作字符串 ``'24:00'``）。"""
    if isinstance(value, (time, datetime)):
        return False
    return "" if value is None else str(value).strip() in {"24:00", "24:0"}


def check_charge_discharge_sheet(
    path: Path,
    sheet: str,
    *,
    expect_dates: Sequence[date] | None,
) -> CheckResult:
    """校验 ``充放电量`` 表结构（自动兼容 5 列 / 6 列两种模板布局）。

    每一组为 6 行（``0:00-4:00`` … ``20:00-24:00``）；日期只写在组内首行（合并
    单元格式留空），``时刻`` 列只在组内第 1、2 行分别给出 ``0:00`` 与 ``24:00``，
    ``储电量`` 列与之同行。

    Args:
        path: 结果文件路径。
        sheet: 工作表名。
        expect_dates: 期望出现的日期集合；``None`` 表示不校验（result1 无日期列）。

    Returns:
        校验结果。
    """
    rows = _load_rows(path, sheet)
    header = ["" if v is None else str(v).strip() for v in rows[0]]
    problems: list[str] = []

    columns = charge_discharge_columns(rows[0])
    expected_header = (
        list(CHARGE_DISCHARGE_HEADER_RESULT1) if expect_dates is None
        else list(CHARGE_DISCHARGE_HEADER)
    )
    if header != expected_header:
        problems.append(f"表头 实测{header} 期望{expected_header}")
    if columns is None:
        problems.append(f"无法识别列布局，实测表头 {header}")
        return CheckResult(
            criterion=f"{sheet}: 表头可识别（5 列或 6 列布局）",
            status="failed",
            detail="; ".join(problems),
        )

    col_label, col_charge, col_discharge, col_stamp, col_soc = columns
    body = [r for r in rows[1:] if not _is_placeholder(r[col_label] if len(r) > col_label else None)]
    if len(body) % 6 != 0:
        problems.append(f"数据行数 {len(body)} 不是 6 的整数倍")

    n_groups = len(body) // 6
    for g in range(n_groups):
        block = body[6 * g : 6 * (g + 1)]
        labels = [str(b[col_label]).strip() if len(b) > col_label and b[col_label] is not None else ""
                  for b in block]
        if labels != BLOCK_LABELS:
            problems.append(f"第{g + 1}组时间段 {labels} 期望 {BLOCK_LABELS}")
        stamp1 = block[0][col_stamp] if len(block[0]) > col_stamp else None
        stamp2 = block[1][col_stamp] if len(block[1]) > col_stamp else None
        ok1 = _is_midnight_stamp(stamp1)
        ok2 = _is_end_of_day_stamp(stamp2)
        if not (ok1 and ok2):
            problems.append(f"第{g + 1}组时刻列 实测({stamp1!r}, {stamp2!r}) 期望(0:00, 24:00)")
        if expect_dates is not None:
            first = io.coerce_date(block[0][0])
            if first not in set(expect_dates):
                problems.append(f"第{g + 1}组日期 {first} 不在期望集合内")

    detail = f"{n_groups} 组 x 6 行; " + ("全部合规" if not problems else "; ".join(problems[:4]))
    return CheckResult(
        criterion=f"{sheet}: 6 行/组(0:00-4:00..20:00-24:00) + 时刻列(0:00,24:00)",
        status="passed" if not problems else "failed",
        detail=detail,
    )


def check_emergency_sheet(path: Path, sheet: str) -> CheckResult:
    """校验 ``紧急购电量`` 表结构（日期 / 购电时间段 / 购电量）。

    Args:
        path: 结果文件路径。
        sheet: 工作表名。

    Returns:
        校验结果。
    """
    rows = _load_rows(path, sheet)
    header = ["" if v is None else str(v).strip() for v in rows[0]]
    body = [r for r in rows[1:] if not _is_placeholder(r[0] if r else None)]
    problems: list[str] = []
    if header != list(EMERGENCY_HEADER):
        problems.append(f"表头 实测{header} 期望{list(EMERGENCY_HEADER)}")
    bad_span = [r[1] for r in body if r[1] is not None and "-" not in str(r[1])]
    if bad_span:
        problems.append(f"非 '起-止' 格式的时间段 {bad_span[:3]}")
    detail = f"{len(body)} 条明细; " + ("格式合规" if not problems else "; ".join(problems[:3]))
    return CheckResult(
        criterion=f"{sheet}: 3 列 + 时间段 '起-止' 格式",
        status="passed" if not problems else "failed",
        detail=detail,
    )


# --------------------------------------------------------------------------- #
# B. 数值校验
# --------------------------------------------------------------------------- #
def extract_plan_matrix(
    path: Path, sheet: str, *, label_mode: str
) -> tuple[list[date | None], np.ndarray] | None:
    """提取 ``计划购电量`` 的数值矩阵。

    Args:
        path: 结果文件路径。
        sheet: 工作表名。
        label_mode: ``"header"`` 或 ``"row"``。

    Returns:
        ``(dates, matrix)``；``matrix`` 形状 ``(n_rows, 144)``，日期列在
        ``"row"`` 模式下返回 ``None`` 列表。解析失败返回 ``None``。
    """
    rows = _load_rows(path, sheet)
    body = [r for r in rows[1:] if not _is_placeholder(r[0] if r else None)]
    if not body:
        return None
    if label_mode == "header":
        if len(rows[0]) < 145:
            return None
        dates_out: list[date | None] = [io.coerce_date(r[0]) for r in body]
        matrix = np.array([[_as_float(v) for v in r[1:145]] for r in body], dtype=float)
    else:
        if len(rows[0]) < 2:
            return None
        dates_out = [None] * len(body)
        matrix = np.array([[_as_float(r[1] if len(r) > 1 else None)] for r in body], dtype=float)
    return dates_out, matrix


def extract_storage_series(
    path: Path, sheet: str
) -> list[tuple[date | None, np.ndarray, float, float]]:
    """提取 ``充放电量`` 的逐组数据。

    Args:
        path: 结果文件路径。
        sheet: 工作表名。

    Returns:
        ``[(日期, [6 个充电量], [6 个放电量], 0:00 储电量, 24:00 储电量), ...]``；
        缺失值以 ``nan`` 表示。
    """
    rows = _load_rows(path, sheet)
    columns = charge_discharge_columns(rows[0])
    if columns is None:
        return []
    col_label, col_charge, col_discharge, _col_stamp, col_soc = columns
    body = [r for r in rows[1:] if not _is_placeholder(r[col_label] if len(r) > col_label else None)]
    out: list[tuple[date | None, np.ndarray, np.ndarray, float, float]] = []
    for g in range(len(body) // 6):
        block = body[6 * g : 6 * (g + 1)]
        day = io.coerce_date(block[0][0])
        charge = np.array([_as_float(b[col_charge] if len(b) > col_charge else None) for b in block])
        discharge = np.array(
            [_as_float(b[col_discharge] if len(b) > col_discharge else None) for b in block]
        )
        # 储电量列：组内第 1 行写 0:00、第 2 行写 24:00
        soc0 = _as_float(block[0][col_soc]) if len(block[0]) > col_soc else math.nan
        soc24 = _as_float(block[1][col_soc]) if len(block[1]) > col_soc else math.nan
        out.append((day, charge, discharge, soc0, soc24))
    return out


def check_non_negative(
    matrix: np.ndarray | None, *, what: str, tol: float = 0.0
) -> CheckResult:
    """校验数值矩阵非负。

    Args:
        matrix: 待检矩阵；``None`` 时返回 ``skipped``。
        what: 描述文本。
        tol: 允许的下界松弛。

    Returns:
        校验结果。
    """
    if matrix is None or matrix.size == 0 or np.all(np.isnan(matrix)):
        return CheckResult(f"{what} 非负", "skipped", "无数值可检")
    finite = matrix[~np.isnan(matrix)]
    n_neg = int((finite < -abs(tol)).sum())
    worst = float(finite.min()) if finite.size else math.nan
    return CheckResult(
        criterion=f"{what} >= 0",
        status="passed" if n_neg == 0 else "failed",
        detail=f"负值个数 {n_neg}/{finite.size}; 最小值 {worst:.6f}",
        residual=worst,
    )


def recompute_daily_totals(
    plan: np.ndarray,
    price: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """复算 ``全天购电量`` 与 ``全天购电费``。

    Args:
        plan: 形状 ``(n_days, 144)`` 的逐时段购电量（kWh）。
        price: 形状 ``(n_days, 144)`` 的逐时段电价（元/kWh）。

    Returns:
        ``(全天购电量, 全天购电费)``，各长度 ``n_days``。
    """
    total_energy = np.nansum(plan, axis=1)
    total_cost = np.nansum(plan * price, axis=1)
    return total_energy, total_cost


def check_totals(
    path: Path,
    sheet: str,
    price: np.ndarray,
) -> CheckResult:
    """校验 ``全天购电量`` / ``全天购电费`` 与逐时段明细一致。

    Args:
        path: 结果文件路径。
        sheet: 工作表名。
        price: 形状 ``(n_days, 144)`` 的电价矩阵，与计划购电量行序一致。

    Returns:
        校验结果。
    """
    rows = _load_rows(path, sheet)
    body = [r for r in rows[1:] if not _is_placeholder(r[0] if r else None)]
    if not body:
        return CheckResult(f"{sheet} 全天汇总复算", "skipped", "无数据行")
    plan = np.array([[_as_float(v) for v in r[1:145]] for r in body], dtype=float)
    reported_e = np.array([_as_float(r[145] if len(r) > 145 else None) for r in body])
    reported_c = np.array([_as_float(r[146] if len(r) > 146 else None) for r in body])
    calc_e, calc_c = recompute_daily_totals(plan, price)
    if np.all(np.isnan(reported_e)) and np.all(np.isnan(reported_c)):
        return CheckResult(
            f"{sheet} 全天购电量/购电费复算",
            "skipped",
            "模板汇总列为空（尚未填写）",
        )
    de = np.nanmax(np.abs(calc_e - reported_e)) if reported_e.size else math.nan
    dc = np.nanmax(np.abs(calc_c - reported_c)) if reported_c.size else math.nan
    ok = (de <= 1e-4) and (dc <= 1e-3)
    return CheckResult(
        criterion=f"{sheet} 全天购电量/购电费 == 逐时段求和",
        status="passed" if ok else "failed",
        detail=f"max|Δ购电量|={de:.6g}; max|Δ购电费|={dc:.6g}",
        residual=float(max(de, dc)) if not math.isnan(de) and not math.isnan(dc) else None,
    )


def check_soc_bounds(
    groups: Sequence[tuple[date | None, np.ndarray, np.ndarray, float, float]],
) -> CheckResult:
    """校验储能 0:00 / 24:00 储电量落在 ``[1200, 10800]`` 内。

    Args:
        groups: :func:`extract_storage_series` 的返回值。

    Returns:
        校验结果。
    """
    values = [v for _, _, _, a, b in groups for v in (a, b) if not math.isnan(v)]
    if not values:
        return CheckResult("储电量 ∈ [1200, 10800]", "skipped", "未填写储电量")
    arr = np.array(values)
    lo, hi = paths.STORAGE.soc_min_kwh, paths.STORAGE.soc_max_kwh
    n_bad = int(((arr < lo) | (arr > hi)).sum())
    return CheckResult(
        criterion="所有 0:00/24:00 储电量 ∈ [1200, 10800] kWh",
        status="passed" if n_bad == 0 else "failed",
        detail=f"越界 {n_bad}/{arr.size}; 实测范围 [{arr.min():.2f}, {arr.max():.2f}]",
    )


def check_soc_closure(groups: Sequence[tuple[date | None, np.ndarray, np.ndarray, float, float]]) -> CheckResult:
    """校验每组 ``0:00 储电量 == 24:00 储电量``（题目对 0:00 与 24:00 的要求）。

    Args:
        groups: :func:`extract_storage_series` 的返回值。

    Returns:
        校验结果。
    """
    pairs = [(a, b) for _, _, _, a, b in groups if not math.isnan(a) and not math.isnan(b)]
    if not pairs:
        return CheckResult("0:00 储电量 == 24:00 储电量", "skipped", "未填写储电量")
    diffs = np.array([abs(a - b) for a, b in pairs])
    return CheckResult(
        criterion="每组 0:00 储电量 == 24:00 储电量",
        status="passed" if float(diffs.max()) <= ENERGY_TOL else "failed",
        detail=f"最大偏差 {float(diffs.max()):.6g} kWh（{len(pairs)} 组）",
        residual=float(diffs.max()),
    )


def check_daily_soc_continuity(
    groups: Sequence[tuple[date | None, np.ndarray, np.ndarray, float, float]],
) -> CheckResult:
    """校验相邻日之间 24:00 与次日 0:00 储电量衔接（若填写了多日）。

    Args:
        groups: :func:`extract_storage_series` 的返回值。

    Returns:
        校验结果。
    """
    pairs = [(a, b) for _, _, _, a, b in groups if not math.isnan(a) and not math.isnan(b)]
    if len(pairs) < 2:
        return CheckResult("跨日储电量衔接", "skipped", "少于 2 组已填写数据")
    diffs = np.array([abs(pairs[i][1] - pairs[i + 1][0]) for i in range(len(pairs) - 1)])
    return CheckResult(
        criterion="第 d 日 24:00 储电量 == 第 d+1 日 0:00 储电量",
        status="passed" if float(diffs.max()) <= ENERGY_TOL else "failed",
        detail=f"最大偏差 {float(diffs.max()):.6g} kWh（{len(diffs)} 处衔接）",
        residual=float(diffs.max()),
    )


# --------------------------------------------------------------------------- #
# C / D. 物理一致性
# --------------------------------------------------------------------------- #
def check_power_balance(
    plan: np.ndarray,
    load_kw: np.ndarray,
    pv_kw: np.ndarray,
    discharge: np.ndarray,
) -> CheckResult:
    """校验功率平衡残差：``购电 + 放电 >= (负载 - 光伏) * 10/60``。

    题目要求"微网提供的电能不可低于小区负载"；不足部分由紧急购电补齐，
    因此**计划购电量**下该残差允许为正（表示需紧急购电），但不得为负
    （为负意味着计划购电浪费或数据/口径错误）。

    Args:
        plan: 逐时段购电量（kWh）。
        load_kw: 逐时段小区负载（kW）。
        pv_kw: 逐时段光伏实际功率（kW）。
        discharge: 逐时段储能放电量（kWh）。

    Returns:
        校验结果。
    """
    need = np.asarray(load_kw, dtype=float) * paths.INTERVAL_MINUTES / 60.0
    supply = np.asarray(plan, dtype=float) + np.asarray(discharge, dtype=float)
    residual = need - supply
    worst = float(np.nanmax(residual)) if residual.size else math.nan
    return CheckResult(
        criterion="计划购电 + 放电 + 光伏 >= 负载 (kWh/时段)",
        status="passed" if worst <= POWER_BALANCE_TOL else "failed",
        detail=f"最大缺口 {worst:.6f} kWh/时段（>0 表示需紧急购电）",
        residual=worst,
    )


def check_storage_recurrence(
    charge: np.ndarray,
    discharge: np.ndarray,
    soc0: float,
    soc24: float,
    *,
    efficiency: float = 0.9,
) -> CheckResult:
    """校验储能递推闭合：``soc24 == soc0 + eta*Σ充 - Σ放/eta``。

    Args:
        charge: 6 个区块的充电量（kWh，入网侧）。
        discharge: 6 个区块的放电量（kWh，出网侧）。
        soc0: 0:00 储电量。
        soc24: 24:00 储电量。
        efficiency: 充放电效率。

    Returns:
        校验结果。
    """
    if any(math.isnan(v) for v in [*charge.tolist(), *discharge.tolist(), soc0, soc24]):
        return CheckResult("储能递推闭合", "skipped", "存在未填写的充放电或储电量")
    predicted = soc0 + efficiency * float(charge.sum()) - float(discharge.sum()) / efficiency
    residual = abs(predicted - soc24)
    return CheckResult(
        criterion="24:00 储电量 == 0:00 储电量 + 0.9*Σ充电 - Σ放电/0.9",
        status="passed" if residual <= 1e-3 else "failed",
        detail=f"递推值 {predicted:.6f} vs 报告值 {soc24:.6f}（残差 {residual:.6g}）",
        residual=float(residual),
    )


def check_power_limits(charge: np.ndarray, discharge: np.ndarray) -> CheckResult:
    """校验每个 4 小时区块的充放电量不超过功率上限。

    5000 kW × 4 h = 20000 kWh 为 4 小时区块容量上限。

    Args:
        charge: 6 个区块的充电量。
        discharge: 6 个区块的放电量。

    Returns:
        校验结果。
    """
    cap = paths.STORAGE.power_max_kw * 4.0
    vals = np.array([*charge.tolist(), *discharge.tolist()], dtype=float)
    vals = vals[~np.isnan(vals)]
    if vals.size == 0:
        return CheckResult("区块充放电 ≤ 20000 kWh", "skipped", "无数值")
    worst = float(vals.max())
    return CheckResult(
        criterion="每个 4 小时区块 |充/放| <= 20000 kWh",
        status="passed" if worst <= cap + 1e-6 else "failed",
        detail=f"最大值 {worst:.4f} kWh（上限 {cap:.0f}）",
        residual=worst,
    )


# --------------------------------------------------------------------------- #
# 顶层编排
# --------------------------------------------------------------------------- #
def _emit_missing(report: FileReport, reason: str) -> None:
    """为缺失的结果文件写入唯一一条提示项。"""
    report.add(
        CheckResult(
            criterion=f"{report.name}: 文件存在",
            status="missing",
            detail=reason,
        )
    )


def validate_result1(path: Path) -> FileReport:
    """校验 ``result1.xlsx``（问题 1）。

    Args:
        path: 结果文件路径。

    Returns:
        校验报告。
    """
    report = FileReport("result1", path, path.exists())
    if not path.exists():
        _emit_missing(report, f"未找到 {path}；请先运行问题 1 求解脚本生成该文件")
        return report
    report.add(check_sheets(path, ["计划购电量", "充放电量"]))
    report.add(check_plan_sheet(path, "计划购电量", label_mode="row", label_variant="decision"))
    report.add(check_charge_discharge_sheet(path, "充放电量", expect_dates=None))
    groups = extract_storage_series(path, "充放电量")
    report.add(check_soc_bounds(groups))
    report.add(check_soc_closure(groups))
    report.add(check_power_limits(groups[0][1], groups[0][2]) if groups else
               CheckResult("区块充放电 ≤ 20000 kWh", "skipped", "无充放电组"))
    for day, charge, discharge, soc0, soc24 in groups:
        report.add(check_storage_recurrence(charge, discharge, soc0, soc24))
    return report


def validate_planned_file(
    name: str,
    path: Path,
    sheets: Sequence[str],
    price_matrix: np.ndarray | None,
    *,
    has_adjust: bool,
    header_variant: str = "decision",
    verbose: bool = True,
) -> FileReport:
    """校验 ``result2/3/4-2/4-3`` 这类"全年计划购电量"文件。

    Args:
        name: 逻辑名。
        path: 结果文件路径。
        sheets: 期望的工作表名序列。
        price_matrix: 形状 ``(334, 144)`` 的电价矩阵，用于费用复算；``None``
            表示跳过费用复算。**应与该文件对应的电价口径一致**：``result2`` 用
            附件 1 的单日曲线（每天相同），``result4-2`` 用附件 4 的逐日实时电价；
            传入不符口径的电价矩阵会让费用复算失败——这是**真实**比较，
            不得为了"过校验"而放宽。
        has_adjust: 是否包含 ``调整购电量`` 工作表。
        header_variant: ``计划购电量`` / ``调整购电量`` 的表头口径，
            ``"decision"``（**默认，本队基准 = 方案 A**，见
            :data:`PLAN_HEADER_DECISION`）或 ``"template"``（模板原样）。
            问题二契约 §5.5 决议 3 要求本函数以 ``"decision"`` 调用。
        verbose: 为 ``True``（默认）时，对每个已填写的储能组追加储能递推校验项；
            为 ``False`` 时只追加前 5 组（result2/3/4-2/4-3 填满 334 天后
            逐组校验会产生 334 条重复条目，调用方可关闭以保持报告简洁）。
            关闭只影响**报告条数**，不影响其余任何校验项。

    Returns:
        校验报告。
    """
    report = FileReport(name, path, path.exists())
    if not path.exists():
        _emit_missing(report, f"未找到 {path}；请先运行对应问题的求解脚本生成该文件")
        return report
    report.add(check_sheets(path, sheets))
    report.add(check_plan_sheet(path, "计划购电量", label_mode="header",
                                header_variant=header_variant))
    if has_adjust:
        report.add(check_plan_sheet(path, "调整购电量", label_mode="header",
                                    header_variant=header_variant))
    report.add(check_charge_discharge_sheet(path, "充放电量", expect_dates=PLANNED_RESULT_DATES))
    report.add(check_emergency_sheet(path, "紧急购电量"))

    plan = extract_plan_matrix(path, "计划购电量", label_mode="header")
    if plan is not None:
        _, matrix = plan
        report.add(check_non_negative(matrix, what="计划购电量"))
        if price_matrix is not None:
            report.add(check_totals(path, "计划购电量", price_matrix))
    if has_adjust:
        adjust = extract_plan_matrix(path, "调整购电量", label_mode="header")
        if adjust is not None:
            report.add(check_non_negative(adjust[1], what="调整购电量"))
    groups = extract_storage_series(path, "充放电量")
    report.add(check_soc_bounds(groups))
    report.add(check_daily_soc_continuity(groups))
    report.add(check_power_limits(
        np.nan_to_num(np.array([g[1] for g in groups])),
        np.nan_to_num(np.array([g[2] for g in groups])),
    ) if groups else CheckResult("区块充放电 ≤ 20000 kWh", "skipped", "无充放电组"))
    filled = [g for g in groups if not math.isnan(g[3]) or not math.isnan(g[4])]
    if filled:
        selected = filled if verbose else filled[:5]
        for day, charge, discharge, soc0, soc24 in selected:
            result = check_storage_recurrence(charge, discharge, soc0, soc24)
            if not verbose:
                result.criterion = f"{day} 储能递推闭合"
            report.add(result)
    else:
        report.add(CheckResult("储能递推闭合", "skipped", "充放电量表尚未填写（模板仅有示例行）"))
    return report


def validate_all(repo_root: Path | None = None) -> dict[str, Any]:
    """校验全部结果文件，返回可 JSON 序列化的报告。

    文件缺失不会抛异常，只会在报告中标记 ``status="missing"``。

    Args:
        repo_root: 仓库根目录；``None`` 表示使用 :mod:`CUMCM2026_C.common.code.paths` 推导的默认值。

    Returns:
        含 ``files`` / ``summary`` 的报告字典。
    """
    del repo_root  # 路径统一来自 CUMCM2026_C.common.code.paths（其内部已基于 CUMCM2026_C.common.code.paths.ROOT）

    price_matrix: np.ndarray | None = None
    try:
        attachment_4 = io.load_attachment_4()
        index = {d: i for i, d in enumerate(attachment_4.dates)}
        rows = [index[d] for d in PLANNED_RESULT_DATES if d in index]
        if len(rows) == len(PLANNED_RESULT_DATES):
            price_matrix = attachment_4.price[rows]
    except Exception:  # noqa: BLE001 - 附件 4 缺失不应阻断结构校验
        price_matrix = None

    # ``result2`` 的电价口径是**附件 1 的单日曲线**（问题二：每天电价相同），
    # 与附件 4 的逐日实时电价不同；若沿用附件 4 会让"费用复算"比较两个不同口径
    # 而必然失败。因此按文件分别选择电价矩阵（口径不符即为真实失败，不放宽）。
    price_matrix_att1: np.ndarray | None = None
    try:
        att1_price = np.asarray(io.load_attachment_1().price.values, dtype=float)
        if att1_price.size == paths.INTERVALS_PER_DAY:
            price_matrix_att1 = np.tile(att1_price, (len(PLANNED_RESULT_DATES), 1))
    except Exception:  # noqa: BLE001 - 附件 1 缺失不应阻断结构校验
        price_matrix_att1 = None

    reports = [
        validate_result1(paths.result_path("result1")),
        validate_planned_file(
            "result2", paths.result_path("result2"),
            ["计划购电量", "充放电量", "紧急购电量"],
            price_matrix_att1 if price_matrix_att1 is not None else price_matrix,
            has_adjust=False, verbose=False,
        ),
        validate_planned_file(
            "result3", paths.result_path("result3"),
            ["计划购电量", "调整购电量", "充放电量", "紧急购电量"],
            price_matrix, has_adjust=True, verbose=False,
        ),
        validate_planned_file(
            "result4-2", paths.result_path("result4-2"),
            ["计划购电量", "充放电量", "紧急购电量"], price_matrix, has_adjust=False,
            verbose=False,
        ),
        validate_planned_file(
            "result4-3", paths.result_path("result4-3"),
            ["计划购电量", "调整购电量", "充放电量", "紧急购电量"],
            price_matrix, has_adjust=True, verbose=False,
        ),
    ]

    summary: dict[str, int] = {"passed": 0, "failed": 0, "missing": 0, "skipped": 0}
    for report in reports:
        for check in report.checks:
            summary[check.status] = summary.get(check.status, 0) + 1

    return {
        "results_dir": str(paths.RESULTS_DIR),
        "n_files_present": sum(1 for r in reports if r.exists),
        "summary": summary,
        "files": [r.to_dict() for r in reports],
    }


def render_text(report: dict[str, Any]) -> str:
    """把校验报告渲染成可读文本。

    Args:
        report: :func:`validate_all` 的返回值。

    Returns:
        多行字符串。
    """
    lines: list[str] = []
    lines.append("=" * 78)
    lines.append("result*.xlsx 验收校验")
    lines.append(f"结果目录: {report['results_dir']}")
    lines.append(f"已存在文件: {report['n_files_present']}/5")
    summary = report["summary"]
    lines.append(
        f"校验项统计: 通过 {summary.get('passed', 0)} | 失败 {summary.get('failed', 0)} | "
        f"缺失 {summary.get('missing', 0)} | 跳过 {summary.get('skipped', 0)}"
    )
    lines.append("=" * 78)
    for item in report["files"]:
        mark = "OK " if item["exists"] else "MISSING"
        lines.append(f"\n[{mark}] {item['name']}  ({item['path']})")
        for check in item["checks"]:
            symbol = {"passed": "  v", "failed": "  X", "missing": "  -", "skipped": "  ~"}[
                check["status"]
            ]
            lines.append(f"{symbol} {check['criterion']}")
            if check["detail"]:
                lines.append(f"      {check['detail']}")
    return "\n".join(lines)


def main() -> int:
    """命令行入口：校验结果文件并写出报告。

    Returns:
        进程退出码：``0`` 表示无 ``failed`` 项（``missing`` 不算失败），
        ``1`` 表示存在 ``failed`` 项。
    """
    # 控制台编码兜底：Windows 默认 GBK 控制台下，报告文本里的 ``⁻``（U+207B）、
    # ``⇒``（U+21D2）等字符会让 ``print`` 抛 ``UnicodeEncodeError``。
    # ``backslashreplace`` 把不可编码字符写成 ``\\uXXXX``（信息不丢），
    # 不用 ``replace``（会变成 ``?``，若被替换的恰好是数字则输出失真）。
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, ValueError):  # 非 TextIOWrapper（如被重定向为管道）
            pass
    paths.ensure_output_dirs()
    report = validate_all()
    # 先落盘、后打印：打印是本函数的输出，落盘是它的产物。
    # 若把 print 排在前面，任何打印异常都会让结构化报告**根本不生成**——
    # 校验其实已经跑完，却表现为"没跑过"，比打印失败本身严重得多。
    paths.VALIDATION_REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(render_text(report))
    print(f"\n结构化报告写入 {paths.VALIDATION_REPORT}")
    if report["summary"].get("failed", 0) > 0:
        print("存在验收失败的校验项，请修复后重跑。")
        return 1
    if report["n_files_present"] == 0:
        print("提示：results 目录下尚无 result*.xlsx，本轮仅完成结构规格与校验器自检。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
