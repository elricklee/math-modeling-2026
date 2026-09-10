"""附件 1~4（以及附件 5 模板）的加载器与时间轴工具。

时间轴约定（**已实测确认**，详见 ``docs/C题_数据工程与结果规格.md``）
--------------------------------------------------------------------------
1. ``t = 1..144`` 表示一天内的 10 分钟时段，序号即"右端点 / 10 分钟"：

   ``t``  → 区间 ``((t-1)*10 min, t*10 min]`` → 右端点 ``t*10`` 分钟。

2. 附件 1 的 144 行、附件 2 的 144 个时间列、附件 4 的 144 个时间列
   **共用同一套列标签** ``0:10, 0:20, …, 23:50, 0:00+1``，且标签就是右端点。
   末列 ``0:00+1`` 表示次日 0:00（即次日 00:10 时段？——不是：它表示当日 24:00
   这一时刻。实测该列与其"次日首列"并不相等，故只能解释为**当天最后一个
   10 分钟时段的右端点 24:00**）。

   由此得到**唯一正确对齐**：附件 1 第 ``t`` 行（1-based）↔ 附件 2/4 第 ``t`` 列
   （1-based，即 0-based 列号 ``t-1``）。

3. 附件 3 第 ``k`` 列（``预报k小时``）表示"发布时刻 ``r`` 起第 ``k`` 小时"的
   整点瞬时功率功率预报，即时钟 **整点** ``h = r + k``（跨日自动进位）。
   映射到 10 分钟时段序号：``t = 6 * (h mod 24)``（``h mod 24 == 0`` 时指向 24:00）。

   实测：``t = 6h`` 的落点使 MAE 中位数 = 45.68 kW；错位一格（``t = 6h-6``）
   则退化为 238.11 kW，故 ``t = 6h`` 为正确对齐。

单位
----
* 附件 1/2/3 的功率列为 **kW**（10 分钟时段的平均功率），
  ``电量(kWh) = 功率(kW) * 10/60``。
* 附件 1/4 的电价列为 **元/kWh**。
* 附件 5 结果文件中所有电量列均为 **kWh**，电价费用列为 **元**。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Final, Mapping, Sequence
import numpy as np
import openpyxl

from . import paths

# --------------------------------------------------------------------------- #
# 常量
# --------------------------------------------------------------------------- #
ColumnLabel = str
"""时间列标签，如 ``"0:10"`` 或 ``"0:00+1"``。"""

N_TIME_COLUMNS: Final[int] = paths.INTERVALS_PER_DAY
"""10 分钟时段数 = 144。"""

N_FORECAST_HOURS: Final[int] = paths.HOURS_PER_DAY
"""附件 3 每次发布的预报长度 = 24 小时。"""

FORECAST_RELEASE_HOURS: Final[tuple[int, ...]] = (0, 6, 12, 18)
"""附件 3 每天发布预报的 4 个时刻（小时）。"""

EXCEL_EPOCH: Final[date] = date(1899, 12, 30)
"""Excel 1900 日期系统的序列号 0 对应日期（含 1900 闰年 bug 偏置）。"""

_SHEET_LOAD: Final[str] = "小区负载"
_SHEET_PV: Final[str] = "光伏发电实际功率"


# --------------------------------------------------------------------------- #
# 时间轴工具
# --------------------------------------------------------------------------- #
def time_column_labels() -> list[ColumnLabel]:
    """生成 144 个标准时间列标签：``0:10`` … ``23:50``、``0:00+1``。

    Returns:
        长度 144 的标签列表，第 ``t`` 个元素（1-based）对应右端点 ``t*10`` 分钟。
    """
    labels: list[str] = []
    for t in range(1, N_TIME_COLUMNS + 1):
        minute = t * paths.INTERVAL_MINUTES
        if minute >= 24 * 60:
            labels.append("0:00+1")
        else:
            labels.append(f"{minute // 60}:{minute % 60:02d}")
    return labels


TIME_COLUMN_LABELS: Final[list[ColumnLabel]] = time_column_labels()
"""144 个时间列标签（模块级常量，供其他模块复用）。"""


def interval_end_minutes(t: int) -> int:
    """时段序号 → 右端点（自当日 0:00 起的分钟数）。

    Args:
        t: 时段序号，``1..144``。

    Returns:
        右端点分钟数；``t = 144`` 时返回 ``1440``（即次日 0:00）。

    Raises:
        ValueError: ``t`` 不在 ``1..144`` 范围内。
    """
    if not 1 <= t <= N_TIME_COLUMNS:
        raise ValueError(f"时段序号 t 必须在 1..{N_TIME_COLUMNS} 之间，收到 {t}")
    return t * paths.INTERVAL_MINUTES


def interval_start_minutes(t: int) -> int:
    """时段序号 → 左端点（自当日 0:00 起的分钟数）。

    Args:
        t: 时段序号，``1..144``。

    Returns:
        左端点分钟数，``(t-1)*10``。

    Raises:
        ValueError: ``t`` 不在 ``1..144`` 范围内。
    """
    return interval_end_minutes(t) - paths.INTERVAL_MINUTES


def interval_label(t: int) -> str:
    """时段序号 → 结果文件使用的时间段标签，如 ``t=2`` → ``"0:10-0:20"``。

    注意：这正是附件 5 ``result1.xlsx/计划购电量`` 的 A 列标签序列
    （``t = 1`` 对应 ``"0:00-0:10"``，故该表的首行标签是 ``"0:10-0:20"``，
    与 144 行错开一格——见 ``docs`` 中的写入规格）。

    Args:
        t: 时段序号，``1..144``。

    Returns:
        形如 ``"0:10-0:20"`` 的字符串；``t = 144`` 时为 ``"23:50-0:00+1"``。
    """
    end = interval_end_minutes(t)
    start = end - paths.INTERVAL_MINUTES

    def fmt(minute: int, plus_one: bool) -> str:
        if plus_one:
            return "0:00+1"
        return f"{minute // 60}:{minute % 60:02d}"

    start_label = fmt(start, False)
    end_label = fmt(end, end >= 24 * 60)
    return f"{start_label}-{end_label}"


def plan_purchase_labels() -> list[str]:
    """``result2/3/4-*`` 的 ``计划购电量`` 表头所使用的 144 个时间段标签（**规范写法**）。

    模板实测表头序列为 ``0:10-0:20, 0:20-0:30, …, 23:50-0:00+1, 0:00-0:10+1``
    （即 :func:`interval_label` 的结果整体**左移一格**，末位补次日首区间）。

    本函数产出的是**规范化的**标签（``7:00-7:10``），与模板逐字符对照的写盘
    请改用 :func:`plan_purchase_labels_as_template`。

    Returns:
        长度 144 的标签列表。
    """
    labels = [interval_label(t) for t in range(2, N_TIME_COLUMNS + 1)]
    labels.append("0:00-0:10+1")
    return labels


PLAN_TIME_COLUMNS_TEMPLATE: Final[int] = N_TIME_COLUMNS
"""``result2/3/4-*`` ``计划购电量`` 的时间段列数 = 144（表头第 2..145 列，1-based）。"""


def template_column_to_interval(i: int) -> int | None:
    """**【读模板专用】**把 ``计划购电量`` 表头第 ``i`` 个时间段列（1-based）映射为规范区间序号。

    .. important::
       **本函数只用于「读取/解释模板自己的列」，不得用于「写盘」。**
       两个口径各在自身语境下正确，但**禁止混用**（混用会让整表错位一格、静默出错）：

       * **模板原样口径**（本函数，用于读盘/位置校验）：第 ``i`` 个数据位
         **字面描述**的是区间 ``i + 1``；表头沿用模板原样字符串
         （含 ``7:0-7:10`` 笔误）。写盘侧的对应函数是
         :func:`write_plan_columns` 的 ``mode="template"``。
       * **方案 A 口径**（本队数据组织基准，用 :func:`write_plan_columns` 的
         ``mode="decision"``）：第 ``i`` 个数据位装**时段 ``t = i``** 的值，
         标签用 :func:`interval_label`\\ ``(i)``。

       即：**同一个数据位 ``i``，两种口径下的"含义"与"标签"必须成对选择**——
       选"区间 ``i+1``"就配 ``interval_label(i+1)``，选"时段 ``t=i``"就配
       ``interval_label(i)``；不可跨口径拼接。

    **队长裁定 A18（已落地）**：模板时间标签并非"整体位移"，而是
    **缺当日首个区间（``0:00-0:10``）+ 末位换成次日首区间（``0:00-0:10+1``）**。

    Args:
        i: 时间段列序号，``1..144``（对应表头第 ``i + 1`` 列）。

    Returns:
        该列**字面标签**所描述的规范区间序号；
        ``i = 144`` 代表**次日首个区间**（超出当日 144 个区间），返回 ``None``。

    Raises:
        ValueError: ``i`` 不在 ``1..144`` 范围内。
    """
    if not 1 <= i <= PLAN_TIME_COLUMNS_TEMPLATE:
        raise ValueError(
            f"时间段列序号 i 必须在 1..{PLAN_TIME_COLUMNS_TEMPLATE} 之间，收到 {i}"
        )
    return None if i == PLAN_TIME_COLUMNS_TEMPLATE else i + 1


def write_plan_columns(mode: str = "decision") -> list[tuple[int, str]]:
    """**【写盘专用·单一事实来源】**返回宽表 ``(数据位 i, 表头标签)`` 配对。

    队长裁定 A18 要求：**"数据位含义"与"标签函数"必须在同一处同时选定，
    不得分开推断"**。本函数即该唯一入口——调用方只选 ``mode``，
    不允许自行拼接标签。

    .. list-table:: 两种口径（**禁止混用**）
       :header-rows: 1

       * - ``mode``
         - 第 ``i`` 个数据位的含义
         - 表头标签
         - 适用场景
       * - ``"decision"``（默认）
         - 时段 ``t = i``
         - :func:`interval_label`\\ ``(i)`` → ``0:00-0:10 … 23:50-0:00+1``
         - **本队方案 A 基准**（队长裁定 A4）
       * - ``"template"``
         - 区间 ``i + 1``（末位为**次日**首区间）
         - 模板原样字符串（含 ``7:0-7:10`` 笔误）
         - 仅当要求与模板**逐字符一致**时

    读取/解释模板自己的列请改用 :func:`template_column_to_interval`，
    不要用本函数的返回值去反推模板位置。

    Args:
        mode: ``"decision"``（方案 A，默认）或 ``"template"``（原样保留模板口径）。

    Returns:
        长度 144 的 ``(i, label)`` 列表，``i`` 从 1 开始。

    Raises:
        ValueError: ``mode`` 不是上述两个取值之一。

    Example:
        >>> cols = write_plan_columns()
        >>> cols[0]
        (1, '0:00-0:10')
        >>> cols[-1]
        (144, '23:50-0:00+1')
        >>> write_plan_columns("template")[0]
        (1, '0:10-0:20')
    """
    if mode == "decision":
        labels = [interval_label(t) for t in range(1, N_TIME_COLUMNS + 1)]
    elif mode == "template":
        labels = plan_purchase_labels_as_template()
    else:
        raise ValueError(
            f"mode 必须是 'decision' 或 'template'，收到 {mode!r}"
        )
    return list(zip(range(1, N_TIME_COLUMNS + 1), labels))


def describe_write_columns(mode: str = "decision") -> list[dict[str, object]]:
    """**方案 A 版对照输出**（队长 A18 落地要求 3）：写盘前自检用。

    与 :func:`describe_template_plan_columns`（读模板视角）成对使用：
    前者回答"我要写什么"，后者回答"模板里长什么样"。

    Args:
        mode: 同 :func:`write_plan_columns`。

    Returns:
        长度 144 的列表，每项含 ``slot``（数据位 ``i``，
        1-based）、``cell_column``（Excel 列序号 = ``slot + 1``）、
        ``label``（将写入的表头）、``intervals``（该数据位承载的时段列表）、
        ``matches_template_header``（写出的标签是否与模板该列表头逐字符相同）。
    """
    template_labels = plan_purchase_labels_as_template()
    out: list[dict[str, object]] = []
    for slot, label in write_plan_columns(mode):
        intervals = (
            [slot] if mode == "decision"
            else ([slot + 1] if slot < N_TIME_COLUMNS else [])
        )
        out.append(
            {
                "slot": slot,
                "cell_column": slot + 1,
                "label": label,
                "intervals": intervals,
                "matches_template_header": label == template_labels[slot - 1],
            }
        )
    return out


def describe_template_plan_columns() -> list[dict[str, object]]:
    """列出 ``计划购电量`` 144 个时间段列的"表头标签 → 实际区间"对照。

    用于写盘前的自检与文档生成，可避免按位置推断时段序号导致的静默错位。

    Returns:
        长度 144 的列表，每项含 ``column``（时间段列序号 1-based）、
        ``cell_column``（Excel 列序号 = column + 1）、``label``（表头字符串）、
        ``interval``（规范时段序号，``None`` 表示次日首区间）、
        ``canonical_label``（该列应承载的区间标签）。
    """
    labels = plan_purchase_labels_as_template()
    out: list[dict[str, object]] = []
    for column, label in enumerate(labels, start=1):
        interval = template_column_to_interval(column)
        out.append(
            {
                "column": column,
                "cell_column": column + 1,
                "label": label,
                "interval": interval,
                "canonical_label": interval_label(interval) if interval else "0:00-0:10(次日)",
            }
        )
    return out


def result1_row_labels() -> list[str]:
    """**模板原样序列**（队长裁定 R8 未采用，保留供逐字符对照与校验）。

    .. warning::
       此行标签相对附件 1 口径**整体左移一格**，并以"次日首个区间"
       (``0:00+1-0:10+1``) 顶替"当日首个区间"，导致当日的 ``0:00-0:10``
       **没有行位**。队长裁定 **R8 采用附件 1 口径（方案 A）**：
       写 ``result1.xlsx`` 请改用 :func:`result1_row_labels_decision`。

    Returns:
        ``0:10-0:20`` … ``23:50-0:00+1``、``0:00+1-0:10+1``。
    """
    labels = [interval_label(t) for t in range(2, N_TIME_COLUMNS + 1)]
    labels.append("0:00+1-0:10+1")
    return labels


def result1_row_labels_decision() -> list[str]:
    """**队长裁定 R8 采用**的 ``result1.xlsx/计划购电量`` 144 行标签（方案 A）。

    采用**附件 1 口径**：第 ``r`` 行承载时段 ``t = r`` 的购电量，即
    ``0:00-0:10``、``0:10-0:20`` … ``23:50-0:00+1``；等价于附件 1 的 144 个时段。

    裁定理由（队长采纳的三条）：``0:00-0:10`` 是问题 1 中必须优化且必须报送的
    决策量；题目要求"储能设备在 0:00 和 24:00 的储电量相同"并以 0:00 为起点
    制定当天策略，照模板口径会整段丢弃该时段并与储能递推边界冲突；本方案仍为
    144 行，与模板行数一致，仅标签文本修正。

    Returns:
        长度 144 的标签列表，恒等于 ``[interval_label(t) for t in range(1, 145)]``。
    """
    return [interval_label(t) for t in range(1, N_TIME_COLUMNS + 1)]


TEMPLATE_LABEL_QUIRKS: Final[dict[str, str]] = {
    "7:00-7:10": "7:0-7:10",
}
"""附件 5 模板中的已知拼写瑕疵：规范化标签 → 模板实际写法。

目前仅一处：``result2/3/4-*`` 的 ``计划购电量`` / ``调整购电量`` 表头第 43 列
（1-based）把 ``7:00-7:10`` 写成了 ``7:0-7:10``。

**处理建议：写盘时原样保留该瑕疵**（用
:func:`plan_purchase_labels_as_template`），理由是官方校验大概率按模板逐字符
比对；若评审明确要求规范化，可切换回 :func:`plan_purchase_labels`。
"""


def plan_purchase_labels_as_template() -> list[str]:
    """按附件 5 模板的**原始写法**返回 144 个表头标签（含 ``7:0-7:10`` 瑕疵）。

    Returns:
        与 ``result2/3/4-*`` ``计划购电量`` 表头逐字符一致的标签列表。
    """
    return [TEMPLATE_LABEL_QUIRKS.get(label, label) for label in plan_purchase_labels()]


def template_label_quirks_in(labels: Sequence[str]) -> dict[int, tuple[str, str]]:
    """列出给定标签序列中命中模板瑕疵的位置。

    Args:
        labels: 待检查的标签序列。

    Returns:
        ``{1-based 列号: (实测写法, 规范写法)}``。
    """
    reverse = {quirky: canonical for canonical, quirky in TEMPLATE_LABEL_QUIRKS.items()}
    hits: dict[int, tuple[str, str]] = {}
    for index, label in enumerate(labels, start=1):
        if label in reverse:
            hits[index] = (label, reverse[label])
    return hits


def half_hour_block_labels() -> list[str]:
    """``充放电量`` 表的 6 个 4 小时时段标签。

    Returns:
        ``0:00-4:00`` … ``20:00-24:00``。
    """
    return [f"{h}:00-{h + 4}:00" for h in range(0, 24, 4)]


def excel_serial_to_date(serial: float | int) -> date:
    """Excel 日期序列号 → ``datetime.date``。

    Args:
        serial: Excel 序列号（附件 2/4 首列为 45658…46022）。

    Returns:
        对应日期。
    """
    return EXCEL_EPOCH + timedelta(days=int(round(float(serial))))


def coerce_date(value: object) -> date | None:
    """把单元格值宽松地转成 ``datetime.date``。

    支持 ``datetime`` / ``date`` / Excel 序列号 / ``2025-1-1``、``2025/1/1``
    字符串；空值返回 ``None``。

    Args:
        value: 原始单元格值。

    Returns:
        日期或 ``None``。
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (int, float)):
        return excel_serial_to_date(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("-", "/")
    parts = text.split("/")
    if len(parts) == 3:
        try:
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError:
            return None
    return None


def coerce_hour(value: object) -> int | None:
    """把附件 3 ``预报时刻`` 列的值转成小时整数。

    支持 ``datetime.time(6, 0)``、``"6:00"``、Excel 时间序列号 ``0.25``。

    Args:
        value: 原始单元格值。

    Returns:
        ``0..23`` 的小时数；无法解析返回 ``None``。
    """
    if value is None:
        return None
    if isinstance(value, (time, datetime)):
        return value.hour
    if isinstance(value, (int, float)):
        fraction = float(value)
        if 0.0 <= fraction < 1.0:
            return int(round(fraction * 24)) % 24
        return int(fraction) % 24
    text = str(value).strip()
    if not text:
        return None
    head = text.split(":")[0]
    if head.isdigit():
        return int(head) % 24
    return None


def forecast_hour_to_interval(hour: int) -> int:
    """附件 3 预报的**整点小时** → 10 分钟时段序号 ``t``。

    ``h = 0`` 表示当天 24:00，实测应落在末列（``t = 144``）；其余 ``h`` 落在
    ``t = 6h``。

    Args:
        hour: 整点，``0..23``。

    Returns:
        时段序号 ``1..144``。
    """
    normalized = hour % 24
    return N_TIME_COLUMNS if normalized == 0 else 6 * normalized


def forecast_target(
    release_day: date, release_hour: int, horizon: int
) -> tuple[date, int]:
    """把 (发布日, 发布时刻, 预报 k 小时) 解析为 (生效日, 时段序号 ``t``)。

    Args:
        release_day: 发布日。
        release_hour: 发布时刻（``0/6/12/18``）。
        horizon: 预报 horizon ``k``，``1..24``。

    Returns:
        ``(生效日期, 时段序号 t)``；``t`` 为该生效日内的 10 分钟时段序号。
        ``h = release_hour + k`` 恰为 24 的整数倍时，生效日为次日，``t = 144``。
    """
    absolute_hour = release_hour + horizon
    target_day = release_day + timedelta(days=absolute_hour // 24)
    return target_day, forecast_hour_to_interval(absolute_hour % 24)


# --------------------------------------------------------------------------- #
# 数据容器
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class DaySeries:
    """单日 144 个 10 分钟时段的序列（附件 1）。

    Attributes:
        intervals: 时段序号 ``1..144``。
        values: 长度 144 的数组。
        unit: 单位字符串。
        name: 中文列名。
    """

    intervals: np.ndarray
    values: np.ndarray
    unit: str
    name: str

    def __len__(self) -> int:
        """返回时段数（恒为 144）。"""
        return int(self.values.size)


@dataclass(frozen=True)
class Attachment1:
    """附件 1：某天的电价 / 小区负载 / 光伏发电预测功率。

    Attributes:
        price: 电价序列（元/kWh）。
        load: 小区负载序列（kW）。
        pv_forecast: 光伏发电预测功率序列（kW）。
    """

    price: DaySeries
    load: DaySeries
    pv_forecast: DaySeries

    @property
    def n_intervals(self) -> int:
        """时段数（144）。"""
        return len(self.price)


@dataclass(frozen=True)
class Attachment2:
    """附件 2：2025 全年 10 分钟粒度的小区负载与光伏发电实际功率。

    Attributes:
        dates: 365 个日期，按时间升序。
        intervals: 时段序号 ``1..144``。
        load: 形状 ``(365, 144)`` 的小区负载（kW）。
        pv_actual: 形状 ``(365, 144)`` 的光伏实际功率（kW）。
    """

    dates: list[date]
    intervals: np.ndarray
    load: np.ndarray
    pv_actual: np.ndarray

    def row_index(self, day: date) -> int:
        """返回某日在矩阵中的行下标。

        Args:
            day: 目标日期。

        Returns:
            行下标 ``0..364``。

        Raises:
            KeyError: 日期不在附件 2 覆盖范围内。
        """
        try:
            return self.dates.index(day)
        except ValueError as exc:
            raise KeyError(f"{day} 不在附件 2 覆盖范围（2025-01-01..2025-12-31）内") from exc


@dataclass(frozen=True)
class Attachment3:
    """附件 3：2025 全年每天 4 个时刻发布的未来 24 小时整点光伏预报。

    Attributes:
        release_days: 长度 1460 的发布日列表。
        release_hours: 长度 1460 的发布小时列表（``0/6/12/18``）。
        forecast: 形状 ``(1460, 24)`` 的光伏功率预报（kW），列 ``k-1`` 为
            ``预报k小时``。
    """

    release_days: list[date]
    release_hours: np.ndarray
    forecast: np.ndarray

    def row_index(self, day: date, hour: int) -> int:
        """返回 (发布日, 发布时刻) 对应的行下标。

        Args:
            day: 发布日。
            hour: 发布小时（``0/6/12/18``）。

        Returns:
            行下标。

        Raises:
            KeyError: 组合不存在。
        """
        for i, (d, h) in enumerate(zip(self.release_days, self.release_hours.tolist())):
            if d == day and h == hour:
                return i
        raise KeyError(f"附件 3 中不存在发布日 {day} / 发布时刻 {hour}:00 的记录")


@dataclass(frozen=True)
class Attachment4:
    """附件 4：2025 全年 10 分钟粒度实时电价。

    Attributes:
        dates: 365 个日期，按时间升序。
        intervals: 时段序号 ``1..144``。
        price: 形状 ``(365, 144)`` 的电价（元/kWh）。
    """

    dates: list[date]
    intervals: np.ndarray
    price: np.ndarray

    def row_index(self, day: date) -> int:
        """返回某日在矩阵中的行下标。

        Args:
            day: 目标日期。

        Returns:
            行下标。

        Raises:
            KeyError: 日期不在覆盖范围内。
        """
        try:
            return self.dates.index(day)
        except ValueError as exc:
            raise KeyError(f"{day} 不在附件 4 覆盖范围（2025-01-01..2025-12-31）内") from exc


# --------------------------------------------------------------------------- #
# 底层读取工具
# --------------------------------------------------------------------------- #
def _sheet_rows(path: Path, sheet: str | None = None) -> list[list[object]]:
    """按行读入工作表全部单元格值。

    Args:
        path: xlsx 路径。
        sheet: 工作表名；``None`` 表示第一个工作表。

    Returns:
        行列表，每行为单元格值列表。
    """
    workbook = openpyxl.load_workbook(path, data_only=True, read_only=False)
    try:
        worksheet = workbook[sheet] if sheet else workbook[workbook.sheetnames[0]]
        return [list(row) for row in worksheet.iter_rows(values_only=True)]
    finally:
        workbook.close()


def _to_float(value: object) -> float:
    """单元格值 → ``float``；空值转为 ``nan`` 以便统计缺失。

    Args:
        value: 原始单元格值。

    Returns:
        浮点值，缺失为 ``nan``。
    """
    if value is None:
        return float("nan")
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return float("nan")
    try:
        return float(text)
    except ValueError:
        return float("nan")


def _read_wide_matrix(
    path: Path, sheet: str
) -> tuple[list[date], list[int], np.ndarray, list[ColumnLabel]]:
    """读取附件 2 / 附件 4 的 365x145 宽表。

    Args:
        path: xlsx 路径。
        sheet: 工作表名。

    Returns:
        ``(dates, intervals, matrix, labels)``，``matrix`` 形状 ``(n_days, 144)``。
    """
    rows = _sheet_rows(path, sheet)
    header = rows[0]
    labels = ["" if h is None else str(h).strip() for h in header[1:]]
    dates: list[date] = []
    data: list[list[float]] = []
    for row in rows[1:]:
        day = coerce_date(row[0] if row else None)
        if day is None:
            continue
        dates.append(day)
        data.append([_to_float(v) for v in row[1 : 1 + N_TIME_COLUMNS]])
    matrix = np.array(data, dtype=float)
    intervals = np.arange(1, N_TIME_COLUMNS + 1)
    return dates, list(intervals), matrix, labels


# --------------------------------------------------------------------------- #
# 附件加载
# --------------------------------------------------------------------------- #
def load_attachment_1(path: Path | None = None) -> Attachment1:
    """加载附件 1。

    Args:
        path: 附件 1 路径，默认 :data:`paths.ATTACHMENT_1`。

    Returns:
        解析后的 :class:`Attachment1`。
    """
    rows = _sheet_rows(path or paths.ATTACHMENT_1)
    intervals, price, load, pv = [], [], [], []
    for row in rows[1:]:
        intervals.append(len(intervals) + 1)
        price.append(_to_float(row[1]))
        load.append(_to_float(row[2]))
        pv.append(_to_float(row[3]))
    order = np.argsort(intervals)
    return Attachment1(
        price=DaySeries(np.array(intervals)[order], np.array(price)[order], "元/kWh", "电价"),
        load=DaySeries(np.array(intervals)[order], np.array(load)[order], "kW", "小区负载"),
        pv_forecast=DaySeries(np.array(intervals)[order], np.array(pv)[order], "kW", "光伏发电预测功率"),
    )


def load_attachment_2(path: Path | None = None) -> Attachment2:
    """加载附件 2（小区负载 + 光伏发电实际功率）。

    Args:
        path: 附件 2 路径，默认 :data:`paths.ATTACHMENT_2`。

    Returns:
        解析后的 :class:`Attachment2`。
    """
    target = path or paths.ATTACHMENT_2
    dates_load, intervals, load, _ = _read_wide_matrix(target, _SHEET_LOAD)
    dates_pv, _, pv, _ = _read_wide_matrix(target, _SHEET_PV)
    if dates_load != dates_pv:
        raise ValueError("附件 2 两个工作表的日期列不一致")
    return Attachment2(dates_load, np.array(intervals), load, pv)


def load_attachment_3(path: Path | None = None) -> Attachment3:
    """加载附件 3（4 个时刻发布的 24 小时整点光伏预报）。

    首列日期为"合并单元格"式留空，这里用前向填充还原。

    Args:
        path: 附件 3 路径，默认 :data:`paths.ATTACHMENT_3`。

    Returns:
        解析后的 :class:`Attachment3`。
    """
    rows = _sheet_rows(path or paths.ATTACHMENT_3)
    days: list[date] = []
    hours: list[int] = []
    forecast: list[list[float]] = []
    current: date | None = None
    for row in rows[1:]:
        day = coerce_date(row[0] if row else None)
        if day is not None:
            current = day
        hour = coerce_hour(row[1] if len(row) > 1 else None)
        if current is None or hour is None:
            continue
        days.append(current)
        hours.append(hour)
        forecast.append([_to_float(v) for v in row[2 : 2 + N_FORECAST_HOURS]])
    return Attachment3(days, np.array(hours, dtype=int),
                       np.array(forecast, dtype=float))


def load_attachment_4(path: Path | None = None) -> Attachment4:
    """加载附件 4（2025 全年 10 分钟粒度实时电价）。

    Args:
        path: 附件 4 路径，默认 :data:`paths.ATTACHMENT_4`。

    Returns:
        解析后的 :class:`Attachment4`。
    """
    dates, intervals, price, _ = _read_wide_matrix(path or paths.ATTACHMENT_4, "Sheet1")
    return Attachment4(dates, np.array(intervals), price)


def load_all() -> tuple[Attachment1, Attachment2, Attachment3, Attachment4]:
    """一次性加载附件 1~4。

    Returns:
        ``(附件1, 附件2, 附件3, 附件4)``。
    """
    return (
        load_attachment_1(),
        load_attachment_2(),
        load_attachment_3(),
        load_attachment_4(),
    )


# --------------------------------------------------------------------------- #
# 派生量
# --------------------------------------------------------------------------- #
def interval_power_to_energy(power_kw: np.ndarray) -> np.ndarray:
    """10 分钟时段的平均功率（kW）→ 该时段电量（kWh）。

    ``E = P * 10/60 = P / 6``。

    Args:
        power_kw: 功率数组。

    Returns:
        电量数组，与输入同形状。
    """
    return np.asarray(power_kw, dtype=float) * paths.INTERVAL_MINUTES / 60.0


def block_energy_from_intervals(energy: np.ndarray, block: int) -> np.ndarray:
    """把 144 个时段电量聚合为 6 个 4 小时区块（``充放电量`` 表用）。

    Args:
        energy: 长度 144 的时段电量数组。
        block: 区块下标 ``1..6``。

    Returns:
        区块 ``block`` 内的电量之和。
    """
    if not 1 <= block <= 6:
        raise ValueError(f"区块下标必须在 1..6 之间，收到 {block}")
    start = (block - 1) * 24
    return float(np.asarray(energy, dtype=float)[start : start + 24].sum())


def intervals_in_half_hour(hour: int) -> slice:
    """返回某个整点小时对应的 6 个时段在 0-based 数组中的切片。

    ``hour = h``（``0..23``）对应时段数组下标 ``6h .. 6h+5``。

    Args:
        hour: 整点，``0..23``。

    Returns:
        0-based 切片对象。
    """
    if not 0 <= hour <= 23:
        raise ValueError(f"小时必须在 0..23 之间，收到 {hour}")
    return slice(6 * hour, 6 * hour + 6)


def price_vector_from_attachment_4(attachment_4: Attachment4, day: date) -> np.ndarray:
    """取附件 4 中某日的 144 维实时电价向量。

    Args:
        attachment_4: 附件 4 数据。
        day: 目标日期。

    Returns:
        长度 144 的电价向量（元/kWh）。

    Raises:
        KeyError: 日期不在附件 4 覆盖范围内。
    """
    return np.array(attachment_4.price[attachment_4.row_index(day)], dtype=float)


def as_mapping(series: DaySeries) -> Mapping[int, float]:
    """把 :class:`DaySeries` 转为 ``{时段序号: 数值}`` 映射，便于打印摘要。

    Args:
        series: 单日序列。

    Returns:
        时段序号到数值的映射。
    """
    return {int(t): float(v) for t, v in zip(series.intervals, series.values)}


__all__ = [
    "FORECAST_RELEASE_HOURS",
    "N_FORECAST_HOURS",
    "N_TIME_COLUMNS",
    "TIME_COLUMN_LABELS",
    "TEMPLATE_LABEL_QUIRKS",
    "Attachment1",
    "Attachment2",
    "Attachment3",
    "Attachment4",
    "ColumnLabel",
    "DaySeries",
    "as_mapping",
    "block_energy_from_intervals",
    "coerce_date",
    "coerce_hour",
    "excel_serial_to_date",
    "forecast_hour_to_interval",
    "forecast_target",
    "half_hour_block_labels",
    "interval_end_minutes",
    "interval_label",
    "interval_power_to_energy",
    "interval_start_minutes",
    "intervals_in_half_hour",
    "load_all",
    "load_attachment_1",
    "load_attachment_2",
    "load_attachment_3",
    "load_attachment_4",
    "plan_purchase_labels",
    "plan_purchase_labels_as_template",
    "price_vector_from_attachment_4",
    "result1_row_labels",
    "result1_row_labels_decision",
    "write_plan_columns",
    "describe_write_columns",
    "template_column_to_interval",
    "template_label_quirks_in",
    "describe_template_plan_columns",
    "PLAN_TIME_COLUMNS_TEMPLATE",
    "time_column_labels",
]
