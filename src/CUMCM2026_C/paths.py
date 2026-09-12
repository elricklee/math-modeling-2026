"""CUMCM2026 C题（微网与外部电网电力调控策略）统一路径与全局常量。

设计约定
--------
* 原始附件一律**只读**：位于 ``data/raw/C题``（由用户指定的真实附件目录导入）。
* 一切中间产物写入 ``data/processed/CUMCM2026_C``，结果写入 ``results/CUMCM2026_C``，
  图形写入 ``figures/CUMCM2026_C``。
* 储能与电价等题目参数集中在 :data:`STORAGE` 与 :data:`PRICE_RULES`，
  建模脚本不得在别处硬编码这些数字。

本模块只依赖标准库，可被任何阶段（数据核查 / 求解 / 校验 / 绘图）安全导入。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.config import ROOT

# --------------------------------------------------------------------------- #
# 路径
# --------------------------------------------------------------------------- #
CASE_DIR: Path = ROOT / "CUMCM2026Problems" / "C题"
"""题目原文所在目录（只读）。"""

PROBLEM_TXT: Path = CASE_DIR / "C题.txt"
"""题目原文（权威文本，与 PDF 逐字节一致）。"""

RAW_DIR: Path = ROOT / "data" / "raw" / "C题"
"""附件 1~4 与附件 5 结果模板所在目录（只读，禁止修改）。"""

ATTACHMENT_5_DIR: Path = RAW_DIR / "附件5"
"""附件 5 结果模板目录（只读）。"""

PROCESSED_DIR: Path = ROOT / "data" / "processed" / "CUMCM2026_C"
"""清洗产物与核查报告输出目录。"""

RESULTS_DIR: Path = ROOT / "results" / "CUMCM2026_C"
"""``result*.xlsx`` 生成目录。"""

FIGURES_DIR: Path = ROOT / "figures" / "CUMCM2026_C"
"""图形输出目录。"""

DOCS_DIR: Path = ROOT / "docs"
"""文档输出目录。"""

ATTACHMENT_1: Path = RAW_DIR / "附件1.xlsx"
ATTACHMENT_2: Path = RAW_DIR / "附件2.xlsx"
ATTACHMENT_3: Path = RAW_DIR / "附件3.xlsx"
ATTACHMENT_4: Path = RAW_DIR / "附件4.xlsx"

RESULT_TEMPLATES: dict[str, Path] = {
    "result1": ATTACHMENT_5_DIR / "result1.xlsx",
    "result2": ATTACHMENT_5_DIR / "result2.xlsx",
    "result3": ATTACHMENT_5_DIR / "result3.xlsx",
    "result4-2": ATTACHMENT_5_DIR / "result4-2.xlsx",
    "result4-3": ATTACHMENT_5_DIR / "result4-3.xlsx",
}
"""结果模板路径，键为 ``resultX`` 逻辑名。"""

DATA_QUALITY_REPORT: Path = PROCESSED_DIR / "data_quality_report.json"
"""数据质量核查报告输出路径。"""

VALIDATION_REPORT: Path = PROCESSED_DIR / "result_validation_report.json"
"""结果文件验收报告输出路径。"""


def result_path(name: str) -> Path:
    """返回某份结果文件的写入路径，例如 ``result_path("result1")``。

    Args:
        name: 逻辑名之一：``result1`` / ``result2`` / ``result3`` /
            ``result4-2`` / ``result4-3``（也接受带 ``.xlsx`` 后缀的写法）。

    Returns:
        位于 :data:`RESULTS_DIR` 下的目标路径（不保证已存在）。
    """
    stem = name[:-5] if name.endswith(".xlsx") else name
    return RESULTS_DIR / f"{stem}.xlsx"


def ensure_output_dirs() -> None:
    """创建全部输出目录（幂等）。原始数据目录不在其中，永不被创建或改动。"""
    for directory in (PROCESSED_DIR, RESULTS_DIR, FIGURES_DIR, DOCS_DIR):
        directory.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# 时间轴常量
# --------------------------------------------------------------------------- #
INTERVALS_PER_DAY: int = 144
"""一天被划分为 144 个 10 分钟时段。"""

INTERVAL_MINUTES: int = 10
"""单个时段长度（分钟）。"""

HOURS_PER_DAY: int = 24
"""一天 24 个小时刻度（附件 3 预报的整点轴）。"""


# --------------------------------------------------------------------------- #
# 题目参数（附录 1 与问题 2/3 的费率规则）
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class StorageParams:
    """储能设备参数，来自题目"附录 1 储能设备的参数"。"""

    capacity_max_kwh: float = 12000.0
    """储能设备最大容量（kWh）。"""

    soc_min_kwh: float = 1200.0
    """运行中电量下界（kWh）。"""

    soc_max_kwh: float = 10800.0
    """运行中电量上界（kWh）。"""

    power_max_kw: float = 5000.0
    """最大充放电功率（kW）。"""

    soc_init_kwh: float = 6000.0
    """2025-01-01 0:00 初始电量（kWh）。"""

    efficiency: float = 0.9
    """充放电效率（对称，充放各 0.9）。"""

    @property
    def max_energy_per_interval_charge(self) -> float:
        """单个 10 分钟时段的最大**入网侧**充电电量（kWh）= 5000 kW x (10/60) h。"""
        return self.power_max_kw * INTERVAL_MINUTES / 60.0

    @property
    def max_energy_per_interval_discharge(self) -> float:
        """单个 10 分钟时段的最大**出网侧**放电电量（kWh）。"""
        return self.power_max_kw * INTERVAL_MINUTES / 60.0


@dataclass(frozen=True)
class PriceRules:
    """题目给出的购电费率规则（问题 2/3/4）。"""

    emergency_multiplier: float = 5.0
    """紧急购电电价 = 交易时刻电价的 5 倍。"""

    plan_shortfall_multiplier: float = 0.5
    """计划购电量高于调整购电量部分的违约电价 = 交易时刻电价的 50%。"""

    plan_excess_multiplier: float = 1.5
    """调整购电量高于计划购电量部分的电价 = 交易时刻电价的 1.5 倍。"""


STORAGE: StorageParams = StorageParams()
"""储能参数全局单例。"""

PRICE_RULES: PriceRules = PriceRules()
"""费率规则全局单例。"""


# --------------------------------------------------------------------------- #
# 数据日期范围
# --------------------------------------------------------------------------- #
DATA_START = "2025-01-01"
"""附件 2/3/4 覆盖区间的首日（2025 年 1 月 1 日）。"""

DATA_END = "2025-12-31"
"""附件 2/3/4 覆盖区间的末日（2025 年 12 月 31 日）。"""

RESULT2_START = "2025-02-01"
"""result2/result3/result4-* 计划购电量覆盖区间的首日。"""

RESULT2_END = "2025-12-31"
"""result2/result3/result4-* 计划购电量覆盖区间的末日。"""


__all__ = [
    "ATTACHMENT_1",
    "ATTACHMENT_2",
    "ATTACHMENT_3",
    "ATTACHMENT_4",
    "ATTACHMENT_5_DIR",
    "CASE_DIR",
    "DATA_END",
    "DATA_QUALITY_REPORT",
    "DATA_START",
    "DOCS_DIR",
    "FIGURES_DIR",
    "HOURS_PER_DAY",
    "INTERVALS_PER_DAY",
    "INTERVAL_MINUTES",
    "PRICE_RULES",
    "PROBLEM_TXT",
    "PROCESSED_DIR",
    "RAW_DIR",
    "RESULT2_END",
    "RESULT2_START",
    "RESULT_TEMPLATES",
    "RESULTS_DIR",
    "STORAGE",
    "VALIDATION_REPORT",
    "PriceRules",
    "StorageParams",
    "ensure_output_dirs",
    "result_path",
]
