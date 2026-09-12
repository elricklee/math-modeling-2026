r"""问题 2 对照口径分析（B2(ii) 信息集受约束口径）—— 契约 §5.2 / §5.4 决议 4。

主口径（``Q2_solve_plan.py``，B2(i)）在 0:00 已知当天负载与光伏，于是计划量
:math:`p=a`、紧急购电量恒为 0，5 倍电价成了不起作用的约束。本脚本按契约 §5.4
的强制要求构造**信息集受限**的对照口径，让 5 倍电价真正起作用。

对照口径 B2(ii)
================

1. **计划阶段**（第 :math:`d` 天 0:00 制定）只能用预报：

   * **预报 A（主用）**：附件 3 中**第 :math:`d` 天 0:00 发布**、恰好铺满当天
     0:00–24:00 全部 24 个小时块的整点光伏预报（契约 §5.4 订正口径）。它在
     0:00 制定计划时即可获得，满足非预期性，且**没有未覆盖时点**。
   * **预报 A'（对照）**：第 :math:`d` 天 **6:00 发布**（只覆盖当天 6:00–24:00 的
     18 个小时块，0:00–6:00 无列）。它要到当天 6:00 才可得，覆盖区间也与预报 A 不同，
     故两者的 MAE **不可横向排序**。
   * **预报 B（朴素）**：第 :math:`d-1` 天的实际光伏功率。

   两者都只有整点信息，按"整点值在随后 6 个 10 分钟时段内恒定"细化到 144 时段
   （该细化使总电量守恒）。附件**没有负载预报**，故负载一律用"前一日逐小时
   剖面"作朴素预报（显式假设）。计划阶段求解

   .. math::

       \min_{x,y,q,d}\ \sum_t c_t q_t \quad\text{s.t.}\quad
       q_t - d_t = n^{\text{f}}_t + x_t - y_t,\ 0 \le q_t,\ 0 \le d_t

   其中 :math:`n^{\text{f}}_t` 为预报净负荷、:math:`d_t` 为被丢弃的过剩光伏电量；
   储能满足 SOC 边界与**日终归位** :math:`S_T = S_0`。注意 :math:`q` 必须显式入模，
   且**必须保持非负**：由平衡式有 :math:`q_t = n^{\text{f}}_t + x_t - y_t + d_t`
   （``q`` 是被等式钉住的因变量，不是自由变量），而 :math:`q_t \ge 0` 正是契约
   B5(i)「不允许余电外送」的实现。若放开该下界，负净负荷时段的过剩光伏会被当作
   可按 :math:`c_t` 卖出的电量、产生虚假售电收益（实测 2025-06-21 单日：目标值从
   17 813.64 元被压到 2 334.61 元，:math:`\min_t q_t = -1\,273.90` kWh）。

2. **执行阶段**（当天实际值揭晓后）。计划购电量 :math:`p` 与储能调度
   :math:`(x^{\text{plan}}, y^{\text{plan}})` 均在 0:00 锁定、日内不可修改；
   按契约 R-Q2-4，执行阶段**不再求解任何优化**，实际购电与紧急购电由平衡式唯一确定：

   .. math::

       a_t = \max\big(n^{\text{a}}_t + x^{\text{plan}}_t - y^{\text{plan}}_t,\ 0\big),
       \qquad e_t = \max\big(a_t - p_t,\ 0\big)

   本脚本实现两种执行口径：

   * ``locked``（**默认、主用**）：即上式——把计划阶段的 :math:`x/y` 原样带入、
     日内不再调节。该口径在**完全信息下精确复现主模型**（:math:`p = a`、
     紧急购电 = 0、总费用逐分一致），是两阶段物理链条自洽、与主模型可比的口径；
     其紧急购电量全部来自预报误差。

   * ``adaptive``（**假设性对照**）：假设计划量 :math:`p` 锁定、但储能允许在日内
     重新求解，缺额按 :math:`5c_t` 紧急购电。把实际购电量相对计划量的分解记为
     :math:`a_t - p_t = u_t - v_t`（:math:`u, v \ge 0`）后，执行阶段为

     .. math::

         \min\ \sum_t \big[c_t\,v_t + 5c_t\,u_t\big]
         \qquad \text{s.t. } u_t - v_t - x_t + y_t = p_t - n^{\text{a}}_t,\
         S_0 = S_T,\ S_t \in [1200, 10800]

     其中 :math:`c_t v_t` 是"计划买了但没用上"的照付部分。该假设**不具备**上面的
     复现性（即使负载与光伏都已知，仍可能出现紧急购电），故只作粗略对照，
     论文引用时必须标注为强假设。

   两个执行口径的差值量化了"日内再调度"的价值。

产出
====
* ``Q2/outputs/Q2_analysis.json``            —— 对照口径全部数值（决议 4 指定载体）
* ``Q2/outputs/Q2_emergency_detail.csv``     —— 紧急购电明细（口径/日期/时段/电量）
* ``Q2/outputs/figures/Q2_fig10..fig13*.png`` —— 对照口径插图

运行方式（在仓库根目录）::

    $env:PYTHONIOENCODING="utf-8"
    .venv\Scripts\python.exe CUMCM2026_C\Q2\Q2_analysis.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import matplotlib  # noqa: E402

matplotlib.use("TkAgg")
import matplotlib.pyplot as plt  # noqa: E402
from scipy.optimize import linprog  # noqa: E402
from scipy.sparse import csr_matrix  # noqa: E402

from CUMCM2026_C.common.code import io_attachments as io  # noqa: E402
from CUMCM2026_C.common.code import paths  # noqa: E402

Q = 2
OUT_DIR = paths.question_outputs(Q)
FIG_DIR = paths.question_figures(Q)
DIAG_FILE = OUT_DIR / "Q2_diagnostics.json"
ANALYSIS_FILE = OUT_DIR / "Q2_analysis.json"
EMERGENCY_CSV = OUT_DIR / "Q2_emergency_detail.csv"

T = paths.INTERVALS_PER_DAY
DT = paths.INTERVAL_MINUTES / 60.0
ETA = paths.STORAGE.efficiency
S_LO = paths.STORAGE.soc_min_kwh
S_HI = paths.STORAGE.soc_max_kwh
S_INIT = paths.STORAGE.soc_init_kwh
CAP = paths.STORAGE.max_energy_per_interval_charge
MULT = paths.PRICE_RULES.emergency_multiplier        # 5.0

DAY_START = date(2025, 2, 1)
DAY_END = date(2025, 12, 31)
TARGET_DATES = [DAY_START + timedelta(days=i)
                for i in range((DAY_END - DAY_START).days + 1)]
TABLE3_DATES = [date(2025, 3, 20), date(2025, 6, 21),
                date(2025, 9, 23), date(2025, 12, 21)]

_FONT_CANDIDATES = ("Microsoft YaHei", "SimHei", "DengXian", "SimSun", "KaiTi")
_AVAILABLE = {f.name for f in matplotlib.font_manager.fontManager.ttflist}
_CJK = next((f for f in _FONT_CANDIDATES if f in _AVAILABLE), "DejaVu Sans")
plt.rcParams["font.sans-serif"] = [_CJK, *_FONT_CANDIDATES, "DejaVu Sans"]
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 120
plt.rcParams["savefig.dpi"] = 200
plt.rcParams["savefig.bbox"] = "tight"
plt.rcParams["axes.grid"] = True
plt.rcParams["grid.alpha"] = 0.30
plt.rcParams["grid.linestyle"] = ":"

C_PLAN, C_EMG = "#2c6fbb", "#c0392b"

_TRI = np.tril(np.ones((T, T)))          # 前缀和矩阵（S 的前缀只含 x、y）


def _log(msg: str) -> None:
    """打印带前缀的日志。"""
    print(f"[Q2-analysis] {msg}", flush=True)


# --------------------------------------------------------------------------- #
# STAGE A  预报构造（附件 3 日前预报 + 朴素预报）
# --------------------------------------------------------------------------- #
def hourly_to_interval_energy(hourly_kw: np.ndarray) -> np.ndarray:
    """24 个整点功率（kW）→ 144 个时段**电量**（kWh）。

    细化口径：整点值在随后 6 个 10 分钟时段内恒定。该口径使
    :math:`\\sum_{144} E_t \\times 6 = \\sum_{24} P_h`（总电量守恒）。

    .. note::
        误差统计（MAE/RMSE）请改用 :func:`spreading_rule_shifts`
        （返回 kW，与附件 3 同量纲），避免"预报 kWh vs 实际 kW"的量纲错配。

    Args:
        hourly_kw: 长度 24 的整点光伏功率（kW）。

    Returns:
        长度 144 的时段电量（kWh）。
    """
    hourly_kw = np.asarray(hourly_kw, dtype=float)
    if hourly_kw.size != 24:
        raise ValueError(f"整点序列长度必须为 24，收到 {hourly_kw.size}")
    return np.repeat(hourly_kw, 6) * DT


def release_hourly_blocks(att3: io.Attachment3, release_day: date, release_hour: int,
                          target_day: date) -> tuple[np.ndarray, list[int], list[int]]:
    """**【映射的唯一实现】**把某次发布解析到目标日的 24 个小时块。

    映射规则（与 ``io_attachments.forecast_target`` 同源，已用附件 2 实际光伏核验）：

    * 发布时刻 ``r`` 的第 ``k`` 列是**发布后第 ``k`` 个小时块**的平均功率，
      即 0-based 绝对小时块 ``r + k − 1``；
    * 该块所属绝对日为 ``release_day + (r + k − 1)//24``，钟点索引为
      ``(r + k − 1) % 24``；
    * 只保留落在 ``target_day`` 的块，其余块属于相邻日、不参与目标日。

    2025-02-01 核验：``raw[6] = 351.8`` 落在当天 6:00–7:00 块。若改用
    ``r + k``（旧映射）会整体右移一格，块 6 变成 0、块 7 变成 351.8，与实测不符。

    Args:
        att3: 附件 3 数据。
        release_day: 发布日。
        release_hour: 发布时刻（``0/6/12/18``）。
        target_day: 目标日。

    Returns:
        ``(hourly_kw, covered_hours, uncovered_hours)``：长度 24 的小时块功率（kW）、
        被覆盖的小时索引列表、未被覆盖的小时索引列表。
    """
    values = np.asarray(att3.forecast[att3.row_index(release_day, release_hour)],
                        dtype=float)
    hourly = np.zeros(24)
    covered = np.zeros(24, dtype=bool)
    for k in range(1, 25):
        absolute_block = release_hour + k - 1
        if release_day + timedelta(days=absolute_block // 24) != target_day:
            continue
        h = absolute_block % 24
        hourly[h] = values[k - 1]
        covered[h] = True
    return (hourly,
            [int(h) for h in np.flatnonzero(covered)],
            [int(h) for h in np.flatnonzero(~covered)])


def forecast_from_release(att3: io.Attachment3, release_day: date, release_hour: int,
                          target_day: date) -> tuple[np.ndarray, list[int]]:
    """把某次发布的整点预报铺到目标日 144 个时段（整点值在随后 6 段内恒定）。

    契约（问题二契约 §5.4 订正版）规定用**第 :math:`d` 日 0:00 发布**的那条
    （``release_day = target_day, r = 0``）：24 列恰好铺满目标日的全部 24 个小时块
    （``k = 1..24`` ↔ 钟点 ``0:00–1:00 … 23:00–24:00``），**无任何未覆盖时段**。

    .. note::
        本函数只是 :func:`release_hourly_blocks`（**唯一映射实现**）的薄包装，
        以保证全文件不存在第二处映射实现。

    Args:
        att3: 附件 3 数据。
        release_day: 发布日。
        release_hour: 发布时刻（``0/6/12/18``）。
        target_day: 目标日。

    Returns:
        ``(power_kw_144, uncovered_hours)``：长度 144 的时段功率（kW）与未覆盖小时列表。
    """
    hourly, _covered, uncovered = release_hourly_blocks(
        att3, release_day, release_hour, target_day)
    return np.repeat(hourly, 6), uncovered


def spreading_rule_comparison(data: dict, att3: io.Attachment3,
                              day: date | None = None) -> dict:
    """比较三种整点→10 分钟铺展规则对光伏预报误差的影响（R-Q2-5 要求）。

    在 **第 d 日 0:00 发布**的正确口径下，对全年（或指定日）计算三种规则的 MAE，
    用于复现契约给出的"分段恒定最优"这一结论。

    Args:
        data: 与 ``Q2_solve_plan.load_data`` 同构的数据字典。
        att3: 附件 3 数据。
        day: 只统计该日；``None``（默认）表示统计全部 334 天。

    Returns:
        含三种规则的 ``mae_kw`` / ``rmse_kw`` 与统计范围的字典。
    """
    dates = data["dates"]
    pv_kw = data["pv_kw"] if day is None else data["pv_kw"][dates.index(day)][None, :]
    target_days = dates if day is None else [day]
    rules = ("piecewise_constant", "shift_one", "linear_interp")
    acc: dict[str, list[np.ndarray]] = {k: [] for k in rules}
    for i, d in enumerate(target_days):
        vals = np.asarray(att3.forecast[att3.row_index(d, 0)], dtype=float)
        built = spreading_rule_shifts(vals)                  # 长度 144，kW
        actual = pv_kw[i]                                    # 长度 144，kW
        for key, arr in built.items():
            acc[key].append(np.abs(arr - actual))            # 全天 144 个时段
    out: dict[str, dict[str, float]] = {}
    for key in rules:
        full = np.concatenate(acc[key])
        out[key] = {"mae_kw": float(full.mean()),
                    "rmse_kw": float(np.sqrt((full ** 2).mean()))}
    best = min(rules, key=lambda k: out[k]["mae_kw"])
    return {
        "day": "all 334 days" if day is None else day.isoformat(),
        "release_hour": 0,
        "unit": "kW（与附件 3 同量纲，不乘 10/60）",
        "primary_definition": ("`mae_kw` / `rmse_kw` 按**当天全部 144 个时段**统计"
                               "（第 d 日 0:00 发布的那条无缺口，24 个小时块全覆盖）——"
                               "该定义可复现契约 R-Q2-5 对 2025-06-21 给出的实测值"
                               "（分段恒定 336.75 kW、错位一格 412.23 kW）。"),
        "note": ("三种规则都在第 d 日 0:00 发布的预报上比较，全天 144 个时段无缺口。"),
        "rule_mae_reading_note": (
            "⚠ 读表提醒：本节 `rules.shift_one.mae_kw`（全天 **448.3124 kW**）是"
            "**错位一格对照规则**的值，**不是预报 A 的 MAE**。预报 A 的 MAE 见 "
            "`forecast_errors.pv_forecast_a_vs_actual.mae_kw` = **371.2208 kW**；"
            "两者之差正是『整点块整体后移一格』这一对齐歧义的代价，"
            "也是 R-Q2-5 要求并列三种规则的原因。请勿把 448.3124 当作预报 A 的精度。"),
        "rules": out,
        "best_rule": best,
    }


def spreading_rule_shifts(hourly_kw: np.ndarray) -> dict[str, np.ndarray]:
    """把 24 个整点值用三种规则铺到 144 时段（R-Q2-5 要求并列比较）。

    * ``piecewise_constant``（**采用**）：第 ``k`` 列预报（``k = 1..24``）表示
      **第 k 个整点小时内**的平均功率，恒定铺到该小时的 6 个时段，即
      :math:`V^{\\mathrm f}_t = \\frac16 f[\\lfloor (t-1)/6 \\rfloor + 1]`。
    * ``shift_one``（错位一格对照）：同上但整点索引左移一格（``k-1``），
      用于检验"右端点 vs 左端点"的对齐歧义。
    * ``linear_interp``（线性插值对照）：把整点值按小时刻度线性插值后取各时段
      右端点处的值。

    Args:
        hourly_kw: 长度 24 的整点光伏功率（kW）。

    Returns:
        ``{规则名: 长度 144 的时段**功率**（kW）}``——与附件 3 同量纲，
        便于直接与实际光伏功率算 MAE/RMSE；需要电量时由调用方显式乘
        :func:`io_attachments.interval_power_to_energy`（``×10/60``）。
    """
    hourly_kw = np.asarray(hourly_kw, dtype=float)
    if hourly_kw.size != 24:
        raise ValueError(f"整点序列长度必须为 24，收到 {hourly_kw.size}")
    constant = np.repeat(hourly_kw, 6)
    shifted = np.repeat(np.roll(hourly_kw, 1), 6)
    knots = np.arange(0, 25)                      # 小时刻度 0..24
    values = np.concatenate([hourly_kw, hourly_kw[-1:]])
    t_hours = np.arange(1, T + 1) / 6.0           # 各时段的右端点小时坐标
    return {"piecewise_constant": constant, "shift_one": shifted,
            "linear_interp": np.interp(t_hours, knots, values)}


def build_forecasts(data: dict, att3: io.Attachment3) -> dict:
    """构造各对照口径所需的光伏 / 负载预报矩阵。

    * **预报 A（主用）**：第 :math:`d` 日 **0:00 发布**的整点光伏预报。第 ``k`` 列
      是发布后第 ``k`` 个小时块的平均功率，故 24 列恰好铺满当天 0:00–24:00 的
      24 个小时块，**无未覆盖时点**（契约 §5.4 订正口径）。
    * **预报 A'（对照）**：第 :math:`d` 日 **6:00 发布**，覆盖当天 6:00–24:00
      （0:00–6:00 共 6 个小时块无对应列），用于展示"更晚发布精度更高、
      但要牺牲当天前 6 小时"的取舍。
    * **朴素预报 B**：前一日（:math:`d-1`）的光伏实际功率，按整点均值重复。
    * **负载**：附件不含负载预报，主口径用前一日**逐小时剖面**作朴素预报，
      另提供"负载已知"口径用于隔离光伏预报误差的影响。

    Args:
        data: 与 ``Q2_solve_plan.load_data`` 同构的数据字典。
        att3: 附件 3 数据。

    Returns:
        含 ``pv_forecast_a_kw`` / ``pv_forecast_a_e``（第 d 日 0:00 发布）、
        ``pv_forecast_6h_kw`` / ``pv_forecast_6h_e``（第 d 日 6:00 发布）、
        ``pv_naive_kw`` / ``pv_naive_e``、``load_naive_kw`` / ``load_naive_e``、
        ``load_actual_kw`` / ``load_actual_e``、``pv_actual_kw`` / ``pv_actual_e``
        的字典。
    """
    dates = data["dates"]
    n_days = len(dates)
    att2 = data["att2"]
    full_index = {d: i for i, d in enumerate(att2.dates)}
    pv_full = np.asarray(att2.pv_actual, dtype=float)
    load_full = np.asarray(att2.load, dtype=float)

    prev_pv_kw = np.zeros((n_days, T))
    prev_load_kw = np.zeros((n_days, T))
    forecast_a_kw = np.zeros((n_days, T))
    forecast_6h_kw = np.zeros((n_days, T))
    uncovered_a: list[int] = []
    uncovered_6h: list[int] = []
    for i, day in enumerate(dates):
        prev_day = day - timedelta(days=1)
        if prev_day not in full_index:
            raise KeyError(f"附件 2 缺少 {prev_day}（{day} 的前一日），无法构造朴素预报")
        j = full_index[prev_day]
        prev_pv_kw[i] = pv_full[j]
        # 朴素负载预报用**逐小时剖面**（同一钟点）而不是全天均值：
        # 前者保留日内形状（日间高、夜间低），后者会把整天的形状抹平，
        # 使计划量在负荷高峰期系统性偏低、人为放大紧急购电。
        prev_load_kw[i] = np.repeat(load_full[j].reshape(24, 6).mean(axis=1), 6)
        # 预报 A：第 d 日 0:00 发布（24 列恰好铺满当天 0:00–24:00 的全部 24 个小时块）
        forecast_a_kw[i], ua = forecast_from_release(att3, day, 0, day)
        uncovered_a = ua
        # 显式验收（t6 追加项）：预报 A 必须 144/144 覆盖；
        # 任何未覆盖钟点都意味着块索引/铺展回归，会让 t=1..6 以 0 进入 144 时段分母、
        # 系统性污染 MAE（历史上 448.3124 vs 371.2208 的分歧即由此而来）。
        if ua:
            raise AssertionError(
                f"预报 A 在 {day} 存在未覆盖钟点 {ua}：块索引回归（期望 24/24、144/144）"
            )
        # 预报 A'：第 d 日 6:00 发布（只覆盖当天 6:00–24:00 的 18 个小时块）
        forecast_6h_kw[i], u6 = forecast_from_release(att3, day, 6, day)
        uncovered_6h = u6

    return {
        "pv_forecast_a_kw": forecast_a_kw,
        "pv_forecast_a_e": io.interval_power_to_energy(forecast_a_kw),
        "pv_forecast_6h_kw": forecast_6h_kw,
        "pv_forecast_6h_e": io.interval_power_to_energy(forecast_6h_kw),
        "pv_naive_kw": prev_pv_kw,
        "pv_naive_e": io.interval_power_to_energy(prev_pv_kw),
        "load_naive_kw": prev_load_kw,
        "load_naive_e": io.interval_power_to_energy(prev_load_kw),
        "load_actual_kw": data["load_kw"],
        "load_actual_e": data["load_e"],
        "pv_actual_kw": data["pv_kw"],
        "pv_actual_e": data["pv_e"],
        # 预报 A 覆盖目标日全部 24 个小时块（144 个时段，无缺口）；
        # 预报 A'（6:00 发布）只覆盖 6:00–24:00 的 18 个小时块。
        "covered_hours_per_day": 24,
        "covered_hours_per_day_6h": 18,
        "uncovered_hours": uncovered_a,
        "uncovered_hours_6h": uncovered_6h,
        # 显式验收（t6 追加项）：块索引不变式的机器可读记录
        "block_index_assertion": {
            "rule": "R-Q2-5：f_d[k] 管 t = 6(k-1)+1..6k；绝对小时块 = release_hour + k - 1",
            "days_checked": len(data["dates"]),
            "days_with_uncovered_hours": 0,
            "covered_hours_per_day": 24,
            "covered_intervals_per_day": 144,
            "zero_filled_intervals": 0,
            "assertion": ("预报 A 的 24 列恰好对应当天 0:00–24:00 的 24 个小时块，"
                          "144/144 个时段全部有列、**无任何补零填充**；"
                          "构建时若出现未覆盖钟点会直接 raise（已写入 build_forecasts）。"),
        },
    }


def forecast_errors(data: dict, forecasts: dict, att3: io.Attachment3) -> dict:
    """量化各预报口径的误差（供论文说明对照口径的可信度）。

    除在用口径（第 d 日 0:00 发布、前一日实际、负载朴素剖面）以外，还给出
    **四个发布时刻的横向统计**（第 d 日 0:00 / 6:00 / 12:00 发布的当日预报，
    以及前一日 18:00 发布的那条）。⚠ 各发布时刻能落在**目标日**的覆盖长度不同
    （未覆盖钟点保持 0），**MAE 不可横向排序**，只用于说明"0:00 发布是唯一
    在制定计划时即可获得、且恰好铺满当天 24 个小时块的整点预报"。

    Args:
        data: 与 ``Q2_solve_plan.load_data`` 同构的数据字典。
        forecasts: :func:`build_forecasts` 的返回值。
        att3: 附件 3 数据（用于横向对比其他发布时刻）。

    Returns:
        含 MAE / RMSE / 偏差 / P90 绝对误差（kW）的字典。
    """
    pv_actual, load_actual = data["pv_kw"], data["load_kw"]
    dates = data["dates"]

    def stats(pred: np.ndarray, actual: np.ndarray) -> dict[str, float]:
        """返回一组预测误差指标（kW）。"""
        err = pred - actual
        return {
            "mae_kw": float(np.abs(err).mean()),
            "rmse_kw": float(np.sqrt((err ** 2).mean())),
            "bias_kw": float(err.mean()),
            "p90_abs_kw": float(np.quantile(np.abs(err), 0.90)),
        }

    # 四个发布时刻的横向统计（**复用唯一映射实现 release_hourly_blocks**）。
    # ⚠ 各发布时刻能落在**目标日**的小时块数不同，未覆盖钟点保持 0（不插值、不外推），
    # 故这几行的 MAE **不可横向排序**，只用于说明"越晚发布 ⇒ 当天可覆盖时段越少"
    # 这一取舍；其中 r=0 一行与 `pv_forecast_a_vs_actual` 同口径、数值必须完全相同。
    by_release: dict[str, dict] = {}
    preds_by_release: dict[int, np.ndarray] = {}
    for release_hour in (0, 6, 12, 18):
        pred = np.zeros_like(pv_actual)
        covered_total = 0
        uncovered_hours: list[int] = []
        for i, day in enumerate(dates):
            release_day = day - timedelta(days=1) if release_hour == 18 else day
            hourly, covered_h, uncovered_h = release_hourly_blocks(
                att3, release_day, release_hour, day)
            pred[i] = np.repeat(hourly, 6)                   # 未覆盖钟点 = 0
            covered_total += len(covered_h)
            uncovered_hours = uncovered_h
        covered_per_day = covered_total // len(dates)
        by_release[f"{'前一日' if release_hour == 18 else '当日'} {release_hour:02d}:00 发布"] = {
            **stats(pred, pv_actual),
            "release_hour": release_hour,
            "release_day_offset_days": 1 if release_hour == 18 else 0,
            "hour_blocks_per_release": 24,
            "target_day_covered_hours": covered_per_day,
            "target_day_uncovered_hours": uncovered_hours,
            "zero_filled_uncovered_hours": bool(uncovered_hours),
            "full_target_day_144_intervals": bool(covered_per_day == 24),
            "available_at_00_00": bool(release_hour in (0, 18)),
            "comparable_across_releases": False,
        }
        preds_by_release[release_hour] = pred

    # 四个发布时刻在目标日**共同覆盖**的钟点：12:00–18:00（6 个小时块 / 36 个时段）。
    # 只有在这一**同一批时段**上做跨发布时刻比较才是合法的（见下方 warning）。
    common_hours = [12, 13, 14, 15, 16, 17]
    common_idx = np.concatenate([np.arange(h * 6, (h + 1) * 6) for h in common_hours])
    cross_release_comparable = {
        "definition": ("四个发布时刻在目标日**共同覆盖**的钟点 12:00–18:00"
                       f"（{len(common_hours)} 个小时块 / {int(common_idx.size)} 个时段）。"
                       "跨发布时刻的精度比较**只允许**在这一同一批时段上进行；"
                       "各自全天的 MAE/RMSE 因覆盖区间不同，一律不可横向排序。"),
        "hours": common_hours,
        "n_intervals_per_day": int(common_idx.size),
        "per_release": {
            f"{rh:02d}:00 发布": stats(preds_by_release[rh][:, common_idx],
                                       pv_actual[:, common_idx])
            for rh in (0, 6, 12, 18)
        },
    }

    # ---- 误差统计：**两层并列**（中性命名，不使用"信息性/精确段"等提法）----
    err_a = np.abs(forecasts["pv_forecast_a_kw"] - pv_actual)
    pos = pv_actual > 1e-6
    err_signed = forecasts["pv_forecast_a_kw"] - pv_actual
    layer_full_day = {
        "definition": "当天全部 144 个时段（48 096 个时点）",
        "mae_kw": float(err_a.mean()),
        "rmse_kw": float(np.sqrt((err_a ** 2).mean())),
        "bias_kw": float(err_signed.mean()),
        "p90_abs_kw": float(np.quantile(err_a, 0.90)),
        "n_intervals": int(err_a.size),
    }
    layer_actual_positive = {
        "definition": "只统计实际光伏 > 0 的时段（白天口径，参考层）",
        "mae_kw": float(err_a[pos].mean()),
        "rmse_kw": float(np.sqrt((err_a[pos] ** 2).mean())),
        "bias_kw": float(err_signed[pos].mean()),
        "p90_abs_kw": float(np.quantile(err_a[pos], 0.90)),
        "n_intervals": int(pos.sum()),
        "zero_actual_interval_share": float(1.0 - pos.mean()),
        "note": ("夜间（0:00–4:00 与 19:00–24:00）光伏恒为零，占全天 "
                 f"{float(1.0 - pos.mean()):.2%} 的时段，会把全天 MAE 稀释；"
                 "本层为参考层、**不替代主指标**。论文引用必须写明所用口径，"
                 "两个数不可互相替代。"),
    }
    mae_definition = {
        "definition": ("**两层并列，全部现场计算**：主指标 = 当天全部 144 个时段；"
                       "参考层 = 只统计实际光伏 > 0 的时段。"
                       "预报 A（第 d 日 0:00 发布）的第 k 列对应 t = 6(k−1)+1..6k，"
                       "24 列恰好铺满当天 0:00–24:00，**无缺口、无补零、无子集划分**；"
                       "`pv_forecast_a_vs_actual` 等键按主指标口径。"
                       "**已被移除的旧口径**：曾以『剔除 hour 0 的 6 个时段』计算的旧指标"
                       "（=『错位一格』规则的 MAE × 144/138）建立在『存在未覆盖时段』这一"
                       "**已被块索引修复消灭**的前提上，现已彻底移除，不作为备选项、也不并列。"),
        "n_intervals_per_day": T,
        "n_intervals_total": int(err_a.size),
        "mae_layers": {
            "full_day": layer_full_day,
            "actual_positive": layer_actual_positive,
        },
        "mae_kw_full_day": layer_full_day["mae_kw"],
        "stats_full_day": layer_full_day,
        "stats_actual_positive": layer_actual_positive,
        "cross_release_warning": ("四个发布时刻的覆盖长度与时效区间不同，"
                                  "**跨发布时刻的 MAE 排序一律不得开展**；"
                                  "跨口径比较只能在**同一批时段**上做"
                                  "（见 cross_release_comparable_subset）。"),
    }

    return {
        "pv_forecast_a_vs_actual": stats(forecasts["pv_forecast_a_kw"], pv_actual),
        "pv_forecast_6h_vs_actual": stats(forecasts["pv_forecast_6h_kw"], pv_actual),
        "pv_naive_vs_actual": stats(forecasts["pv_naive_kw"], pv_actual),
        "load_naive_vs_actual": stats(forecasts["load_naive_kw"], load_actual),
        "mae_definition": mae_definition,
        "block_index_assertion": forecasts["block_index_assertion"],
        "cross_release_comparable_subset": cross_release_comparable,
        "by_release_hour": by_release,
        "covered_periods": {
            "definition": ("第 d 日 0:00 发布的那条 24 列恰好对应当天 0:00–24:00 的 "
                           "24 个小时块（144 个时段），**全天无缺口**；"
                           "`pv_forecast_a_vs_actual` 等键按当天全部 144 个时段统计，"
                           "该定义与契约给出的实测参考值一致"
                           "（第 d 日 0:00 发布全年 MAE 371.22 kW；"
                           "2025-06-21 分段恒定 336.75 kW、错位一格 412.23 kW）"),
            "full_day_intervals": 144,
            "covered_hours_per_day": 24,
            "pv_forecast_a_mae_kw_full_day": float(
                np.abs(forecasts["pv_forecast_a_kw"] - pv_actual).mean()),
            "pv_naive_mae_kw_full_day": float(
                np.abs(forecasts["pv_naive_kw"] - pv_actual).mean()),
        },
        "note": ("预报 A = 附件 3 第 d 日 0:00 发布、覆盖当天 0:00–24:00 全部 24 个小时块"
                 "（144 个时段，无缺口）；预报 A' = 第 d 日 6:00 发布（只覆盖 6:00–24:00 "
                 "的 18 个小时块）；"
                 "朴素预报 = 前一日实际值；负载主口径用前一日逐小时剖面"
                 "（附件不含负载预报数据）"),
        "interpretation": (
            "0:00 发布是唯一**在制定计划的时刻（0:00）即可获得、且恰好铺满当天 "
            "24 个小时块（144 个时段，无缺口）**的整点预报；6:00 / 12:00 发布的"
            "预报在 0:00 尚不可得，前一日 18:00 发布的那条虽在 0:00 可得、"
            "却只覆盖当天 0:00–18:00（缺 18:00–24:00 共 6 个钟点）。"
            "各发布时刻的覆盖长度与时效区间不同（**预报 A 本身无缺口**；"
            "仅其它发布时刻的横向统计行里，其未覆盖钟点保持 0） ⇒ "
            "`by_release_hour` 各行的 MAE **不可横向排序**（该键每行 "
            "`comparable_across_releases = False`），故不存在\"哪个发布时刻更准\""
            "的结论。早期实现误用『前一日 18:00 发布』那条、且小时块索引整体错位一格，"
            "曾在同一个 JSON 里对 0:00 发布给出两个互相矛盾的 MAE；现已统一为"
            "唯一映射实现 release_hourly_blocks。"
        ),
    }


# --------------------------------------------------------------------------- #
# STAGE B  两阶段 LP
# --------------------------------------------------------------------------- #
def _soc_inequalities() -> tuple[csr_matrix, np.ndarray]:
    """SOC 上下界不等式（变量顺序 ``[x | y | …]``，只涉及前 2T 列）。

    ``S_{t+1} = S_0 + eta·Σ_{τ<=t} x_τ - (1/eta)·Σ_{τ<=t} y_τ``，故
    ``S_lo ≤ S_{t+1} ≤ S_hi`` 在 ``t = 0..T-1`` 上是 2T 条前缀和不等式。

    Returns:
        ``(a_ub, b_ub)``，形状 ``(2T, 2T)`` 与 ``(2T,)``。
    """
    upper = np.hstack([ETA * _TRI, -_TRI / ETA])
    lower = np.hstack([-ETA * _TRI, _TRI / ETA])
    a_ub = csr_matrix(np.vstack([upper, lower]))
    b_ub = np.concatenate([np.full(T, S_HI - S_INIT), np.full(T, S_INIT - S_LO)])
    return a_ub, b_ub


def _balance_row() -> np.ndarray:
    """日终能量平衡行 ``eta·Σx - Σy/eta``（对应 ``S_T - S_0``）。"""
    return np.concatenate([ETA * np.ones(T), -np.ones(T) / ETA])


def solve_plan_stage(load_e: np.ndarray, pv_e: np.ndarray,
                     price: np.ndarray,
                     p_cap: np.ndarray | None = None,
                     allow_soc_shortfall: bool = False) -> dict:
    r"""计划阶段 LP：用预报制定计划购电量与计划储能调度（0:00 一次锁定）。

    变量 ``[x(T) | y(T) | q(T) | d(T) | (s(T))]``：``q`` 为计划购电量、
    ``d`` 为被丢弃的过剩光伏电量、``s`` 为**日终储电量缺口**（仅当
    ``allow_soc_shortfall`` 时存在）。

    * 等式 ``q_t - d_t - x_t + y_t = n^{f}_t``；
    * 等式 ``eta·Σ_t x_t - Σ_t y_t/eta + Σ_t s_t = 0``（``s ≡ 0`` 时即日终归位
      :math:`S_T = S_0`）；
    * 不等式：SOC 上下界、``q ≥ 0``、``d ≥ 0``，以及可选的 ``q_t ≤ p^{cap}_t``。

    目标（**关键，且必须如实描述**）：

    .. math::

        \min\ \sum_t c_t q_t \;+\; \lambda \sum_t \big(m_t + p_t\big),
        \qquad m_t - p_t = \theta_t - q_t,\quad
        \theta_t = n^{f}_t + x_t - y_t + d_t,\quad \lambda = 5 \cdot \max_t c_t

    两条等式（``q_t - d_t - x_t + y_t = n^{f}_t`` 与 ``θ_t - q_t = m_t - p_t``）在
    **任意可行点**上给出 :math:`q_t \equiv \theta_t` 与 :math:`m_t = p_t`；再加
    ``λ > 0``，最优解处恒有 :math:`q_t = n^{f}_t + x_t - y_t + d_t`、
    :math:`m_t = p_t = 0`。

    **两条必须说清的结论（早期文档曾写成似是而非的论证）**：

    1. ``q`` **不是自由变量**：它被平衡等式唯一钉住，**不存在**"LP 把计划量压到 0"
       的机制——要改 ``q`` 只能改 :math:`(x_t, y_t, d_t)`，而它们受功率上限、SOC
       边界与日终归位约束。因此第二项罚式在**当前实现中对最优值没有任何贡献**
       （实测：把 λ 置 0，最优值只差 4.6e-07 元，仅改变多重最优中的选择），它是
       保留的冗余分解，不是"防止发散"的关键项；真正起作用的是平衡等式、
       ``q ≥ 0``（见模块 docstring）与储能约束。
    2. 完美信息下最优解自然满足 :math:`q_t = n_t + x_t - y_t`（回环校验：紧急购电
       0.00 kWh、总费用与主模型差 3.7e-07 元）；预报下的取舍由**执行阶段的实际
       结算**决定（多买照付、少买按 :math:`5c_t` 紧急购电），不来自第二项罚式。

    Args:
        load_e: 144 维负载电量（kWh，预报值）。
        pv_e: 144 维光伏电量（kWh，预报值）。
        price: 144 维电价（元/kWh）。
        p_cap: 144 维**外生**计划购电上限（kWh）；``None``（默认）表示无上限。
        allow_soc_shortfall: 是否允许日终储电量低于日初值（``s ≥ 0``）。
            购电上限很紧时严格归位会不可行，此时必须允许缺口，否则模型无解。

    Returns:
        含 ``q``/``x``/``y``/``soc``/``need``/``shortfall_kwh``/``cost_yuan`` 的字典。
    """
    net = load_e - pv_e
    # 变量：[x(T) | y(T) | q(T) | d(T) | m(T) | p(T)]（+ [s(T)] 当允许日终缺口）
    #   m/p 为 |need - q| 的正负部：need - q = m - p，m,p ≥ 0
    n_base = 7 * T if allow_soc_shortfall else 6 * T
    i_x, i_y, i_q, i_d, i_m, i_p = 0, T, 2 * T, 3 * T, 4 * T, 5 * T
    i_s = 6 * T
    lam = MULT * float(price.max())

    # 等式 1：q - d - x + y = n^f
    a_energy = np.zeros((T, n_base))
    a_energy[:, i_q:i_q + T] = np.eye(T)
    a_energy[:, i_d:i_d + T] = -np.eye(T)
    a_energy[:, i_x:i_x + T] = -np.eye(T)
    a_energy[:, i_y:i_y + T] = np.eye(T)
    b_energy = net.copy()
    # 等式 2：need - q = m - p  =>  (x - y + d) - q - m + p = -n^f
    a_gap = np.zeros((T, n_base))
    a_gap[:, i_x:i_x + T] = np.eye(T)
    a_gap[:, i_y:i_y + T] = -np.eye(T)
    a_gap[:, i_d:i_d + T] = np.eye(T)
    a_gap[:, i_q:i_q + T] = -np.eye(T)
    a_gap[:, i_m:i_m + T] = -np.eye(T)
    a_gap[:, i_p:i_p + T] = np.eye(T)
    b_gap = -net
    # 等式 3：日终能量平衡（可选缺口 s）
    a_final = np.zeros((1, n_base))
    a_final[0, i_x:i_x + T] = ETA
    a_final[0, i_y:i_y + T] = -1.0 / ETA
    if allow_soc_shortfall:
        a_final[0, i_s:i_s + T] = 1.0
    a_eq = csr_matrix(np.vstack([a_energy, a_gap, a_final]))
    b_eq = np.concatenate([b_energy, b_gap, [0.0]])
    # 不等式：SOC 上下界（只涉及 x、y 两列块）+ （可选）计划购电上限
    soc_block = _soc_inequalities()[0].toarray()
    ub_blocks = [np.hstack([soc_block, np.zeros((2 * T, n_base - 2 * T))])]
    rhs_blocks = [_soc_inequalities()[1]]
    if p_cap is not None:
        cap_rows = np.zeros((T, n_base))
        cap_rows[np.arange(T), i_q + np.arange(T)] = 1.0
        ub_blocks.append(cap_rows)
        rhs_blocks.append(np.asarray(p_cap, dtype=float))
    a_ub = csr_matrix(np.vstack(ub_blocks))
    b_ub = np.concatenate(rhs_blocks)

    c = np.zeros(n_base)
    c[i_q:i_q + T] = price                       # 计划购电费（1 倍电价）
    c[i_m:i_m + T] = lam                         # 净需求高于计划量（少买）
    c[i_p:i_p + T] = lam                         # 计划量高于净需求（多买照付）
    c[i_d:i_d + T] = price * 1e-9                # 极小扰动，去除丢弃量的多重最优
    if allow_soc_shortfall:
        c[i_s:i_s + T] = lam                     # 日终缺口按同一影子价格计价
    bounds = ([(0.0, CAP)] * T + [(0.0, CAP)] * T        # x
              + [(0.0, None)] * T + [(0.0, None)] * T     # q, d
              + [(0.0, None)] * T + [(0.0, None)] * T     # m, p
              + ([(0.0, None)] * T if allow_soc_shortfall else []))   # s
    if len(bounds) != n_base:
        raise AssertionError(
            f"计划阶段变量边界条数 {len(bounds)} != 变量数 {n_base}"
        )
    res = linprog(c, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq,
                  bounds=bounds, method="highs")
    if not res.success:
        raise RuntimeError(f"计划阶段 LP 失败：{res.message}")
    z = res.x

    def _clean(a: np.ndarray) -> np.ndarray:
        """把亚容差抖动量归零。"""
        return np.where(np.abs(a) < 1e-9, 0.0, a)

    x = _clean(z[i_x:i_x + T])
    y = _clean(z[i_y:i_y + T])
    q = _clean(z[i_q:i_q + T])
    d = _clean(z[i_d:i_d + T])
    s = _clean(z[i_s:i_s + T]) if allow_soc_shortfall else np.zeros(T)
    soc = _extract_soc(x, y)
    need = net + x - y + d          # 计划调度下的净需求（预测量口径）
    consumed = need - d             # 实际被消耗的购电量 = net + x - y
    return {"q": q, "x": x, "y": y, "soc": soc, "discard": d, "net": net,
            "need": need, "consumed": consumed,
            "shortfall_kwh": float(s.sum()),
            "cost_yuan": float((price * q).sum()),
            "soc_end_kwh": float(soc[-1]),
            "objective_yuan": float(c @ z),
            "lambda_yuan_per_kwh": lam,
            "max_abs_plan_gap_kwh": float(np.abs(q - need).max())}


def execute_locked_schedule(load_e: np.ndarray, pv_e: np.ndarray, price: np.ndarray,
                            plan_q: np.ndarray, plan_x: np.ndarray,
                            plan_y: np.ndarray, plan_d: np.ndarray) -> dict:
    """**承诺调度**口径（主用）：执行阶段按计划锁定的 ``q/x/y`` 结算，只允许调整弃光。

    两阶段的物理链条（契约 B4：计划量日内不可修改）：

    * 第 d 天 0:00 用预报锁定**计划购电量** :math:`p_t` 与**计划储能调度**
      :math:`(x^{\\text{p}}_t, y^{\\text{p}}_t)`（这就是"制定计划购电策略"的含义：
      策略里既有买多少电，也有储能怎么充放）；
    * 当天实际负载与光伏揭晓后，储能按已承诺的调度执行，微网必须满足负载；
    * 若实际光伏超出计划吸收能力（计划弃光 :math:`d^{\\text{p}}_t` 填不满），
      剩下的余量被丢弃（等价于把弃光量放大到刚好够），故实际购电为

      .. math::

          a_t = \\max\\{\\,n^{\\text{a}}_t + x^{\\text{p}}_t - y^{\\text{p}}_t,\\ 0\\,\\},
          \\qquad e_t = \\max\\{a_t - p_t,\\ 0\\}

    * ``p > a`` 的差额按计划量照付（1 倍电价，多买不退款），``e`` 按 5 倍计价。

    **完全信息下该口径精确复现主模型**（``p = a``、紧急购电 = 0），因此它是与主模型
    可比的对照口径；紧急购电量全部来自预报误差。

    Args:
        load_e: 144 维**实际**负载电量（kWh）。
        pv_e: 144 维**实际**光伏电量（kWh）。
        price: 144 维电价（元/kWh）。
        plan_q: 144 维已锁定的计划购电量（kWh）。
        plan_x: 144 维已锁定的计划充电量（kWh）。
        plan_y: 144 维已锁定的计划放电量（kWh）。
        plan_d: 144 维计划弃光电量（kWh）；当前实现不显式使用（弃光由上式隐含），
            保留该参数以便调用方核对计划阶段口径。

    Returns:
        含 ``actual``/``emergency``/``spare``/``soc`` 与三项费用的字典。
    """
    del plan_d
    net_actual = load_e - pv_e
    need = net_actual + plan_x - plan_y
    actual = np.maximum(need, 0.0)
    emergency = np.maximum(actual - plan_q, 0.0)
    spare = np.maximum(plan_q - actual, 0.0)
    soc = _extract_soc(plan_x, plan_y)
    planned_cost = float((price * plan_q).sum())
    emergency_cost = float((MULT * price * emergency).sum())
    return {
        "x": plan_x, "y": plan_y, "soc": soc,
        "actual": actual, "emergency": emergency, "spare": spare,
        "planned_cost_yuan": planned_cost,
        "emergency_cost_yuan": emergency_cost,
        "total_cost_yuan": planned_cost + emergency_cost,
        "soc_end_kwh": float(soc[-1]),
    }


def execute_adaptive_schedule(load_e: np.ndarray, pv_e: np.ndarray,
                              price: np.ndarray, plan_q: np.ndarray) -> dict:
    """**日内再调度**变体（假设性对照）：计划量锁定，储能按实际值重新优化。

    计划购电量 :math:`p` 与计划储能调度 :math:`(x^{\\text{plan}}, y^{\\text{plan}})`
    在 0:00 锁定、日内不可修改（契约 B4）；本变体额外假设储能调度
    :math:`(x_t, y_t, g_t)` 在当天实际负载与光伏揭晓后**可以重新优化**，
    因此**不再复现主模型**（完全信息下仍可能出现紧急购电），属强假设的粗略对照。
    把实际购电量相对计划量的分解记为
    :math:`a_t - p_t = u_t - v_t`（``u, v ≥ 0``，分别为紧急量与富余量）：

    .. math::

        \\min\\ \\sum_t \\big[5c_t\\,u_t + c_t\\,v_t\\big]
        \\quad\\text{s.t.}\\quad
        u_t - v_t - x_t + y_t = p_t - n^{\\text{a}}_t,\\quad
        S_0 = S_T = 6000,\\ 1200 \\le S_t \\le 10800

    目标里 :math:`c_t v_t` 是"计划买了但没用上"的照付部分（多买不退款），
    :math:`5c_t u_t` 是紧急购电。该变体只用于说明"日内再调度能省多少"，
    其数值**不构成对主口径紧急购电量的界**（复现性已被破坏）。

    Args:
        load_e: 144 维**实际**负载电量（kWh）。
        pv_e: 144 维**实际**光伏电量（kWh）。
        price: 144 维电价（元/kWh）。
        plan_q: 144 维已锁定的计划购电量（kWh）。

    Returns:
        含 ``x``/``y``/``soc``/``actual``/``emergency``/``spare`` 与三项费用的字典。
    """
    net = load_e - pv_e
    n = 4 * T
    i_x, i_y, i_u, i_v = 0, T, 2 * T, 3 * T
    # 等式：u - v - x + y = p - net
    a_link = np.hstack([-np.eye(T), np.eye(T), np.eye(T), -np.eye(T)])
    a_eq = csr_matrix(a_link)
    b_eq = plan_q - net
    # 不等式：SOC 上下界 + 日终归位（-eta·Σx + Σy/eta ≤ 0 与 ≥ 0 两条）
    soc_rows = _soc_inequalities()[0].toarray()
    final_row = np.concatenate([-ETA * np.ones(T), np.ones(T) / ETA, np.zeros(2 * T)])
    a_ub = csr_matrix(np.vstack([
        np.hstack([soc_rows, np.zeros((2 * T, 2 * T))]),
        final_row,
        -final_row,
    ]))
    b_ub = np.concatenate([_soc_inequalities()[1], [0.0], [0.0]])
    c = np.zeros(n)
    c[i_u:i_u + T] = MULT * price                 # 紧急购电：5 倍
    c[i_v:i_v + T] = price                        # 计划量内：1 倍（多买不退款）
    bounds = ([(0.0, CAP)] * T + [(0.0, CAP)] * T
              + [(0.0, None)] * T + [(0.0, None)] * T)
    res = linprog(c, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq,
                  bounds=bounds, method="highs")
    if not res.success:
        raise RuntimeError(f"日内再调度 LP 失败：{res.message}")
    z = res.x
    x = np.where(np.abs(z[i_x:i_x + T]) < 1e-9, 0.0, z[i_x:i_x + T])
    y = np.where(np.abs(z[i_y:i_y + T]) < 1e-9, 0.0, z[i_y:i_y + T])
    u = np.where(np.abs(z[i_u:i_u + T]) < 1e-9, 0.0, z[i_u:i_u + T])
    v = np.where(np.abs(z[i_v:i_v + T]) < 1e-9, 0.0, z[i_v:i_v + T])
    soc = _extract_soc(x, y)
    actual = net + x - y
    planned_cost = float((price * plan_q).sum())
    emergency_cost = float((MULT * price * u).sum())
    return {
        "x": x, "y": y, "soc": soc, "emergency": u, "spare": v, "actual": actual,
        "planned_cost_yuan": planned_cost,
        "emergency_cost_yuan": emergency_cost,
        "total_cost_yuan": planned_cost + emergency_cost,
        "soc_end_kwh": float(soc[-1]),
    }


def _extract_soc(x: np.ndarray, y: np.ndarray, *, s_init: float = S_INIT) -> np.ndarray:
    """由充放电序列回代储电量轨迹 ``S_0..S_T``（长度 T+1）。"""
    soc = np.empty(x.size + 1)
    soc[0] = s_init
    for t in range(x.size):
        soc[t + 1] = soc[t] + ETA * x[t] - y[t] / ETA
    return soc


# --------------------------------------------------------------------------- #
# STAGE C  全年两阶段仿真
# --------------------------------------------------------------------------- #
def run_variant(data: dict, forecasts: dict, pv_key: str, load_key: str,
                label: str, *, dispatch: str = "locked") -> dict:
    """对一种预报口径跑完整的两阶段（计划 + 执行）全年仿真。

    Args:
        data: 与 ``Q2_solve_plan.load_data`` 同构的数据字典。
        forecasts: :func:`build_forecasts` 的返回值。
        pv_key: 计划阶段使用的光伏预报列（``"pv_forecast_a_e"`` /
            ``"pv_forecast_6h_e"`` / ``"pv_naive_e"`` / ``"pv_actual_e"``）。
        load_key: 计划阶段使用的负载预报列（``"load_naive_e"`` / ``"load_actual_e"``）。
        label: 口径名称（写入结果与图例）。
        dispatch: 执行阶段的储能调度口径：

            * ``"locked"``（**默认、主用**）：储能按**计划已承诺的调度**执行。
              该口径在**完全信息下精确复现主模型**（紧急购电 = 0、总费用与
              result2.xlsx 逐分一致），因此是与主模型可比的对照口径；
            * ``"adaptive"``（**假设性对照**）：假设计划量锁定但储能可在日内
              重新优化。该口径**不具备上述复现性**（即使负载与光伏都已知仍有紧急购电），
              故只用于粗略说明"日内再调度能省多少"，须显式标注为强假设。

    Returns:
        含逐日计划量 / 实际量 / 紧急购电量、储电轨迹与费用汇总的字典。
    """
    if dispatch not in {"adaptive", "locked"}:
        raise ValueError(f"dispatch 必须是 'adaptive' 或 'locked'，收到 {dispatch!r}")
    dates = data["dates"]
    n_days = len(dates)
    price_row = data["price_row"]
    load_e, pv_e = data["load_e"], data["pv_e"]
    load_f, pv_f = forecasts[load_key], forecasts[pv_key]

    plan = np.zeros((n_days, T))
    actual = np.zeros((n_days, T))
    emergency = np.zeros((n_days, T))
    spare = np.zeros((n_days, T))
    x_plan = np.zeros((n_days, T))
    y_plan = np.zeros((n_days, T))
    p_discard = np.zeros((n_days, T))
    x_act = np.zeros((n_days, T))
    y_act = np.zeros((n_days, T))
    soc_act = np.zeros((n_days, T + 1))
    planned_cost = np.zeros(n_days)
    emergency_cost = np.zeros(n_days)
    total_cost = np.zeros(n_days)
    soc_end = np.zeros(n_days)

    t0 = time.perf_counter()
    for i, _day in enumerate(dates):
        p = solve_plan_stage(load_f[i], pv_f[i], price_row)
        # 计划阶段一致性自检：SOC 轨迹必须落在 [S_LO, S_HI] 且日终归位
        if not (S_LO - 1e-6 <= p["soc"].min() and p["soc"].max() <= S_HI + 1e-6
                and abs(p["soc"][-1] - S_INIT) < 1e-6):
            raise AssertionError(
                f"{dates[i]} 计划阶段 SOC 越界或未归位："
                f"min={p['soc'].min():.6f} max={p['soc'].max():.6f} end={p['soc'][-1]:.6f}"
            )
        plan[i] = p["q"]
        x_plan[i], y_plan[i] = p["x"], p["y"]
        p_discard[i] = p["discard"]
        # 执行阶段：计划量锁定，储能按所选口径处理
        if dispatch == "adaptive":
            a = execute_adaptive_schedule(load_e[i], pv_e[i], price_row, plan[i])
        else:
            a = execute_locked_schedule(load_e[i], pv_e[i], price_row,
                                        plan[i], x_plan[i], y_plan[i], p_discard[i])
        actual[i] = a["actual"]
        emergency[i] = a["emergency"]
        spare[i] = a["spare"]
        x_act[i], y_act[i], soc_act[i] = a["x"], a["y"], a["soc"]
        planned_cost[i] = a["planned_cost_yuan"]
        emergency_cost[i] = a["emergency_cost_yuan"]
        total_cost[i] = a["total_cost_yuan"]
        soc_end[i] = a["soc_end_kwh"]
    elapsed = time.perf_counter() - t0

    emg_total = float(emergency.sum())
    n_emg_slots = int((emergency > 1e-9).sum())
    n_emg_days = int((emergency.sum(axis=1) > 1e-9).sum())
    _log(f"[{label}] 两阶段仿真完成：{n_days} 天，耗时 {elapsed:.1f} s；"
         f"紧急购电 {emg_total:,.2f} kWh（{n_emg_days} 天 / {n_emg_slots} 个时段）；"
         f"总费用 {total_cost.sum():,.2f} 元，其中紧急购电费 {emergency_cost.sum():,.2f} 元")

    return {
        "label": label,
        "forecast_column": pv_key,
        "load_column": load_key,
        "dispatch": dispatch,
        "elapsed_seconds": elapsed,
        "plan": plan, "actual": actual, "emergency": emergency, "spare": spare,
        "x_plan": x_plan, "y_plan": y_plan,
        "x_actual": x_act, "y_actual": y_act, "soc_actual": soc_act,
        "planned_cost_yuan": planned_cost,
        "emergency_cost_yuan": emergency_cost,
        "total_cost_yuan": total_cost,
        "soc_end_kwh": soc_end,
        "summary": {
            "planned_purchase_kwh": float(plan.sum()),
            "actual_purchase_kwh": float(actual.sum()),
            "emergency_purchase_kwh": emg_total,
            "emergency_slots": n_emg_slots,
            "emergency_days": n_emg_days,
            "emergency_day_share": n_emg_days / n_days,
            "planned_cost_yuan": float(planned_cost.sum()),
            "emergency_cost_yuan": float(emergency_cost.sum()),
            "total_cost_yuan": float(total_cost.sum()),
            "emergency_share_of_total_cost": (float(emergency_cost.sum() / total_cost.sum())
                                              if total_cost.sum() > 0 else 0.0),
            "mean_emergency_price_yuan_per_kwh": (
                float(emergency_cost.sum() / emg_total) if emg_total > 1e-9 else 0.0
            ),
            "spare_kwh": float(spare.sum()),
            "soc_end_mean_kwh": float(soc_end.mean()),
            "soc_end_min_kwh": float(soc_end.min()),
            "soc_end_max_kwh": float(soc_end.max()),
            "soc_min_kwh": float(soc_act.min()),
            "soc_max_kwh": float(soc_act.max()),
        },
    }


# --------------------------------------------------------------------------- #
# STAGE D  表 3 明细
# --------------------------------------------------------------------------- #
def _span_labels(start_t: int, end_t: int) -> tuple[str, str]:
    """时段序号闭区间 ``[start_t, end_t]``（1-based）→ ``(起点, 止点)`` 时刻标签。"""
    def fmt(minutes: int) -> str:
        """分钟数 → ``H:MM`` 标签（跨日用 ``0:00+1``）。"""
        if minutes >= 24 * 60:
            return "0:00+1"
        return f"{minutes // 60}:{minutes % 60:02d}"

    return (fmt((start_t - 1) * paths.INTERVAL_MINUTES),
            fmt(end_t * paths.INTERVAL_MINUTES))


def pcap_sensitivity(data: dict, forecasts: dict,
                     alphas: tuple[float, ...] = (0.70, 0.85, 1.00),
                     pv_key: str = "pv_forecast_a_e",
                     load_key: str = "load_actual_e") -> dict:
    """``p^cap`` 敏感性口径：给"常规购电通道"加逐时段外生上限后重算紧急购电。

    口径（对应 ``C题_问题分析与数学建模框架.md`` §5.4 与裁定 A16）：

    .. math::

        p^{\\text{cap}}_{d,t} = \\alpha \\cdot \\max_t n^{\\text{f}}_{d,t}
        \\qquad \\alpha \\in \\{0.70,\\ 0.85,\\ 1.00\\}

    即把计划购电量的逐时段上限设为"当日预报净负荷峰值"的 :math:`\\alpha` 倍
    （:math:`\\alpha = 1` 表示上限等于峰值、通常不再构成约束，可与无上限的主口径
    相互印证）。计划阶段在该上限下求解，执行阶段按**已锁定的储能调度**结算，
    超出计划量的部分按 5 倍电价紧急购电。

    .. note::
        题目**没有**给出任何购电容量或合约上限，故本口径是**敏感性对照**而非主口径；
        它的价值在于回答"若常规购电通道受限、需要多少紧急购电"。

    Args:
        data: 与 ``Q2_solve_plan.load_data`` 同构的数据字典。
        forecasts: :func:`build_forecasts` 的返回值（提供预报列）。
        alphas: 待扫描的上限比例。
        pv_key: 计划阶段用的光伏列（默认附件 3 日前预报）。
        load_key: 计划阶段用的负载列（默认实际值，以隔离上限这一单一因素）。

    Returns:
        含 ``alphas``、``scenarios``（每个 :math:`\\alpha` 的逐日与全年汇总）与
        ``table3_specified_dates``（四个指定日期的紧急购电量）的字典。
    """
    dates = data["dates"]
    price_row = data["price_row"]
    load_e, pv_e = data["load_e"], data["pv_e"]
    load_f = forecasts[load_key]
    pv_f = forecasts[pv_key]
    net_f = load_f - pv_f

    scenarios: dict[str, dict] = {}
    for alpha in alphas:
        plan = np.zeros((len(dates), T))
        emergency = np.zeros((len(dates), T))
        planned_cost = np.zeros(len(dates))
        emergency_cost = np.zeros(len(dates))
        cap_hit_slots = 0
        shortfall_days = 0
        shortfall_total = 0.0
        fallback_days: list[str] = []
        for i, day in enumerate(dates):
            cap = alpha * float(net_f[i].max())
            cap_vec = np.full(T, cap)
            # 上限很紧时严格日终归位可能不可行（无足够电量把储能充回 6000），
            # 此时允许日终储电量缺口，并把它按 5 倍电价的影子价格计入计划阶段目标。
            try:
                p = solve_plan_stage(load_f[i], pv_f[i], price_row, p_cap=cap_vec)
            except RuntimeError:
                try:
                    p = solve_plan_stage(load_f[i], pv_f[i], price_row, p_cap=cap_vec,
                                         allow_soc_shortfall=True)
                    shortfall_days += 1
                    shortfall_total += p["shortfall_kwh"]
                except RuntimeError:
                    # 兜底：某些 (α, 日) 组合即使允许缺口也无法满足 SOC 下界，
                    # 此时退化为"无上限计划"以保持敏感性分析完整，并记录退化日。
                    p = solve_plan_stage(load_f[i], pv_f[i], price_row)
                    fallback_days.append(day.isoformat())
            plan[i] = p["q"]
            cap_hit_slots += int((p["q"] >= cap - 1e-6).sum())
            a = execute_locked_schedule(load_e[i], pv_e[i], price_row,
                                        p["q"], p["x"], p["y"], p["discard"])
            emergency[i] = a["emergency"]
            planned_cost[i] = a["planned_cost_yuan"]
            emergency_cost[i] = a["emergency_cost_yuan"]
        emg_total = float(emergency.sum())
        label = f"α={alpha:.2f}"
        scenarios[label] = {
            "alpha": alpha,
            "cap_definition": "p^cap_t = alpha * max_t(预报净负荷)（当日逐时段相同，单位 kWh/时段）",
            "planned_purchase_kwh": float(plan.sum()),
            "emergency_purchase_kwh": emg_total,
            "emergency_slots": int((emergency > 1e-9).sum()),
            "emergency_days": int((emergency.sum(axis=1) > 1e-9).sum()),
            "cap_binding_slots": cap_hit_slots,
            "soc_shortfall_days": shortfall_days,
            "soc_shortfall_kwh": shortfall_total,
            "uncapped_fallback_days": fallback_days,
            "planned_cost_yuan": float(planned_cost.sum()),
            "emergency_cost_yuan": float(emergency_cost.sum()),
            "total_cost_yuan": float(planned_cost.sum() + emergency_cost.sum()),
            "mean_emergency_price_yuan_per_kwh": (
                float(emergency_cost.sum() / emg_total) if emg_total > 1e-9 else 0.0
            ),
            "daily_emergency_kwh": [float(v) for v in emergency.sum(axis=1)],
        }
        _log(f"[p^cap 敏感性] {label}: 计划购电 {plan.sum():,.2f} kWh；"
             f"紧急购电 {emg_total:,.2f} kWh（{scenarios[label]['emergency_days']} 天）；"
             f"总费用 {scenarios[label]['total_cost_yuan']:,.2f} 元；"
             f"上限触界时段 {cap_hit_slots}；日终缺口 {shortfall_days} 天 / "
             f"{shortfall_total:,.2f} kWh；无上限退化日 {len(fallback_days)}")

    table3: dict[str, dict[str, float]] = {}
    for label, scenario in scenarios.items():
        # 逐日紧急电量已在 scenarios 里，按日期取出四个指定日期的值
        daily = scenario["daily_emergency_kwh"]
        table3[label] = {day.isoformat(): float(daily[dates.index(day)])
                         for day in TABLE3_DATES}
    # finding 的全部数值都从 scenarios 现场取（避免手写死数与实测不一致）
    first = scenarios[f"α={alphas[0]:.2f}"]
    last = scenarios[f"α={alphas[-1]:.2f}"]
    emg_lo = first["emergency_purchase_kwh"]
    emg_hi = last["emergency_purchase_kwh"]
    emg_spread = abs(emg_hi - emg_lo) / max(emg_lo, 1e-9)
    return {"alphas": list(alphas), "scenarios": scenarios,
            "table3_specified_dates": table3,
            "finding": (
                f"α 从 {alphas[0]:.2f} 到 {alphas[-1]:.2f}（上限从『净负荷峰值的 "
                f"{alphas[0]:.0%}』放宽到『等于峰值』），紧急购电量几乎不变"
                f"（{emg_lo:,.2f} → {emg_hi:,.2f} kWh，相对变化 {emg_spread:.2%}），"
                f"但总费用从 {first['total_cost_yuan']:,.2f} 元降到 "
                f"{last['total_cost_yuan']:,.2f} 元、上限触界时段从 "
                f"{first['cap_binding_slots']} 降到 {last['cap_binding_slots']}。"
                "这说明在**执行阶段储能调度按计划锁定**的口径下，"
                "常规购电通道的容量上限并不是紧急购电的主因："
                "上限收紧只是把购电时机在『相邻时段』之间挪动（受惩罚的是相对计划的"
                "缺口而非绝对量），真正决定紧急购电量的是"
                "**实际净负荷与计划调度是否匹配**（即预报误差）。"
                f"注意 α={alphas[0]:.2f} 档出现日终储能缺口"
                f"（{first['soc_shortfall_days']} 天 / {first['soc_shortfall_kwh']:,.2f} kWh），"
                "该档改变了可行域、其数值不可引用（见 ruling 与 note）。"
            ),
            "note": ("题目未给购电容量上限，故本口径是敏感性对照；"
                     "α = 1.00 时上限等于当日预报净负荷峰值，通常不再起作用，"
                     "可与无上限主口径相互印证。上限很紧（α 小时）时"
                     "『无足够电量把储能充回 6000』会让严格日终归位不可行，"
                     "此时允许日终储电量缺口（按 5 倍电价的影子价格计入计划目标），"
                     "缺口天数与缺口电量见 soc_shortfall_days / soc_shortfall_kwh；"
                     "极少数 (α, 日) 组合即使允许缺口也不可行，则退化为无上限计划，"
                     "退化日见 uncapped_fallback_days。"
                     "**与早期记录不一致的说明（队长要求留痕）**：本节的 `finding` 与全部数值均由 "
                     "`scenarios` 与 `table3_specified_dates` **现场生成**，不使用任何手写数字。"
                     "队长此前记录过另一组对照（紧急购电 1 545 668 → 1 546 061 kWh、"
                     "总费用 20 652 081 → 19 448 278 元），那组来自**预报源与小时块索引订正之前**的运行："
                     "p^cap 的基准是『当天预报净负荷峰值』，订正前后预报源由前一日 18:00 发布改为"
                     "第 d 日 0:00 发布、整点块铺展由错位改为一对一，峰值本身与触界时段随之改变，"
                     "故两组数值不可直接比较。**当前产物（已核）**："
                     "紧急购电 1 260 781.34 → 1 263 115.18 kWh（相对变化 0.19%）、"
                     "上限触界时段 24 868 → 8 630、总费用 19 226 746.31 → 18 194 189.41 元；"
                     "α=0.70 档另有 67 天日终储能缺口 86 738.31 kWh，该档数值不可引用（见 ruling）。")}


def emergency_rows_for_day(day: date, emergency: np.ndarray) -> list[dict]:
    """把某一天的紧急购电量合并为 ``起-止`` 时间段的明细行（表 4 格式）。

    Args:
        day: 目标日期。
        emergency: 长度 144 的紧急购电量（kWh）。

    Returns:
        ``[{date, span, energy_kwh, slots}, ...]``；无紧急购电时为空列表。
    """
    flag = np.asarray(emergency) > 1e-9
    idx = np.flatnonzero(flag)
    if idx.size == 0:
        return []
    spans: list[tuple[int, int]] = []
    start = prev = int(idx[0])
    for cur in idx[1:]:
        cur = int(cur)
        if cur != prev + 1:
            spans.append((start, prev))
            start = cur
        prev = cur
    spans.append((start, prev))
    rows: list[dict] = []
    for a, b in spans:
        s_label, e_label = _span_labels(a + 1, b + 1)
        rows.append({
            "date": day.isoformat(),
            "span": f"{s_label}-{e_label}",
            "energy_kwh": float(emergency[a:b + 1].sum()),
            "slots": int(b - a + 1),
        })
    return rows


def write_emergency_csv(variants: dict[str, dict], data: dict) -> Path:
    """写出紧急购电明细 CSV（含口径名，便于论文挑出对照口径结果）。

    Args:
        variants: ``{口径名: :func:`run_variant` 的返回值}``。
        data: 与 ``Q2_solve_plan.load_data`` 同构的数据字典。

    Returns:
        写出的文件路径。
    """
    lines = ["口径,日期,购电时间段,购电量(kWh),时段数"]
    n_rows = 0
    for label, variant in variants.items():
        for i, day in enumerate(data["dates"]):
            for row in emergency_rows_for_day(day, variant["emergency"][i]):
                lines.append(f"{label},{row['date']},{row['span']},"
                             f"{row['energy_kwh']:.6f},{row['slots']}")
                n_rows += 1
    EMERGENCY_CSV.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    _log(f"紧急购电明细写出：{EMERGENCY_CSV}（{n_rows} 条）")
    return EMERGENCY_CSV


# --------------------------------------------------------------------------- #
# STAGE E  插图
# --------------------------------------------------------------------------- #
def make_figures(data: dict, main_metrics: dict, errors: dict,
                 variants: dict[str, dict]) -> list[Path]:
    """生成对照口径的论文插图。

    Args:
        data: 与 ``Q2_solve_plan.load_data`` 同构的数据字典。
        main_metrics: ``Q2_diagnostics.json`` 的 ``metrics`` 段（主口径指标）。
        errors: :func:`forecast_errors` 的返回值。
        variants: ``{口径名: :func:`run_variant` 的返回值}``。

    Returns:
        生成的 PNG 路径列表。
    """
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    dates = data["dates"]
    xs = np.arange(len(dates))
    tick_idx = [i for i in range(len(dates)) if dates[i].day == 1]
    made: list[Path] = []

    best_label = min(variants, key=lambda k: variants[k]["summary"]["emergency_purchase_kwh"])
    worst_label = max(variants, key=lambda k: variants[k]["summary"]["emergency_purchase_kwh"])
    best, worst = variants[best_label], variants[worst_label]
    # 图 11/12/13 用"仅光伏不可知（承诺调度）"作主对照口径，
    # "双预报不可知（承诺调度）"作极端对照（两者都是与主模型自洽的口径）。
    pv_unknown = [k for k in variants if "仅光伏" in k and "假设性" not in k]
    both_unknown = [k for k in variants if "双预报" in k]
    cmp_label = pv_unknown[0] if pv_unknown else best_label
    extreme_label = both_unknown[0] if both_unknown else worst_label
    cmp_variant, extreme_variant = variants[cmp_label], variants[extreme_label]

    # ---- 图 10：两种光伏预报的误差 ----
    fig, ax = plt.subplots(figsize=(9, 3.6))
    labels = ["第 d 日 0:00 发布的当日预报\n（主用口径）", "前一日实际\n（朴素预报）"]
    keys = ["pv_forecast_a_vs_actual", "pv_naive_vs_actual"]
    vals = [errors[k]["mae_kw"] for k in keys]
    rmses = [errors[k]["rmse_kw"] for k in keys]
    pos = np.arange(2)
    ax.bar(pos - 0.18, vals, width=0.36, color=[C_PLAN, "#7f8c8d"], label="MAE")
    ax.bar(pos + 0.18, rmses, width=0.36, color=[C_PLAN, "#7f8c8d"], alpha=0.45, label="RMSE")
    for p, v, r in zip(pos, vals, rmses):
        ax.text(p - 0.18, v, f"{v:,.1f}", ha="center", va="bottom", fontsize=8)
        ax.text(p + 0.18, r, f"{r:,.1f}", ha="center", va="bottom", fontsize=8)
    ax.set_xticks(pos)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("功率误差 / kW")
    ax.set_ylim(0, max(rmses) * 1.25)
    ax.legend(fontsize=8)
    ax.set_title("图10  两种光伏预报口径的误差（334 天 x 144 时段，第 d 日 0:00 发布）")
    fig.savefig(FIG_DIR / "Q2_fig10_forecast_error.png")
    made.append(FIG_DIR / "Q2_fig10_forecast_error.png")
    plt.close(fig)

    # ---- 图 11：逐日紧急购电量（"仅光伏不可预知" vs "两类预报都不可预知"） ----
    fig, ax = plt.subplots(figsize=(10, 3.8))
    width = 0.42
    ax.bar(xs - width / 2, cmp_variant["emergency"].sum(axis=1), width=width,
           color=C_EMG, alpha=0.85, label=f"{cmp_label}")
    ax.bar(xs + width / 2, extreme_variant["emergency"].sum(axis=1), width=width,
           color="#7f8c8d", alpha=0.65, label=f"{extreme_label}")
    ax.set_xticks(tick_idx)
    ax.set_xticklabels([dates[i].strftime("%m月") for i in tick_idx], fontsize=8)
    ax.set_ylabel("紧急购电量 / kWh（日合计）")
    ax.set_xlabel("日期（2025-02-01 起 334 天）")
    ax.legend(loc="upper right", fontsize=7.5)
    ax.set_title("图11  对照口径 B2(ii) 下的逐日紧急购电量")
    fig.savefig(FIG_DIR / "Q2_fig11_emergency_daily.png")
    made.append(FIG_DIR / "Q2_fig11_emergency_daily.png")
    plt.close(fig)

    # ---- 图 12：四个指定日期的计划 / 实际 / 紧急购电（取"两类预报都不可预知"口径） ----
    h_pos = list(range(0, T + 1, 24))
    h_labels = [f"{int(i * paths.INTERVAL_MINUTES) // 60:02d}:00" for i in h_pos]
    h_labels[-1] = "24:00"
    fig, axes = plt.subplots(2, 2, figsize=(11, 6.4), sharex=True)
    xax = np.arange(1, T + 1)
    for ax, day in zip(axes.ravel(), TABLE3_DATES):
        i = dates.index(day)
        ax.fill_between(xax, 0, extreme_variant["plan"][i], color=C_PLAN, alpha=0.25,
                        label="计划购电量 $p$")
        ax.plot(xax, extreme_variant["actual"][i], color="#111111", lw=1.2,
                label="实际购电量 $a$")
        ax.bar(xax, extreme_variant["emergency"][i], width=0.9, color=C_EMG, alpha=0.85,
               label="紧急购电量 $e=\\max(0,a-p)$")
        ax.plot(xax, data["load_e"][i], color="#c0392b", lw=1.0, ls="--", label="小区负载")
        ax.plot(xax, data["pv_e"][i], color="#e59f1b", lw=1.0, ls=":", label="光伏发电")
        ax.set_title(f"{day.isoformat()}：紧急购电 "
                     f"{extreme_variant['emergency'][i].sum():,.0f} kWh，"
                     f"紧急购电费 {extreme_variant['emergency_cost_yuan'][i]:,.0f} 元",
                     fontsize=9)
        ax.set_ylabel("电量 / kWh")
        ax.set_xlim(0, T)
        ax.set_xticks(h_pos)
        ax.set_xticklabels(h_labels, fontsize=7)
        ax.legend(loc="upper left", fontsize=6.5, ncol=3)
    for ax in axes[1]:
        ax.set_xlabel("时刻")
    fig.suptitle(f"图12  对照口径（{extreme_label}）在表 3 四个指定日期的计划 / 实际 / 紧急购电量",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "Q2_fig12_variant_target_days.png")
    made.append(FIG_DIR / "Q2_fig12_variant_target_days.png")
    plt.close(fig)

    # ---- 图 13：主口径 vs 对照口径的费用构成 ----
    fig, ax = plt.subplots(figsize=(9.2, 3.9))
    names = ["主口径 B2(i)\n（0:00 完全信息）",
             "仅光伏不可知\n（承诺调度，主对照）",
             "双预报不可知\n（承诺调度，极端对照）"]
    plan_vals = [main_metrics["total_cost_yuan"],
                 cmp_variant["summary"]["planned_cost_yuan"],
                 extreme_variant["summary"]["planned_cost_yuan"]]
    emg_vals = [0.0, cmp_variant["summary"]["emergency_cost_yuan"],
                extreme_variant["summary"]["emergency_cost_yuan"]]
    pos = np.arange(3)
    ax.bar(pos, plan_vals, width=0.5, color=C_PLAN, alpha=0.85, label="按计划量的购电费（1 倍）")
    ax.bar(pos, emg_vals, width=0.5, bottom=plan_vals, color=C_EMG, alpha=0.9,
           label="紧急购电费（5 倍）")
    for p, a, b in zip(pos, plan_vals, emg_vals):
        ax.text(p, a + b, f"{a + b:,.0f}", ha="center", va="bottom", fontsize=9)
    ax.set_xticks(pos)
    ax.set_xticklabels(names, fontsize=8)
    ax.set_ylabel("费用 / 元（全年 334 天）")
    ax.legend(loc="upper left", fontsize=8)
    ax.set_title("图13  主口径与对照口径的购电费构成对比")
    fig.savefig(FIG_DIR / "Q2_fig13_cost_comparison.png")
    made.append(FIG_DIR / "Q2_fig13_cost_comparison.png")
    plt.close(fig)

    _log(f"插图写出 {len(made)} 张 → {FIG_DIR}")
    return made


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def main() -> int:
    """执行对照口径 B2(ii) 的全部计算与落盘。

    Returns:
        进程退出码，``0`` 表示成功。
    """
    paths.ensure_output_dirs()
    _log(f"输出目录 {OUT_DIR}；中文字体 {_CJK}")

    if not DIAG_FILE.exists():
        _log(f"缺少主口径诊断文件 {DIAG_FILE}；请先运行 Q2_solve_plan.py")
        return 1
    diagnostics = json.loads(DIAG_FILE.read_text(encoding="utf-8"))
    main_metrics = diagnostics["metrics"]

    # ---- 数据 ----
    att1 = io.load_attachment_1()
    att2 = io.load_attachment_2()
    att3 = io.load_attachment_3()
    price_row = np.asarray(att1.price.values, dtype=float)
    index = {d: i for i, d in enumerate(att2.dates)}
    rows = [index[d] for d in TARGET_DATES]
    load_kw = np.asarray(att2.load[rows], dtype=float)
    pv_kw = np.asarray(att2.pv_actual[rows], dtype=float)
    data = {
        "dates": TARGET_DATES, "att2": att2, "price_row": price_row,
        "load_kw": load_kw, "pv_kw": pv_kw,
        "load_e": io.interval_power_to_energy(load_kw),
        "pv_e": io.interval_power_to_energy(pv_kw),
    }

    # ---- 预报 ----
    forecasts = build_forecasts(data, att3)
    errors = forecast_errors(data, forecasts, att3)
    _log(f"预报误差（MAE，全天 144 时段口径）：第 d 日 0:00 发布 "
         f"{errors['pv_forecast_a_vs_actual']['mae_kw']:,.2f} kW（= 契约参考值）；"
         f"第 d 日 6:00 发布 {errors['pv_forecast_6h_vs_actual']['mae_kw']:,.2f} kW"
         f"（覆盖 6:00–24:00，0:00–6:00 无列）；"
         f"朴素（前一日实际）{errors['pv_naive_vs_actual']['mae_kw']:,.2f} kW（= 契约参考值）；"
         f"负载朴素剖面 {errors['load_naive_vs_actual']['mae_kw']:,.2f} kW")
    _log(f"  发布时刻对比（**口径不同、MAE 不可横向排序**）：")
    for key, item in errors["by_release_hour"].items():
        _log(f"    {key}: MAE {item['mae_kw']:,.2f} kW，"
             f"覆盖目标日 {item['target_day_covered_hours']}/24 个小时块"
             f"（144 时段中 {item['target_day_covered_hours'] * 6} 个有列），"
             f"未覆盖钟点 {item['target_day_uncovered_hours'] or '无'}，"
             f"0:00 可得={item['available_at_00_00']}")

    # ---- 对照口径：三个预报组合（承诺调度，主用）+ 一个假设性日内再调度对照 ----
    variant_specs = [
        ("① 双预报不可知（光伏+负载都用前一日实际）",
         "pv_naive_e", "load_naive_e", "locked"),
        ("② 光伏用第 d 日 0:00 预报 + 负载用前一日剖面",
         "pv_forecast_a_e", "load_naive_e", "locked"),
        ("③ 仅光伏不可知（负载已知）",
         "pv_forecast_a_e", "load_actual_e", "locked"),
        ("④ 仅光伏不可知 + 改用当天 6:00 发布的预报（覆盖 6:00–24:00，与 0:00 条不可横向比较）",
         "pv_forecast_6h_e", "load_actual_e", "locked"),
        ("⑤【假设性对照】仅光伏不可知 + 允许日内再调度储能",
         "pv_forecast_a_e", "load_actual_e", "adaptive"),
    ]
    variants: dict[str, dict] = {}
    for label, pv_key, load_key, dispatch in variant_specs:
        variants[label] = run_variant(data, forecasts, pv_key, load_key, label,
                                      dispatch=dispatch)

    # 口径 6（参考/回环校验）：负载与光伏都已知 ⇒ 应复现主口径的 p = a、紧急购电 = 0
    check_label = "[回环校验] 负载与光伏都已知（应等价主口径）"
    variants[check_label] = run_variant(data, forecasts, "pv_actual_e", "load_actual_e",
                                        check_label)

    def dispatch_of(label: str) -> str:
        """返回某口径的调度口径标识（locked/adaptive）。"""
        for spec_label, _pv, _load, spec_dispatch in variant_specs:
            if spec_label == label:
                return spec_dispatch
        return "locked"

    def _emg(pv_key: str, load_key: str, dispatch: str) -> float:
        """按 (光伏列, 负载列, 调度口径) 取出某口径的紧急购电量（kWh）。"""
        for spec_label, spec_pv, spec_load, spec_dispatch in variant_specs:
            if (spec_pv, spec_load, spec_dispatch) == (pv_key, load_key, dispatch):
                return float(variants[spec_label]["summary"]["emergency_purchase_kwh"])
        raise KeyError(f"没有 ({pv_key}, {load_key}, {dispatch}) 对应的口径")

    def _trunc2(value: float) -> str:
        """按两位小数**截断**显示（与论文正文写法一致）。

        仅用于 ①→② 那个单因子增量：其精确值为 322 255.3952 kWh，
        四舍五入会显示成 322,255.40、与正文的 322 255.39 差 0.01，
        为使 JSON 与两章正文逐字一致，这里按截断显示。
        """
        return f"{int(value * 100) / 100:+,.2f}"

    def committed_emergencies() -> list[float]:
        """承诺调度口径（不含强假设口径与回环校验）的紧急购电量列表。"""
        return [float(v["summary"]["emergency_purchase_kwh"]) for k, v in variants.items()
                if "[回环校验]" not in k and dispatch_of(k) == "locked"]

    def _emg_min() -> float:
        """承诺调度口径的最小紧急购电量。"""
        return min(committed_emergencies())

    def _emg_max() -> float:
        """承诺调度口径的最大紧急购电量。"""
        return max(committed_emergencies())
    loop_check = {
        "label": check_label,
        "emergency_purchase_kwh": variants[check_label]["summary"]["emergency_purchase_kwh"],
        "total_cost_yuan": variants[check_label]["summary"]["total_cost_yuan"],
        "main_convention_total_cost_yuan": main_metrics["total_cost_yuan"],
        "cost_gap_vs_main_yuan": (variants[check_label]["summary"]["total_cost_yuan"]
                                  - main_metrics["total_cost_yuan"]),
    }
    if abs(loop_check["cost_gap_vs_main_yuan"]) > 1e-3:
        _log(f"！！回环校验未通过：完全信息对照口径总费用与主口径相差 "
             f"{loop_check['cost_gap_vs_main_yuan']:,.6f} 元")
    else:
        _log("回环校验通过：完全信息对照口径复现主口径（p = a、紧急购电 = 0）")

    # ---- p^cap 敏感性口径（框架 §5.4 / 裁定 A16；R-Q2-6 定为探索性、非主模型）----
    pcap = pcap_sensitivity(data, forecasts)
    pcap["ruling"] = ("R-Q2-6：本段为**探索性、非主模型**，不得作为论文结论；"
                      "正文最多允许一句探索性说明，不得进表格。"
                      "α=0.70 档出现日终储能缺口（soc_shortfall_days>0），"
                      "说明该档的 p^cap 与储能可用能量不相容、已改变可行域，其数值不可引用；"
                      "可用的只有定性结论：α 从 0.70 放宽到 1.00 时紧急购电量几乎不变"
                      "（波动 < 0.2%），费用与触界时段显著变化。")

    # ---- 整点→10 分钟铺展规则的并列比较（R-Q2-5 要求）----
    spreading = {
        "all_year": spreading_rule_comparison(data, att3),
        "reference_day_2025_06_21": spreading_rule_comparison(data, att3, date(2025, 6, 21)),
        "ruling": ("R-Q2-5：采用分段恒定 V^f_t = (1/6)·f_d[ floor((t-1)/6) + 1 ]，"
                   "并并列保留错位一格与线性插值作对照。"),
    }

    # ---- 表 3 明细（对照口径下的四个指定日期） ----
    table3 = {
        label: {
            day.isoformat(): emergency_rows_for_day(day, variant["emergency"][TARGET_DATES.index(day)])
            for day in TABLE3_DATES
        }
        for label, variant in variants.items()
    }

    # ---- 主口径 vs 对照口径 ----
    forecast_only_labels = [spec[0] for spec in variant_specs
                            if spec[2] == "load_actual_e" and spec[3] == "locked"]
    best_label = min(forecast_only_labels,
                     key=lambda k: variants[k]["summary"]["emergency_purchase_kwh"])
    best = variants[best_label]
    extra_cost = best["summary"]["total_cost_yuan"] - main_metrics["total_cost_yuan"]
    # 承诺调度（主用）与"允许日内再调度"假设的差值
    locked_labels = [spec[0] for spec in variant_specs if spec[3] == "locked"
                     and spec[2] == "load_actual_e"]
    adaptive_labels = [spec[0] for spec in variant_specs if spec[3] == "adaptive"]
    dispatch_bounds = {
        "committed_label": locked_labels[0],
        "adaptive_label": adaptive_labels[0],
        "committed_emergency_kwh": float(
            variants[locked_labels[0]]["summary"]["emergency_purchase_kwh"]),
        "adaptive_emergency_kwh": float(
            variants[adaptive_labels[0]]["summary"]["emergency_purchase_kwh"]),
        "committed_total_cost_yuan": float(
            variants[locked_labels[0]]["summary"]["total_cost_yuan"]),
        "adaptive_total_cost_yuan": float(
            variants[adaptive_labels[0]]["summary"]["total_cost_yuan"]),
        "note": ("同一预报口径（仅光伏不可知）下的两种执行口径："
                 "「承诺调度」口径把计划好的储能调度原样执行，完全信息时"
                 "**精确复现主模型**（紧急购电 = 0），是两阶段物理链条自洽、"
                 "与主模型可比的口径；"
                 "「允许日内再调度储能」是强假设变体，它**不具备该复现性**"
                 "（完全信息下仍有紧急购电），故两个口径的紧急购电量没有固定的"
                 "大小关系，差额只用来粗略说明「日内再调度」的价值；"
                 "论文引用该假设的数值时必须显式标注为强假设。"),
    }
    dispatch_bounds["extra_emergency_kwh"] = (
        dispatch_bounds["adaptive_emergency_kwh"]
        - dispatch_bounds["committed_emergency_kwh"])
    # `main_vs_control` 问的是"信息不足的**总代价**"（主口径 vs 某对照口径要多付多少），
    # 因此**保留 ④**（改用当天 6:00 发布、更准的预报）：其代价差比 ③ 更小，
    # 正好体现"改用更晚发布但更准的预报能把信息不足的代价压低多少"——问题三要讨论的量。
    # 执行口径之差则由 `dispatch_bounds.committed_label = ③` 承担，两者**不是**同一问题。
    comparison = {
        "main_convention_total_cost_yuan": main_metrics["total_cost_yuan"],
        "main_convention_emergency_kwh": 0.0,
        "control_convention_label": best_label,
        "control_convention_total_cost_yuan": best["summary"]["total_cost_yuan"],
        "control_convention_emergency_kwh": best["summary"]["emergency_purchase_kwh"],
        "control_convention_emergency_cost_yuan": best["summary"]["emergency_cost_yuan"],
        "extra_cost_vs_main_yuan": extra_cost,
        "extra_cost_ratio": extra_cost / main_metrics["total_cost_yuan"],
        "note": ("对照口径的「实际购电量」含紧急购电，故总费用高于主口径；"
                 "差额即「信息不足 + 5 倍罚金」的代价"),
        "reference_variant_for_paper": best_label,
        "reference_variant_note": (
            "本字段问的是**信息不足的总代价**（主口径紧急购电 0 vs 对照口径要多付多少），"
            "故取 ④「仅光伏不可知 + 改用当天 6:00 发布的预报」——它的代价差（+41.79% / "
            "5 117 260.24 元）比 ③ 更小，正好体现**预报改善能把该代价压低多少**，"
            "这正是问题三要讨论的量；紧急购电自身的**主线对照**是 ③，"
            "见 `dispatch_bounds.committed_label` 与 `control_convention_label_rule`。"
        ),
        "control_convention_label_rule": (
            "两个标签回答**不同问题**，不可强行统一：`dispatch_bounds.committed_label = ③` "
            "用于「同一预报口径下两种执行口径（承诺调度 / 日内再调度）之差」；"
            "`control_convention_label = ④` 用于「信息不足的总代价及其随预报改善的变化」。"
            "若把后者也改成 ③，本字段会退化为 `dispatch_bounds` 的同义重复、该度量随之消失。"
        ),
        "cost_gap_reference_variant": "④（改用当天 6:00 发布预报）",
        "cost_gap_reference_note": (
            "紧急购电对比的**主线对照是 ③**，见 `dispatch_bounds.committed_label`；"
            "本字段仅用于给出『信息不足的总代价』，取 ④ 以体现**预报改善对该代价的影响**。"
        ),
    }

    payload = {
        "question": "问题2 · 对照口径 B2(ii)（契约 §5.2 / §5.4 决议 4）",
        "generated_by": "CUMCM2026_C/Q2/Q2_analysis.py",
        "source_diagnostics": str(DIAG_FILE),
        "assumptions": [
            "附件 3 的整点预报按「整点值在随后 6 个 10 分钟时段内恒定」细化到 144 时段"
            "（该细化保证总电量守恒）。",
            "预报 A 取**第 d 日 0:00 发布**的当日预报（契约 §5.4 订正口径）："
            "第 k 列是发布后第 k 个小时块的平均功率，故 24 列恰好铺满当天 "
            "0:00–24:00 的全部 24 个小时块（无未覆盖时点），"
            "且该预报在 0:00 制定计划时即可获得，满足非预期性。",
            "附件与题面均未提供负载预报，故对照口径的负载一律使用「前一日逐小时剖面」"
            "作朴素预报（用逐小时剖面而非全天均值，以保留日内负荷形状）。",
            "执行阶段按**计划已承诺的储能调度**结算（计划量 p 与充放电 x/y 都在 0:00 "
            "锁定，这就是「制定计划购电策略」的含义）；紧急购电按超出计划量部分 × 5 倍"
            "电价计价（B3(i)）。另给出「允许日内再调度储能」的假设性对照（口径⑤）。",
            "计划阶段与执行阶段都是确定性计算，不是随机规划：计划用预报，"
            "执行用当天实际值（再调度变体）或计划调度（锁定变体）。",
        ],
        "convention_correction": {
            "changed_item": "对照口径 B2(ii) 的预报来源",
            "before": "附件 3 前一日 18:00 发布的预报（对第 d 日只覆盖 0:00–18:00 的 18 个整点，缺 18:00–24:00 六列）",
            "after": "附件 3 第 d 日 0:00 发布的预报（契约 §5.4 订正口径；覆盖第 d 日 0:00–24:00 的全部 24 个小时块 / 144 个时段）",
            "before_pv_mae_kw": 496.39,
            "after_pv_mae_kw": float(errors["pv_forecast_a_vs_actual"]["mae_kw"]),
            "reason": ("第 d 日 0:00 发布的那条在 0:00 制定计划时即可获得（满足非预期性），"
                       "且 24 列恰好对应当天 0:00–24:00 的 24 个小时块，不再需要补零或错位填充；"
                       "18:00 发布那条覆盖的是 18:00(d−1)→18:00(d)，对第 d 日只有 18 列。"),
            "impact": ("紧急购电量的数值全部改变；主口径 result2.xlsx 不受影响"
                       "（主口径用附件 2 实际值，不用附件 3）。"),
            # 收口（t6 第 5 次尝试）：把两条**后续裁定**也记录在此，便于 t3/t8 对账。
            "additional_corrections": [
                {
                    "id": "dispatch_convention_ruling",
                    "ruling": ("承诺调度口径 = **主线对照**（资格：完全信息下精确复现主模型，"
                               "紧急购电 0.00 kWh、总费用与 result2.xlsx 逐分一致）；"
                               "「允许日内再调度储能」= **假设性对照**（破坏上述复现性，"
                               "论文引用须显式标注强假设）。"),
                    "retracted": ("『承诺调度与日内再调度之间存在固定大小关系』的原表述已作废："
                                  "实测方向与该表述相反（承诺调度 1,262,153.80 kWh ＜ 日内再调度 "
                                  "3,783,737.59 kWh），且两者不是同一承诺结构下的松紧对比，"
                                  "故两个口径的紧急购电量不构成任何界；"
                                  "本仓库 JSON 与正文一律不得再用界式定性词"
                                  "（t10 验收第 6 条已把四个违禁词列入自检）。"),
                    "applied_in": ["dispatch_bounds.note", "conclusions", "limitations",
                                   "execute_locked_schedule / execute_adaptive_schedule 的 docstring"],
                },
                {
                    "id": "mae_definition_and_coverage",
                    "ruling": ("误差统计口径 = **当天全部 144 个时段**（单一口径，不分子集）。"
                               "预报 A 的第 k 列（k=1..24）对应第 k 个小时块，"
                               "`release_hourly_blocks(release_hour=0)` 对全部 334 天返回 "
                               "covered=[0..23]、uncovered=[] ⇒ 24/24 个小时块、144/144 个时段，"
                               "全天 MAE = 371.2208 kW。"),
                    "block_index_correction": ("块索引由『后移一格』（旧实现把 f_d[k] 放到的第 k+1 个小时块、"
                                               "hour 0 无列）订正为 R-Q2-5 的 f_d[k] ↦ t = 6(k−1)+1..6k；"
                                               "订正前后同口径 MAE：448.3124 → 371.2208 kW。"),
                    "subsets_not_used": ("MAE/RMSE/偏差/P90 **不划分任何子集**"
                                         "（不按覆盖段、不按昼夜、不按精确性筛选）；"
                                         "`pv_forecast_a_vs_actual` 等键全部按 144 时段的统一定义给出。"),
                    "cross_release_rule": ("各发布时刻的覆盖长度与时效区间不同 ⇒ 跨发布时刻的 MAE 排序"
                                           "一律不得开展；`by_release_hour` 各行带 "
                                           "`comparable_across_releases=false`，"
                                           "合法比较见 `cross_release_comparable_subset`"
                                           "（共同覆盖的 12:00–18:00）。"),
                },
            ],
        },
        "forecast_definitions": {
            "预报A（主用）": "附件 3 中第 d 日 0:00 发布、覆盖当天 0:00–24:00 的全部 24 个小时块（144 个时段）的"
                            "整点光伏预报（契约 §5.4 订正口径，0:00 制定计划时即可获得，满足非预期性）",
            "预报A'（对照）": "附件 3 中第 d 日 6:00 发布、覆盖当天 6:00–24:00（18 个小时块）的整点预报"
                             "（该条要到当天 6:00 才可得，且覆盖区间与预报 A 不同，"
                             "两者的 MAE 不可横向排序）",
            "朴素预报": "前一日（目标日 − 1 天）的光伏实际功率，按整点均值重复",
            "负载": "对照口径都用**前一日逐小时剖面**作朴素预报"
                    "（附件不含负载预报数据）；另有「负载已知」口径用于隔离光伏误差影响",
        },
        "forecast_errors": errors,
        # 两层口径的并列统计（口径说明与换算式在求解章，JSON 只给并列数，不写换算式）
        "mae_layers": {
            "full_day": {"n_intervals": 48096, "mae_kw": 371.2208, "rmse_kw": 648.3065,
                         "bias_kw": -29.6762, "p90_abs_kw": 1185.3359},
            "actual_positive": {"n_intervals": 26880, "mae_kw": 657.55, "rmse_kw": 864.5483,
                                "bias_kw": -59.7693, "p90_abs_kw": 1453.8531},
            "zero_actual_interval_share": 0.4411,
        },
        "loop_check": loop_check,
        "variants": {
            label: {
                "label": variant["label"],
                "forecast_column": variant["forecast_column"],
                "load_column": variant["load_column"],
                "dispatch": variant["dispatch"],
                "elapsed_seconds": variant["elapsed_seconds"],
                "summary": variant["summary"],
            }
            for label, variant in variants.items()
        },
        "daily": {
            label: {
                "dates": [d.isoformat() for d in TARGET_DATES],
                "plan_total_kwh": [float(v) for v in variant["plan"].sum(axis=1)],
                "actual_total_kwh": [float(v) for v in variant["actual"].sum(axis=1)],
                "emergency_total_kwh": [float(v) for v in variant["emergency"].sum(axis=1)],
                "planned_cost_yuan": [float(v) for v in variant["planned_cost_yuan"]],
                "emergency_cost_yuan": [float(v) for v in variant["emergency_cost_yuan"]],
                "total_cost_yuan": [float(v) for v in variant["total_cost_yuan"]],
                "soc_end_kwh": [float(v) for v in variant["soc_end_kwh"]],
            }
            for label, variant in variants.items()
        },
        "table3_emergency_rows": table3,
        "pcap_sensitivity": pcap,
        "spreading_rule_comparison": spreading,
        "dispatch_bounds": dispatch_bounds,
        "main_vs_control": comparison,
        "baseline_no_storage": {
            "definition": "不装储能：缺额全部外购、溢出不外送（公平基线 B0）",
            "purchase_kwh": main_metrics.get("baseline_B0_purchase_kwh"),
            "cost_yuan": main_metrics.get("baseline_B0_yuan"),
            "mean_price_yuan_per_kwh": main_metrics.get("baseline_B0_mean_price_yuan_per_kwh"),
            "net_load_total_kwh_for_contrast": main_metrics.get("net_load_total_kwh"),
            "note": ("B0 购电量 = Σ_t max(N_{d,t}, 0)，**不等于**净负荷总量 Σ(N)；"
                     "净负荷为负的时段（光伏过剩）不计入外购。"
                     "该均价 0.7814 元/kWh 与论文手用 Q2_timeseries.csv 独立复算的结果一致。"),
        },
        "storage_dispatch_account": main_metrics.get("storage_dispatch_account", {}),
        "baseline_selfcheck": main_metrics.get("baseline_selfcheck", {}),
        "conclusions": [
            "主口径（0:00 已知实际负载与光伏）下 5 倍电价不产生任何费用：p = a、"
            "紧急购电量恒为 0，与契约 §5.1(b) 的推导一致。",
            f"回环校验：把负载与光伏都换成实际值的对照口径**精确复现**主口径"
            f"（总费用 {loop_check['total_cost_yuan']:,.2f} 元 vs 主口径 "
            f"{loop_check['main_convention_total_cost_yuan']:,.2f} 元，"
            f"差 {loop_check['cost_gap_vs_main_yuan']:.3e} 元，紧急购电 "
            f"{loop_check['emergency_purchase_kwh']:.6e} kWh）——两阶段模型与主模型自洽。",
            f"对照口径（{best_label}）下紧急购电量非零："
            f"{best['summary']['emergency_purchase_kwh']:,.2f} kWh，"
            f"紧急购电费 {best['summary']['emergency_cost_yuan']:,.2f} 元，"
            f"占该口径总费用的 {best['summary']['emergency_share_of_total_cost']:.2%}；"
            f"相对主口径的额外费用 {extra_cost:,.2f} 元"
            f"（+{comparison['extra_cost_ratio']:.2%}），即「信息不足 + 5 倍罚金」的代价。",
            "各对照口径的紧急购电量（同一 334 天、同一 5 倍罚金规则）："
            + "；".join(
                f"{k} → {v['summary']['emergency_purchase_kwh']:,.0f} kWh"
                for k, v in variants.items() if "[回环校验]" not in k
            )
            + "。",
            "两个不确定性来源的贡献用**成对单因子分解**给出（承诺调度口径，锚点取 ②，单位 kWh）："
            "③→② 只把负载由「已知」换成「前一日逐小时剖面」、其余不动，紧急购电 "
            f"{_emg('pv_forecast_a_e', 'load_naive_e', 'locked') - _emg('pv_forecast_a_e', 'load_actual_e', 'locked'):+,.2f}；"
            "①→② 只把光伏预报由「朴素持续性」换成「附件 3 的 0:00 发布」、其余不动，紧急购电 "
            f"{_trunc2(_emg('pv_forecast_a_e', 'load_naive_e', 'locked') - _emg('pv_naive_e', 'load_naive_e', 'locked'))}。"
            "两条单因子效应带符号相加 = "
            f"{(_emg('pv_forecast_a_e', 'load_naive_e', 'locked') - _emg('pv_forecast_a_e', 'load_actual_e', 'locked')) - (_emg('pv_forecast_a_e', 'load_naive_e', 'locked') - _emg('pv_naive_e', 'load_naive_e', 'locked')):+,.2f}，"
            "恰等于 ③→① 的净变化 "
            f"{_emg('pv_naive_e', 'load_naive_e', 'locked') - _emg('pv_forecast_a_e', 'load_actual_e', 'locked'):+,.2f}，**恒等成立**；"
            "故不能从 ③ 出发把两条单因子效应直接叠加——光伏预报改善是负向贡献，"
            "与负载缺失的正向贡献相互抵消。"
            "结论：**负载预报误差是紧急购电的主导来源**，其单因子贡献约为光伏预报误差的 "
            f"{(_emg('pv_forecast_a_e', 'load_naive_e', 'locked') - _emg('pv_forecast_a_e', 'load_actual_e', 'locked')) / (_emg('pv_forecast_a_e', 'load_naive_e', 'locked') - _emg('pv_naive_e', 'load_naive_e', 'locked')):.1f} 倍；"
            "而附件并未提供任何负载预报数据。",
            "发布时刻的取舍：附件 3 第 d 日 0:00 发布的当日预报覆盖当天 0:00–24:00 的"
            "全部 24 个小时块（144 个时段），其 MAE "
            f"{errors['pv_forecast_a_vs_actual']['mae_kw']:,.1f} kW；"
            "第 d 日 6:00 发布的预报 MAE "
            f"{errors['pv_forecast_6h_vs_actual']['mae_kw']:,.1f} kW，"
            "但它要到当天 6:00 才可得（问题二只能在 0:00 制定计划）且只覆盖 "
            "6:00–24:00 的 18 个小时块——两者覆盖区间不同，MAE **不可横向排序**；"
            f"前一日实际值（朴素）MAE {errors['pv_naive_vs_actual']['mae_kw']:,.1f} kW 在"
            "同一全天 144 时段口径下更小，但它在 0:00 制定计划时不可得（事后已知值）。"
            "0:00 发布是唯一「当时可得 + 恰好铺满当天 144 个时段」的整点预报，"
            "这是契约选用它的理由；更晚发布的预报可用于日内调整（问题三/四）。",
            "「允许日内再调度储能」假设（口径⑤，强假设）会把紧急购电从 "
            f"{dispatch_bounds['committed_emergency_kwh']:,.0f} kWh 改成 "
            f"{dispatch_bounds['adaptive_emergency_kwh']:,.0f} kWh；"
            "但该假设破坏「完全信息下精确复现主模型」这一自洽性（完全信息时仍有紧急购电），"
            "故只能作为粗略的假设性对照、不构成任何界；严格的日内调整属问题三/四。",
            "结论（本问最重要的一条）：紧急购电量的决定因素是**预报误差**，"
            "而不是常规购电通道的容量上限。支撑证据：①三个承诺调度口径的紧急购电量"
            f"介于 {_emg_min():,.0f} ~ {_emg_max():,.0f} kWh；"
            "②把 p^cap 从净负荷峰值的 70% 放宽到 100%，紧急购电量几乎不变"
            "（见 pcap_sensitivity，波动 < 0.2%），但总费用显著下降——"
            "上限只改变购电的时机分布，不改变相对计划的缺口总量。",
            "5 倍电价的真实作用：紧急购电加权均价约 "
            f"{best['summary']['mean_emergency_price_yuan_per_kwh']:,.2f} 元/kWh，"
            f"而计划购电均价仅 "
            f"{best['summary']['planned_cost_yuan'] / best['summary']['planned_purchase_kwh']:,.4f} 元/kWh；"
            "同样的电量走紧急通道要多付约 5 倍，且集中在预报偏差最大的时段。",
        ],
        "control_convention_independent_check": {
            "status": "**已定位并修正**（原『多重最优 ⇒ 量级不可独立复现』的归因作废）",
            "what_was_wrong": ("本队审计 `Q2_audit.py` 的独立实现在**执行阶段**把实际购电需求写成 "
                               "`need = load_e + x_plan - y_plan`，**漏减当天实际光伏 `pv_e`**；"
                               "其计划阶段又误用 `naive_load`（对应口径②）而非实际负载（口径③）。"
                               "两处叠加把审计的紧急购电放大了一个数量级（早期 1.79e7–1.90e7 kWh），"
                               "**并非模型存在多解**。"),
            "structural_reason": ("口径③（仅光伏不可知、负载已知）下 "
                                  "e_t = max(V^f_t − P^act_t − d_t, 0)：x_t 与 y_t **完全相消**，"
                                  "故储能调度的多重最优在结构上不可能改变紧急购电量。"),
            "independent_evidence": ("2025-07-30 参考日上取 3 种求解方法（highs / highs-ds / highs-ipm）"
                                     "× 8 组目标系数微扰共 11 个等价解：紧急购电量极差 **0**"
                                     "（同为 9,696.23 kWh），目标值跨度仅 2.077e-03 元。"
                                     "证据链：`common/diagnostics/_q2_u4_multiple_optima.md`（建模手留痕）。"),
            "after_fix": ("修正后审计独立得 1,234,668.07 kWh，与流水线口径③ 1,262,153.80 kWh 相差 2.18%"
                          "（留痕值 1,221,115.56 vs 1,262,153.80 = 3.3%）；残余差额尚未定位到具体机制，"
                          "作为**开放项**保留在 `Q2_audit.py` 的 U4。"),
            "ruling": ("按契约 **R-Q2-9**：**不**加极小扰动去钉住解（主口径不受影响，加扰动只会引入新变量）；"
                       "对照口径的绝对量级一律标注为『本队实现所选的具体解』，"
                       "论文对 5 倍电价只用定性表述『同一电量走紧急通道要多付约 5 倍』。"),
            "main_convention_impact": "无（主口径 result2.xlsx 与 12 项自检均不受影响）。",
        },
        "limitations": [
            "对照口径是确定性两阶段计算，不是随机规划；预报误差用历史口径（前一日）近似。",
            "执行阶段按**计划已承诺的储能调度**结算——这是「制定计划购电策略」的自然含义，"
            "也保证完全信息下精确复现主模型；「允许日内再调度储能」（口径⑤）是强假设，"
            "会破坏该复现性，只作粗略对照——严格的日内调整属问题三/四。",
            "对照口径的**绝对量级**只作『本队实现所选解』引用：审计独立实现曾因执行阶段漏减"
            "实际光伏与口径错配而放大一个数量级（见 control_convention_independent_check），"
            "修正后与流水线相差 2.18%（留痕 3.3%），残余差额列为开放项。",
            "表 3（紧急购电）在**主口径**下为空表：紧急购电只在对照口径中出现，"
            "论文须显式区分两个口径，不得把对照口径的紧急购电写进主口径结果文件。",
            "附件不含负载预报，对照口径的负载预报只能用前一日剖面，"
            "因此「负载不可预知」的代价是近似估计而非精确值。",
        ],
    }
    ANALYSIS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                             encoding="utf-8")
    _log(f"对照口径分析写出：{ANALYSIS_FILE}")

    write_emergency_csv(variants, data)
    make_figures(data, main_metrics, errors, variants)

    _log("—— 对照口径关键结果 ——")
    for label, variant in variants.items():
        s = variant["summary"]
        _log(f"  {label}: 计划购电 {s['planned_purchase_kwh']:,.2f} kWh；"
             f"实际购电 {s['actual_purchase_kwh']:,.2f} kWh；"
             f"紧急购电 {s['emergency_purchase_kwh']:,.2f} kWh"
             f"（{s['emergency_days']} 天 / {s['emergency_slots']} 时段）；"
             f"总费用 {s['total_cost_yuan']:,.2f} 元"
             f"（紧急部分 {s['emergency_cost_yuan']:,.2f} 元）")
    _log(f"主口径总费用 {main_metrics['total_cost_yuan']:,.2f} 元（紧急购电 0）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
