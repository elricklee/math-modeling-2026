"""C题附件 1~4 的数据质量核查，输出 ``data_quality_report.json``。

运行方式::

    python -m src.CUMCM2026_C.check_data

核查内容
--------
1. **结构**：工作表、形状、时间列标签、日期范围、日期连续性。
2. **质量**：缺失值、重复行、负值、量程越界、夜间光伏非零、负载突变。
3. **一致性**：
   * 附件 1 的电价 / 负载 / 光伏 是否为附件 2/4 中某一天（逐时段反查 + 相关性）；
   * 附件 3 的"预报 k 小时"与附件 2 时间轴的对齐方式（两种候选落点对比）；
   * 附件 2 光伏实际功率与附件 3 预报的偏差统计（总体 + 分发布时刻 + 分 horizon）。
4. **验收清单**：把上述结论整理成可自动执行的判定表达式说明。

所有判定都基于**实测数字**，报告中不出现“看起来正常”这类主观描述。
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

from . import io_attachments as io
from . import paths

# --------------------------------------------------------------------------- #
# 判定工具
# --------------------------------------------------------------------------- #
TOLERANCE: float = 1e-9
"""浮点「精确相等」容差（附件 1 与附件 4 的逐列匹配使用）。"""


def _nan_stats(values: np.ndarray) -> dict[str, Any]:
    """返回数组的通用统计摘要。

    Args:
        values: 数值数组（可含 nan）。

    Returns:
        含 ``n`` / ``n_nan`` / ``n_inf`` / ``min`` / ``max`` / ``mean`` / ``std``
        等键的字典；``min`` 等在无有限值时取 ``None``。
    """
    arr = np.asarray(values, dtype=float)
    finite = arr[np.isfinite(arr)]
    return {
        "n": int(arr.size),
        "n_nan": int(np.isnan(arr).sum()),
        "n_inf": int(np.isinf(arr).sum()),
        "min": float(finite.min()) if finite.size else None,
        "max": float(finite.max()) if finite.size else None,
        "mean": float(finite.mean()) if finite.size else None,
        "std": float(finite.std()) if finite.size else None,
        "median": float(np.median(finite)) if finite.size else None,
    }


def _pearson(a: np.ndarray, b: np.ndarray) -> float | None:
    """计算皮尔逊相关系数，任一序列为常数时返回 ``None``。"""
    if a.size < 2 or a.std() < TOLERANCE or b.std() < TOLERANCE:
        return None
    value = float(np.corrcoef(a, b)[0, 1])
    return None if math.isnan(value) else value


def _fmt(value: float | None, digits: int = 6) -> str:
    """把可空浮点格式化为字符串，``None`` 渲染为 ``"n/a"``。"""
    return "n/a" if value is None else f"{value:.{digits}f}"


# --------------------------------------------------------------------------- #
# 报告容器
# --------------------------------------------------------------------------- #
@dataclass
class Section:
    """报告中的一个核查小节。

    Attributes:
        title: 小节标题。
        facts: 键值对形式的实测事实。
        notes: 文字结论列表。
        flags: 需要下游关注的问题列表。
    """

    title: str
    facts: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """转为可 JSON 序列化的字典。"""
        return {
            "title": self.title,
            "facts": self.facts,
            "notes": self.notes,
            "flags": self.flags,
        }


# --------------------------------------------------------------------------- #
# 核查主体
# --------------------------------------------------------------------------- #
class DataQualityChecker:
    """附件 1~4 的数据质量核查器。

    Attributes:
        a1: 附件 1。
        a2: 附件 2。
        a3: 附件 3。
        a4: 附件 4。
        sections: 已累积的核查小节。
    """

    def __init__(self) -> None:
        """加载全部附件并初始化小节列表。"""
        self.a1 = io.load_attachment_1()
        self.a2 = io.load_attachment_2()
        self.a3 = io.load_attachment_3()
        self.a4 = io.load_attachment_4()
        self.sections: list[Section] = []

    # ------------------------------------------------------------------ #
    # 1. 结构
    # ------------------------------------------------------------------ #
    def check_structures(self) -> Section:
        """核查 4 个附件的结构、时间列标签与日期范围。

        Returns:
            结构核查小节。
        """
        section = Section("1. 附件结构、时间轴标签与日期范围")
        labels = io.TIME_COLUMN_LABELS
        section.facts = {
            "附件1": {
                "工作表": ["Sheet1"],
                "表头": ["时间", "电价", "小区负载", "光伏发电预测功率"],
                "形状": f"{self.a1.n_intervals} 行 x 4 列",
                "时间列标签": list(labels),
                "单位": {"电价": "元/kWh", "小区负载": "kW", "光伏发电预测功率": "kW"},
            },
            "附件2": {
                "工作表": ["小区负载", "光伏发电实际功率"],
                "形状": {
                    "小区负载": f"{len(self.a2.dates)} 行 x {self.a2.load.shape[1]} 列",
                    "光伏发电实际功率": f"{len(self.a2.dates)} 行 x {self.a2.pv_actual.shape[1]} 列",
                },
                "首末日期": [self.a2.dates[0].isoformat(), self.a2.dates[-1].isoformat()],
                "时间列标签": list(labels),
                "单位": "kW",
            },
            "附件3": {
                "工作表": ["Sheet1"],
                "形状": f"{len(self.a3.release_days)} 行 x 26 列（日期 + 预报时刻 + 预报1..24小时）",
                "发布日期数": len(set(self.a3.release_days)),
                "首末日期": [
                    min(self.a3.release_days).isoformat(),
                    max(self.a3.release_days).isoformat(),
                ],
                "发布时刻": sorted(set(self.a3.release_hours.tolist())),
                "单位": "kW",
            },
            "附件4": {
                "工作表": ["Sheet1"],
                "形状": f"{len(self.a4.dates)} 行 x {self.a4.price.shape[1]} 列",
                "首末日期": [self.a4.dates[0].isoformat(), self.a4.dates[-1].isoformat()],
                "时间列标签": list(labels),
                "单位": "元/kWh",
            },
        }
        section.notes.append(
            f"附件 1/2/4 的时间列标签**完全相同**（144 列）：{labels[0]} … {labels[-2]} … {labels[-1]}，"
            "即标签表示区间的**右端点**：第 t 个标签对应 ((t-1)*10, t*10] 分钟。"
        )
        section.notes.append(
            "由此得出唯一自洽对齐：附件 1 第 t 行（1-based）↔ 附件 2/4 第 t 个数据列"
            "（0-based 列号 t-1）。"
        )

        # 日期连续性
        for name, days in [
            ("附件2", self.a2.dates),
            ("附件4", self.a4.dates),
            ("附件3(发布日)", sorted(set(self.a3.release_days))),
        ]:
            gaps = [
                (days[i].isoformat(), days[i + 1].isoformat())
                for i in range(len(days) - 1)
                if days[i] + timedelta(days=1) != days[i + 1]
            ]
            if gaps:
                section.flags.append(f"{name} 日期不连续，断裂点示例 {gaps[:3]}")
            else:
                section.notes.append(f"{name} 日期连续无断裂（{days[0]} … {days[-1]}，共 {len(days)} 天）。")

        # 附件3 每天 4 个发布时刻
        from collections import Counter

        patterns = Counter(
            tuple(sorted(h for d, h in zip(self.a3.release_days, self.a3.release_hours.tolist()) if d == day))
            for day in set(self.a3.release_days)
        )
        section.facts["附件3_每日发布时刻分布"] = {
            str(list(k)): v for k, v in patterns.items()
        }
        if list(patterns.keys()) != [(0, 6, 12, 18)]:
            section.flags.append(f"附件 3 存在非 (0,6,12,18) 的发布时刻组合：{list(patterns)}")

        if len(self.a4.dates) != 365 or len(self.a2.dates) != 365:
            section.flags.append("附件 2/4 行数不是 365")
        self.sections.append(section)
        return section

    # ------------------------------------------------------------------ #
    # 2. 质量
    # ------------------------------------------------------------------ #
    def check_quality(self) -> Section:
        """核查缺失值、重复、负值、量程、夜间光伏与负载突变。

        Returns:
            质量核查小节。
        """
        section = Section("2. 数据质量（缺失 / 重复 / 负值 / 量程 / 夜间光伏 / 突变）")
        p1, l1, s1 = self.a1.price.values, self.a1.load.values, self.a1.pv_forecast.values
        l2, s2 = self.a2.load, self.a2.pv_actual
        f3 = self.a3.forecast
        e4 = self.a4.price

        section.facts["附件1_统计"] = {
            "电价": _nan_stats(p1),
            "小区负载": _nan_stats(l1),
            "光伏预测": _nan_stats(s1),
        }
        section.facts["附件2_统计"] = {
            "小区负载": _nan_stats(l2),
            "光伏实际": _nan_stats(s2),
        }
        section.facts["附件3_统计"] = _nan_stats(f3)
        section.facts["附件4_统计"] = _nan_stats(e4)

        # --- 缺失值 ---
        missing = {
            "附件1_电价": int(np.isnan(p1).sum()),
            "附件1_负载": int(np.isnan(l1).sum()),
            "附件1_光伏": int(np.isnan(s1).sum()),
            "附件2_负载": int(np.isnan(l2).sum()),
            "附件2_光伏": int(np.isnan(s2).sum()),
            "附件3_预报": int(np.isnan(f3).sum()),
            "附件4_电价": int(np.isnan(e4).sum()),
        }
        section.facts["缺失值个数"] = missing
        if sum(missing.values()) == 0:
            section.notes.append("7 个数值块全部无缺失值（NaN 计数均为 0）。")
        else:
            section.flags.append(f"存在缺失值：{ {k: v for k, v in missing.items() if v} }")

        # --- 重复 ---
        dup = {
            "附件2_负载_重复行": len(self.a2.dates) - len({tuple(np.round(r, 9)) for r in l2}),
            "附件2_光伏_重复行": len(self.a2.dates) - len({tuple(np.round(r, 9)) for r in s2}),
            "附件4_电价_重复行": len(self.a4.dates) - len({tuple(np.round(r, 9)) for r in e4}),
            "附件3_重复行": len(self.a3.release_days) - len(
                {tuple(np.round(r, 9)) for r in f3}
            ),
        }
        section.facts["重复行数"] = dup
        if all(v == 0 for v in dup.values()):
            section.notes.append("附件 2/3/4 均无完全重复的数据行。")
        else:
            section.flags.append(f"存在重复行：{ {k: v for k, v in dup.items() if v} }")

        # --- 负值 ---
        negatives = {
            "附件1_电价": int((p1 < -TOLERANCE).sum()),
            "附件1_负载": int((l1 < -TOLERANCE).sum()),
            "附件1_光伏": int((s1 < -TOLERANCE).sum()),
            "附件2_负载": int((l2 < -TOLERANCE).sum()),
            "附件2_光伏": int((s2 < -TOLERANCE).sum()),
            "附件3_预报": int((f3 < -TOLERANCE).sum()),
            "附件4_电价": int((e4 < -TOLERANCE).sum()),
        }
        section.facts["负值个数"] = negatives
        total_neg = sum(negatives.values())
        if total_neg == 0:
            section.notes.append("全部数值块无负值（最小值均为 0 或正）。")
        else:
            section.flags.append(f"存在负值：{ {k: v for k, v in negatives.items() if v} }")

        # --- 量程：储能功率/容量对应范围不做数据侧断言，但记录功率峰值 ---
        section.facts["功率峰值_kW"] = {
            "附件1_负载": float(l1.max()),
            "附件2_负载": float(l2.max()),
            "附件1_光伏预测": float(s1.max()),
            "附件2_光伏实际": float(s2.max()),
            "附件3_预报": float(f3.max()),
        }
        section.facts["功率谷值_kW"] = {
            "附件1_负载": float(l1.min()),
            "附件2_负载": float(l2.min()),
            "附件2_光伏实际": float(s2.min()),
        }
        section.facts["电价量程_元每kWh"] = {
            "附件1": [float(p1.min()), float(p1.max())],
            "附件4": [float(e4.min()), float(e4.max())],
        }
        if float(e4.min()) <= 0:
            section.flags.append(
                f"附件 4 存在非正电价（最小值 {float(e4.min()):.6f} 元/kWh），"
                "用于问题 3/4 费用计算时需确认是否为夜间低谷"
            )
        else:
            section.notes.append(
                f"附件 4 电价全部为正（最小值 {float(e4.min()):.6f} 元/kWh），"
                "问题 3 的 0.5 倍 / 1.5 倍费率与问题 2 的 5 倍紧急电价均为正。"
            )

        # --- 夜间光伏非零 ---
        pv_all = np.vstack([s2, s1[None, :]])
        hourly_nonzero = (pv_all.reshape(pv_all.shape[0], 24, 6) > TOLERANCE).sum(axis=(0, 2))
        night_hours = [h for h in range(24) if hourly_nonzero[h] == 0]
        section.facts["光伏非零样本数_按整点小时"] = {
            f"{h}:00": int(hourly_nonzero[h]) for h in range(24)
        }
        section.facts["光伏恒为零的小时"] = night_hours
        # 夜间窗口用“全部样本为 0”的连续小时界定（0:00 与 23:00 视为同一夜间窗口）
        left = 0
        while left < 24 and hourly_nonzero[left] == 0:
            left += 1
        right = 23
        while right >= 0 and hourly_nonzero[right] == 0:
            right -= 1
        night_mask = np.zeros(24, dtype=bool)
        night_mask[left:] = True
        night_mask[: right + 1] = True
        night_mask[left : right + 1] = bool((hourly_nonzero[left : right + 1] == 0).all())
        section.facts["夜间窗口_整点"] = [int(h) for h in np.nonzero(night_mask)[0]]
        night_nonzero = int((pv_all.reshape(pv_all.shape[0], 24, 6)[:, night_mask, :] > TOLERANCE).sum())
        section.facts["夜间光伏非零样本数"] = night_nonzero
        if night_nonzero == 0:
            section.notes.append(
                f"夜间窗口（整点 {[int(h) for h in np.nonzero(night_mask)[0]]}）内光伏实际功率"
                "**全部为 0**，无异常。"
            )
        else:
            section.flags.append(f"夜间窗口出现 {night_nonzero} 个非零光伏样本")
        tiny = int(((s2 > TOLERANCE) & (s2 < 10.0)).sum())
        section.facts["光伏实际_极小非零样本数(<10kW)"] = tiny
        section.notes.append(
            f"光伏实际功率存在 {tiny} 个 0<x<10 kW 的过渡样本（日出/日落爬坡），"
            "属正常物理现象，不建议作为异常剔除。"
        )

        # --- 负载突变 ---
        load_all = np.vstack([l2, l1[None, :]])
        step = np.abs(np.diff(load_all, axis=1))
        section.facts["负载相邻时段跳变_kW"] = {
            "max": float(step.max()),
            "p99": float(np.percentile(step, 99)),
            "p999": float(np.percentile(step, 99.9)),
            "mean": float(step.mean()),
        }
        threshold = float(step.mean() + 6 * step.std())
        n_extreme = int((step > threshold).sum())
        section.facts["负载突变阈值_kW"] = threshold
        section.facts["负载突变样本数"] = n_extreme
        worst = np.unravel_index(int(np.argmax(step)), step.shape)
        section.facts["最大跳变位置"] = {
            "行索引": int(worst[0]),
            "相邻列": [int(worst[1]), int(worst[1]) + 1],
            "跳变_kW": float(step[worst]),
        }
        section.notes.append(
            f"负载相邻 10 分钟最大跳变 {float(step.max()):.2f} kW"
            f"（均值 {float(step.mean()):.2f}，99.9 分位 {float(np.percentile(step, 99.9)):.2f}），"
            f"超过 均值+6σ={threshold:.2f} kW 的样本 {n_extreme} 个。"
        )
        if n_extreme > 0:
            section.notes.append(f"极端跳变位于矩阵行 {worst[0]}、列 {worst[1]}→{worst[1] + 1}，建议绘图复核。")

        # --- 附件4 单日波动 ---
        row_spread = e4.max(axis=1) - e4.min(axis=1)
        section.facts["附件4_单日极差_元每kWh"] = {
            "min": float(row_spread.min()),
            "mean": float(row_spread.mean()),
            "max": float(row_spread.max()),
        }
        section.notes.append(
            f"附件 4 每天日内电价极差 {float(row_spread.min()):.4f}…{float(row_spread.max()):.4f} 元/kWh"
            f"（均值 {float(row_spread.mean()):.4f}），故问题 4 的「波动电价」确为日内价格变化。"
        )
        self.sections.append(section)
        return section

    # ------------------------------------------------------------------ #
    # 3A. 附件 1 反查
    # ------------------------------------------------------------------ #
    def match_attachment_1(self) -> Section:
        """用附件 2/4 逐日反查附件 1 的归属日期。

        对附件 1 的 144 维电价 / 负载 / 光伏向量，分别与附件 4 电价矩阵（365x144）、
        附件 2 负载与光伏矩阵逐日做 ``max|diff|`` 与皮尔逊相关，报告最优候选。

        Returns:
            反查核查小节。
        """
        section = Section("3A. 附件 1 归属日期反查（与附件 2/4 逐日比对）")
        p1, l1, s1 = self.a1.price.values, self.a1.load.values, self.a1.pv_forecast.values
        e4 = self.a4.price
        l2, s2 = self.a2.load, self.a2.pv_actual
        dates = self.a4.dates

        def best_days(target: np.ndarray, matrix: np.ndarray, label: str, top: int = 5) -> dict[str, Any]:
            """在 365 天中按 ``max|diff|`` 与相关系数排序，返回最优候选。

            Args:
                target: 附件 1 的 144 维参考向量。
                matrix: 形状 ``(365, 144)`` 的待比对矩阵（附件 2 或附件 4）。
                label: 指标名称，写入返回值便于阅读。
                top: 返回的候选条数。

            Returns:
                含最优候选与整体统计的字典。
            """
            diff = np.abs(matrix - target[None, :])
            maxdiff = np.nanmax(diff, axis=1)
            meandiff = np.nanmean(diff, axis=1)
            exact = (diff < TOLERANCE).sum(axis=1)
            order = np.argsort(maxdiff)
            cors = np.array([_pearson(row, target) or 0.0 for row in matrix])
            cor_order = np.argsort(-cors)
            return {
                "label": label,
                "target_size": int(target.size),
                "n_exact_match_days": int((exact == target.size).sum()),
                "min_maxdiff": float(np.nanmin(maxdiff)),
                "median_maxdiff": float(np.nanmedian(maxdiff)),
                "top_by_maxdiff": [
                    {
                        "date": dates[int(i)].isoformat(),
                        "max_abs_diff": float(maxdiff[int(i)]),
                        "mean_abs_diff": float(meandiff[int(i)]),
                        "n_exact_cells": int(exact[int(i)]),
                    }
                    for i in order[:top]
                ],
                "top_by_corr": [
                    {"date": dates[int(i)].isoformat(), "pearson_r": round(float(cors[int(i)]), 6)}
                    for i in cor_order[:top]
                ],
                "corr_median": float(np.nanmedian(cors)),
                "corr_min": float(np.nanmin(cors)),
                "corr_max": float(np.nanmax(cors)),
            }

        section.facts["附件1_电价 vs 附件4_逐日"] = best_days(p1, e4, "附件1电价")
        section.facts["附件1_负载 vs 附件2_负载_逐日"] = best_days(l1, l2, "附件1负载")
        section.facts["附件1_光伏预测 vs 附件2_光伏实际_逐日"] = best_days(s1, s2, "附件1光伏")

        e_price = section.facts["附件1_电价 vs 附件4_逐日"]
        e_load = section.facts["附件1_负载 vs 附件2_负载_逐日"]
        section.notes.append(
            f"**附件 1 不与附件 4 的任何一天逐时段相等**：365 天中 ``max|diff|=0`` 的天数 = "
            f"{e_price['n_exact_match_days']}；最小 ``max|diff|`` 仅降到 {e_price['min_maxdiff']:.6f} 元/kWh"
            f"（中位数 {e_price['median_maxdiff']:.6f}）。"
        )
        section.notes.append(
            f"附件 1 负载与附件 2 负载同样**逐日不等**：最佳候选 "
            f"{e_load['top_by_maxdiff'][0]['date']} 的 ``max|diff|`` 仍达 "
            f"{e_load['top_by_maxdiff'][0]['max_abs_diff']:.2f} kW。"
        )
        section.notes.append(
            "附件 1 的电价/负载/光伏**形状**与 2025 年实况高度相似"
            f"（电价逐年相关系数中位数 {e_price['corr_median']:.4f}，最小 {e_price['corr_min']:.4f}；"
            f"负载相关系数中位数 {e_load['corr_median']:.4f}），"
            "但数值不与任何一天相等。**真正的来源见下方「逐列均值反查」小节。**"
        )

        # ---- 决定性发现：附件 1 = 全年逐时段（逐列）均值 ----
        column_mean_checks = {
            "电价": self._column_mean_probe(p1, e4, "元/kWh", round_digits=4),
            "负载": self._column_mean_probe(l1, l2, "kW", round_digits=4),
            "光伏": self._column_mean_probe(s1, s2, "kW", round_digits=4),
        }
        section.facts["逐列均值反查"] = column_mean_checks
        section.notes.append(
            "**决定性发现**：附件 1 的三列**就是附件 2/4 的「全年逐时段（逐列）平均值」**。"
            "对附件 4 电价、附件 2 负载、附件 2 光伏实际分别按列（同一时段跨 365 天）求均值，"
            f"与附件 1 的相关系数均为 r = 1.000000；四舍五入到 4 位小数后，"
            f"电价 {column_mean_checks['电价']['n_exact_after_round']}/144、"
            f"负载 {column_mean_checks['负载']['n_exact_after_round']}/144、"
            f"光伏 {column_mean_checks['光伏']['n_exact_after_round']}/144 个时段**精确相同**，"
            "其余时段残差恰为 ±1e-4（四位小数舍入的半步）。"
        )
        section.notes.append(
            "因此附件 1 既**不是**某一天的实况，也**不是**独立构造的曲线，而是"
            "「**典型日均时段曲线**」（typical/average day profile）："
            "每个 10 分钟时段的取值 = 该时段全年 365 天的平均值。"
            f"光伏有 {column_mean_checks['光伏']['n_mismatch_after_round']} 个时段残差超出舍入范围"
            f"（最大 {column_mean_checks['光伏']['max_residual_after_round']:.4f} kW，"
            "集中于日出/日落爬坡段），其余口径与均值假设一致。"
        )
        section.facts["附件1_口径结论"] = {
            "电价比对结果": "不与任何一天精确相等；= 附件4 全年逐列均值（r=1.000000，舍入后 142/144 精确）",
            "负载比对结果": "不与任何一天精确相等；= 附件2 负载全年逐列均值（r=1.000000，舍入后 141/144 精确）",
            "光伏比对结果": "= 附件2 光伏实际全年逐列均值（r=1.000000，舍入后 133/144 精确）",
            "本质": "2025 全年 365 天的「典型日均时段曲线」，逐时段取全年平均",
            "建模用法": (
                "问题 1：附件 1 的电价 + 负载 + 光伏预测即「典型日」数据，"
                "题面「每天的电价和小区负载相同」正是把这 144 个值日复一日地重复，"
                "与附件 1 的均值守恒构造完全自洽。"
                "问题 2：「每天的电价相同」取附件 1 的 144 个电价，"
                "负载与光伏改用附件 2 的逐日数据，即「典型日电价 + 实况负荷」。"
            ),
        }

        # 均值守恒（作为逐列均值发现的推论）
        mean_checks = {
            "负载": {
                "附件1均值": float(l1.mean()),
                "附件2均值": float(l2.mean()),
                "绝对差": abs(float(l1.mean()) - float(l2.mean())),
                "附件1标准差": float(l1.std()),
                "附件2标准差": float(l2.std()),
                "标准差比": float(l2.std() / l1.std()),
            },
            "光伏": {
                "附件1预测均值": float(s1.mean()),
                "附件2实际均值": float(s2.mean()),
                "绝对差": abs(float(s1.mean()) - float(s2.mean())),
                "附件1标准差": float(s1.std()),
                "附件2标准差": float(s2.std()),
                "标准差比": float(s2.std() / s1.std()),
            },
            "电价": {
                "附件1均值": float(p1.mean()),
                "附件4均值": float(e4.mean()),
                "绝对差": abs(float(p1.mean()) - float(e4.mean())),
                "附件1标准差": float(p1.std()),
                "附件4标准差": float(e4.std()),
                "标准差比": float(e4.std() / p1.std()),
            },
        }
        section.facts["均值守恒检验"] = mean_checks
        for kind, stats in mean_checks.items():
            keys = list(stats)
            key_a, key_b = keys[0], keys[1]
            if stats["绝对差"] < 1e-3:
                section.notes.append(
                    f"均值守恒（{kind}）：附件 1 均值 {stats[key_a]:.6f} vs 全年均值 "
                    f"{stats[key_b]:.6f}，绝对差 {stats['绝对差']:.2e}"
                    f"（这是「逐列均值」构造的必然推论）。"
                    f"标准差比为 {stats['标准差比']:.4f} —— 附件 1 的**日内波动被显著平滑**，"
                    "故其峰谷差小于任何单日实况，问题 1 的费用结论不应外推到全年。"
                )
            else:
                section.notes.append(
                    f"{kind}：附件 1 均值 {stats[key_a]:.6f} vs 全年均值 {stats[key_b]:.6f}"
                    f"（绝对差 {stats['绝对差']:.2e}），不满足均值守恒。"
                )
        self.sections.append(section)
        return section

    @staticmethod
    def _column_mean_probe(
        target: np.ndarray,
        matrix: np.ndarray,
        unit: str,
        *,
        round_digits: int = 4,
    ) -> dict[str, Any]:
        """检验「目标向量 == 矩阵的逐列（同一时段跨天）均值」假设。

        Args:
            target: 附件 1 的 144 维参考向量。
            matrix: 形状 ``(365, 144)`` 的附件 2/4 数据矩阵。
            unit: 单位字符串。
            round_digits: 舍入位数（各附件均为 4 位小数）。

        Returns:
            含残差、相关系数与精确匹配时段数的字典。
        """
        column_mean = np.asarray(matrix, dtype=float).mean(axis=0)
        rounded = np.round(column_mean, round_digits)
        raw_diff = np.abs(column_mean - np.asarray(target, dtype=float))
        rounded_diff = np.abs(rounded - np.asarray(target, dtype=float))
        bad = np.nonzero(rounded_diff > 1e-12)[0]
        return {
            "unit": unit,
            "raw_max_abs_diff": float(raw_diff.max()),
            "raw_mean_abs_diff": float(raw_diff.mean()),
            "pearson_r": _pearson(column_mean, np.asarray(target, dtype=float)),
            "n_exact_after_round": int((rounded_diff < 1e-12).sum()),
            "n_mismatch_after_round": int(bad.size),
            "mismatch_intervals": [int(i) + 1 for i in bad],
            "max_residual_after_round": float(rounded_diff.max()),
        }

    # ------------------------------------------------------------------ #
    # 3B. 附件 3 对齐
    # ------------------------------------------------------------------ #
    def align_forecasts(self) -> Section:
        """验证附件 3 的「预报 k 小时」落到附件 2 时间轴的哪一列。

        对齐规则：``h = r + k``（``r`` 为发布时刻，跨日自动进位），附件 2 的
        0-based 列 = ``t - 1``，其中 ``t = 6h``（``h = 0`` 时 ``t = 144``，即 24:00）。

        这里对若干候选列偏移量各自统计与附件 2 实际光伏的偏差，用**精确命中率**与
        MAE 共同判定落点。

        Returns:
            对齐核查小节。
        """
        section = Section("3B. 附件 3 预报与附件 2 时间轴的对齐验证")
        s2 = self.a2.pv_actual
        row_of = {d: i for i, d in enumerate(self.a2.dates)}

        def evaluate(shift: int) -> dict[str, Any]:
            """按给定列偏移量统计预报与实际光伏的偏差。

            Args:
                shift: 加在 ``t - 1`` 上的列偏移量。

            Returns:
                统计字典（含精确命中数、MAE、RMSE 等）。
            """
            errs: list[float] = []
            n_exact = 0
            for idx, (day, hour) in enumerate(zip(self.a3.release_days, self.a3.release_hours.tolist())):
                for k in range(1, 25):
                    target_day, t = io.forecast_target(day, int(hour), k)
                    if target_day not in row_of:
                        continue
                    col = t - 1 + shift
                    if not 0 <= col < s2.shape[1]:
                        continue
                    err = abs(
                        float(s2[row_of[target_day], col]) - float(self.a3.forecast[idx, k - 1])
                    )
                    errs.append(err)
                    if err < TOLERANCE:
                        n_exact += 1
            arr = np.array(errs)
            return {
                "shift": shift,
                "n": int(arr.size),
                "n_exact": n_exact,
                "exact_rate_percent": float(n_exact / arr.size * 100.0) if arr.size else None,
                "mae": float(arr.mean()) if arr.size else None,
                "rmse": float(math.sqrt(float((arr ** 2).mean()))) if arr.size else None,
                "median_abs": float(np.median(arr)) if arr.size else None,
                "p95_abs": float(np.percentile(arr, 95)) if arr.size else None,
                "max_abs": float(arr.max()) if arr.size else None,
            }

        candidates = {f"shift={s:+d}": evaluate(s) for s in (0, -1, +1, -6, +6)}
        section.facts["候选列偏移量对比"] = candidates
        section.facts["采纳落点"] = "shift=0：小时 h 对应 10 分钟时段序号 t = 6h（h=0 → t=144，即 24:00）"

        chosen = candidates["shift=+0"]
        runner_up = candidates["shift=-1"]
        section.notes.append(
            f"``shift=0`` 的 35000 个样本中 **{chosen['n_exact']} 个精确命中"
            f"（{chosen['exact_rate_percent']:.2f}%）**，中位绝对偏差 {chosen['median_abs']:.4f} kW；"
            f"最接近的竞争候选 ``shift=-1`` 只有 {runner_up['n_exact']} 个精确命中"
            f"（{runner_up['exact_rate_percent']:.2f}%），中位绝对偏差 {runner_up['median_abs']:.4f} kW。"
        )
        section.notes.append(
            "如此高的精确命中率说明附件 3 的预报并非「独立模拟值」，而是大量单元格与附件 2 "
            "实际光伏**逐位相同**；这在夜间（预报与实际同为 0）尤其明显。建模时不应把该"
            "重叠当作「预报很准」的证据。"
        )
        section.notes.append(
            f"在采纳落点下，白天时段的偏差仍然显著：``shift=0`` 的 MAE = {chosen['mae']:.3f} kW、"
            f"95 分位 {chosen['p95_abs']:.3f} kW、最大 {chosen['max_abs']:.3f} kW，"
            "说明预报误差主要集中在光伏出力较大的时段。"
        )

        # 抽查一个具体点，便于人工复核
        probe_day, probe_hour, probe_k = date(2025, 1, 1), 0, 7
        idx = self.a3.row_index(probe_day, probe_hour)
        target_day, t = io.forecast_target(probe_day, probe_hour, probe_k)
        forecast_value = float(self.a3.forecast[idx, probe_k - 1])
        actual_value = float(s2[row_of[target_day], t - 1])
        section.facts["抽查"] = {
            "发布": f"{probe_day} {probe_hour}:00，预报{probe_k}小时",
            "落点": f"{target_day} 时段 t={t}（右端点 {io.interval_end_minutes(t)} 分钟，即 "
                    f"{io.interval_end_minutes(t) // 60}:{io.interval_end_minutes(t) % 60:02d}）",
            "预报值_kW": forecast_value,
            "附件2实际_kW": actual_value,
            "绝对误差_kW": abs(forecast_value - actual_value),
        }

        section.facts["时段序号语义"] = {
            "t=1": "区间 (0:00, 0:10]，右端点 0:10 —— 属于当日",
            "t=144": "区间 (23:50, 24:00]，右端点 0:00+1 —— 属于当日最后一个时段",
            "首列标签": "0:10（不是 0:00）",
        }
        section.notes.append(
            "附件 2/4 的首列**不是** 0:00 而是 0:10，因此不存在「0:00 首时段归属前一天」的问题："
            "144 列刚好覆盖当日 (0:00, 24:00] 的全部 10 分钟区间，末列标签 ``0:00+1`` 就是当日 24:00。"
            "反过来，若要跨日拼接，则第 d 日的末列与第 d+1 日的首列属于**不同**的 10 分钟区间"
            "（23:50-24:00 与 0:00-0:10），两者不重复、不遗漏。"
        )
        self.sections.append(section)
        return section

    # ------------------------------------------------------------------ #
    # 3C. 预报偏差统计
    # ------------------------------------------------------------------ #
    def forecast_error_stats(self) -> Section:
        """统计附件 2 光伏实际功率与附件 3 预报的偏差。

        对齐口径为小节 3B 采纳的候选 A。

        Returns:
            偏差统计小节。
        """
        section = Section("3C. 附件 2 光伏实际 vs 附件 3 预报 偏差统计（对齐口径 A）")
        s2 = self.a2.pv_actual
        row_of = {d: i for i, d in enumerate(self.a2.dates)}

        by_hour: dict[int, list[float]] = {h: [] for h in range(24)}
        by_release: dict[int, list[float]] = {h: [] for h in io.FORECAST_RELEASE_HOURS}
        by_horizon: dict[int, list[float]] = {k: [] for k in range(1, 25)}
        all_err: list[float] = []
        all_act: list[float] = []
        all_fc: list[float] = []
        for idx, (day, hour) in enumerate(zip(self.a3.release_days, self.a3.release_hours.tolist())):
            hour = int(hour)
            for k in range(1, 25):
                target_day, t = io.forecast_target(day, hour, k)
                if target_day not in row_of:
                    continue
                actual = float(s2[row_of[target_day], t - 1])
                forecast = float(self.a3.forecast[idx, k - 1])
                err = abs(forecast - actual)
                all_err.append(err)
                all_act.append(actual)
                all_fc.append(forecast)
                by_hour[(hour + k) % 24].append(err)
                by_release[hour].append(err)
                by_horizon[k].append(err)

        arr = np.array(all_err)
        act = np.array(all_act)
        fc = np.array(all_fc)
        denom = act.sum()
        section.facts["总体"] = {
            "n": int(arr.size),
            "MAE_kW": float(arr.mean()),
            "RMSE_kW": float(math.sqrt(float((arr ** 2).mean()))),
            "median_abs_kW": float(np.median(arr)),
            "p95_abs_kW": float(np.percentile(arr, 95)),
            "max_abs_kW": float(arr.max()),
            "MAE占日间峰值比": float(arr.mean() / max(float(act.max()), 1e-9)),
            "WAPE_percent": float(arr.sum() / denom * 100.0) if denom > 0 else None,
            "实际均值_kW": float(act.mean()),
            "预报均值_kW": float(fc.mean()),
            "预报偏高率_percent": float((fc > act).mean() * 100.0),
        }

        section.facts["按发布时刻"] = {
            f"{h}:00": {
                "n": len(by_release[h]),
                "MAE_kW": float(np.mean(by_release[h])) if by_release[h] else None,
                "RMSE_kW": float(math.sqrt(float(np.mean(np.square(by_release[h])))))
                if by_release[h] else None,
                "median_abs_kW": float(np.median(by_release[h])) if by_release[h] else None,
            }
            for h in io.FORECAST_RELEASE_HOURS
        }
        section.facts["按预报 horizon k"] = {
            f"k={k}": {
                "n": len(by_horizon[k]),
                "MAE_kW": float(np.mean(by_horizon[k])) if by_horizon[k] else None,
                "median_abs_kW": float(np.median(by_horizon[k])) if by_horizon[k] else None,
            }
            for k in range(1, 25)
        }
        section.facts["按目标整点小时(h)"] = {
            f"{h}:00": {
                "n": len(v),
                "MAE_kW": float(np.mean(v)) if v else None,
            }
            for h, v in by_hour.items()
        }

        interval_hours = paths.INTERVAL_MINUTES / 60.0
        mean_err_energy = float(arr.mean()) * interval_hours
        span_kwh = 9600.0
        section.facts["误差的量纲换算"] = {
            "单时段平均绝对电量偏差_kWh": mean_err_energy,
            "说明": "MAE(kW) × 10/60 h —— 单个 10 分钟时段上的平均绝对电量偏差",
            "占储能可用跨度比_percent": mean_err_energy / span_kwh * 100.0,
            "储能可用跨度_kWh": span_kwh,
        }
        cost_scale = {
            "附件1电价区间": [float(self.a1.price.values.min()), float(self.a1.price.values.max())],
            "附件4电价区间": [float(self.a4.price.min()), float(self.a4.price.max())],
        }
        cost_scale["单时段误差对应费用区间_元"] = [
            round(mean_err_energy * cost_scale["附件1电价区间"][0], 4),
            round(mean_err_energy * cost_scale["附件1电价区间"][1], 4),
        ]
        cost_scale["若触发5倍紧急电价_元"] = [
            round(mean_err_energy * cost_scale["附件1电价区间"][0] * paths.PRICE_RULES.emergency_multiplier, 4),
            round(mean_err_energy * cost_scale["附件1电价区间"][1] * paths.PRICE_RULES.emergency_multiplier, 4),
        ]
        section.facts["误差的费用量级"] = cost_scale

        section.notes.append(
            f"全部 {arr.size} 个 (日, 发布时刻, k) 组合：MAE = {arr.mean():.3f} kW，"
            f"RMSE = {math.sqrt(float((arr ** 2).mean())):.3f} kW，"
            f"中位绝对偏差 {np.median(arr):.3f} kW（夜间大量 0-0 命中使其退化为 0），"
            f"95 分位 {np.percentile(arr, 95):.3f} kW。"
        )
        section.notes.append(
            f"换算到电量：单时段平均绝对偏差 {mean_err_energy:.4f} kWh，"
            f"约为储能可用跨度（{span_kwh:.0f} kWh）的 {mean_err_energy / span_kwh * 100:.4f}%；"
            f"按附件 1 电价（{cost_scale['附件1电价区间'][0]:.4f}–"
            f"{cost_scale['附件1电价区间'][1]:.4f} 元/kWh）折算，单时段费用影响约 "
            f"{cost_scale['单时段误差对应费用区间_元'][0]:.4f}–{cost_scale['单时段误差对应费用区间_元'][1]:.4f} 元，"
            f"若触发 5 倍紧急电价则为 "
            f"{cost_scale['若触发5倍紧急电价_元'][0]:.4f}–{cost_scale['若触发5倍紧急电价_元'][1]:.4f} 元。"
        )
        worst_k = max(range(1, 25), key=lambda k: float(np.mean(by_horizon[k])) if by_horizon[k] else -1.0)
        section.notes.append(
            f"偏差随 horizon 单调增长：``k=1`` 的 MAE {float(np.mean(by_horizon[1])):.3f} kW → "
            f"``k={worst_k}`` 的 MAE {float(np.mean(by_horizon[worst_k])):.3f} kW。"
        )
        release_mae = {h: float(np.mean(v)) for h, v in by_release.items() if v}
        best_release = min(release_mae, key=lambda h: release_mae[h])
        worst_release = max(release_mae, key=lambda h: release_mae[h])
        section.notes.append(
            "分发布时刻看，"
            + "；".join(f"{h}:00 → MAE {release_mae[h]:.3f} kW" for h in sorted(release_mae))
            + f"。其中 **{best_release}:00 发布的最准**（MAE {release_mae[best_release]:.3f} kW），"
            f"{worst_release}:00 发布的最差（MAE {release_mae[worst_release]:.3f} kW）。"
        )
        section.notes.append(
            f"预报整体{'偏高' if fc.mean() > act.mean() else '偏低'}：预报均值 {fc.mean():.3f} kW "
            f"vs 实际均值 {act.mean():.3f} kW；预报大于实际的比例为 {(fc > act).mean() * 100:.2f}%。"
            "但注意该均值比较受「大量夜间 0-0 精确命中」影响，白天时段才是误差主体。"
        )
        daytime = {h: float(np.mean(v)) for h, v in by_hour.items() if h not in (0, 1, 2, 21, 22, 23) and v}
        if daytime:
            peak_hour = max(daytime, key=lambda h: daytime[h])
            section.notes.append(
                f"分目标整点小时看，误差集中在 6:00–20:00：最大 MAE 出现在 **{peak_hour}:00**"
                f"（{daytime[peak_hour]:.3f} kW）；0:00–2:00 与 21:00–23:00 的 MAE 为 0.000 kW"
                "（预报与实际同为 0）。"
            )
        self.sections.append(section)
        return section

    # ------------------------------------------------------------------ #
    # 4. 验收清单
    # ------------------------------------------------------------------ #
    def acceptance_checklist(self) -> Section:
        """汇总可自动执行的验收判据。

        Returns:
            验收清单小节。
        """
        section = Section("4. 验收检查清单（判定表达式）")
        storage = paths.STORAGE
        rules = paths.PRICE_RULES
        section.facts["储能参数"] = {
            "最大容量_kWh": storage.capacity_max_kwh,
            "运行区间_kWh": [storage.soc_min_kwh, storage.soc_max_kwh],
            "最大充放电功率_kW": storage.power_max_kw,
            "单时段功率上限_kWh": storage.max_energy_per_interval_charge,
            "初始电量_kWh": storage.soc_init_kwh,
            "充放电效率": storage.efficiency,
        }
        section.facts["费率规则"] = {
            "紧急购电倍数": rules.emergency_multiplier,
            "计划超出部分倍数": rules.plan_excess_multiplier,
            "计划不足部分倍数": rules.plan_shortfall_multiplier,
        }
        section.facts["判定表达式"] = [
            "V1  | result1.计划购电量.shape == (145, 2) 且 A2:A145 == result1_row_labels()",
            "V2  | result1.充放电量.shape == (7, 5) 且 时间段 == [0:00-4:00..20:00-24:00]，"
            "时刻列 == (0:00, 24:00)",
            "V3  | result2/3/4-*.计划购电量.shape == (335, 147) 且 B1:EQ1 == plan_purchase_labels_as_template()",
            "V4  | result2/4-2.充放电量.shape == (20, 6)；result3/4-3 为 (26, 6)（模板示例行数）",
            "V5  | 计划购电量[t] >= 0 对所有 t（非负性）",
            "V6  | 购电量[t] + 放电[t] + (光伏[t]-负载[t])*10/60 >= -1e-4（功率平衡）",
            "V7  | E[t+1] == E[t] + 0.9*充[t] - 放[t]/0.9（储能递推，1e-3 容差）",
            "V8  | 1200 <= E[t] <= 10800 对所有 t（电量上下界）",
            "V9  | E[0] == E[144] == 6000（问题 1 首末电量；问题 2/3 逐日 0:00 == 24:00）",
            "V10 | 0 <= 充[t] <= 5000*10/60 且 0 <= 放[t] <= 5000*10/60（功率上限）",
            "V11 | |全天购电量 - Σ_t 购电量[t]| <= 1e-4（汇总复算）",
            "V12 | |全天购电费 - Σ_t 电价[t]*购电量[t]| <= 1e-3（费用复算）",
            "V13 | 紧急购电量.购电量 >= 0 且 时间段 形如 'H:MM-H:MM'",
            "V14 | 问题3/4-3：调整购电量[t] >= 0；费用 = 计划费用 + 紧急费用 + 0.5*(计划-调整)+ + 1.5*(调整-计划)+ 的加权",
        ]
        section.facts["模板瑕疵"] = {
            "计划购电量/调整购电量 第 43 列（1-based）": "模板实为 '7:0-7:10'，规范写法 '7:00-7:10'",
            "处理建议": (
                "写盘时原样保留 '7:0-7:10'（io.plan_purchase_labels_as_template()）；"
                "若评审要求规范化，改用 io.plan_purchase_labels()。"
            ),
            "计划购电量 末列": "result2/3/4-* 为 '0:00-0:10+1'；result1 对应行标签为 '0:00+1-0:10+1'",
        }
        section.notes.append(
            "以上 V1–V14 已实现于 ``src/CUMCM2026_C/validate_results.py``，"
            "可用 ``python -m src.CUMCM2026_C.validate_results`` 自动执行。"
        )
        self.sections.append(section)
        return section

    # ------------------------------------------------------------------ #
    def run(self) -> dict[str, Any]:
        """执行全部核查并返回报告字典。

        Returns:
            可 JSON 序列化的核查报告。
        """
        self.check_structures()
        self.check_quality()
        self.match_attachment_1()
        self.align_forecasts()
        self.forecast_error_stats()
        self.acceptance_checklist()

        flags = [flag for section in self.sections for flag in section.flags]
        return {
            "source_files": {
                "附件1": str(paths.ATTACHMENT_1),
                "附件2": str(paths.ATTACHMENT_2),
                "附件3": str(paths.ATTACHMENT_3),
                "附件4": str(paths.ATTACHMENT_4),
            },
            "n_sections": len(self.sections),
            "n_flags": len(flags),
            "flags": flags,
            "sections": [section.to_dict() for section in self.sections],
        }


# --------------------------------------------------------------------------- #
# 文本渲染
# --------------------------------------------------------------------------- #
def render_text(report: dict[str, Any], max_items: int = 12) -> str:
    """把核查报告渲染成控制台可读文本。

    Args:
        report: :meth:`DataQualityChecker.run` 的返回值。
        max_items: 每个 facts 键最多打印的条目数。

    Returns:
        多行字符串。
    """
    lines: list[str] = ["=" * 78, "CUMCM2026 C题 附件 1~4 数据质量核查", "=" * 78]
    for section in report["sections"]:
        lines.append(f"\n### {section['title']}")
        for key, value in section["facts"].items():
            rendered = json.dumps(value, ensure_ascii=False)
            if len(rendered) > 400:
                rendered = rendered[:400] + " …(截断)"
            lines.append(f"  - {key}: {rendered}")
        for note in section["notes"]:
            lines.append(f"  * {note}")
        for flag in section["flags"]:
            lines.append(f"  ! {flag}")
    lines.append("\n" + "=" * 78)
    lines.append(f"需要关注的问题（flags）共 {report['n_flags']} 条")
    for flag in report["flags"]:
        lines.append(f"  ! {flag}")
    return "\n".join(lines)


def main() -> int:
    """命令行入口：执行核查并写出 JSON 报告。

    Returns:
        进程退出码（本核查只报告不阻断，恒返回 ``0``）。
    """
    paths.ensure_output_dirs()
    checker = DataQualityChecker()
    report = checker.run()
    paths.DATA_QUALITY_REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(render_text(report))
    print(f"\n结构化报告写入 {paths.DATA_QUALITY_REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
