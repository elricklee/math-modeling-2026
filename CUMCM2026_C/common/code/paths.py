"""CUMCM2026 C题（微网与外部电网电力调控策略）统一路径与全局常量。

目录约定（按 skill 的"按问分目录"结构，详见 ``CUMCM2026_C/README.md``）
------------------------------------------------------------------
* 题目与附件一律**只读**：位于 ``CUMCM2026_C/00_problem``。
* 每问的脚本、结果与章节写入 ``CUMCM2026_C/Qn``（n = 1..4）。
  - 结果文件 ``result*.xlsx`` 写入 ``Qn/outputs``
  - 图形写入 ``Qn/outputs/figures``
  - 章节 Markdown 写入 ``Qn`` 根
* 跨问共享的代码/文档/诊断报告位于 ``CUMCM2026_C/common``。
* 论文汇总与 Univer 分析容器位于 ``CUMCM2026_C/paper``。
* 储能与电价等题目参数集中在 :data:`STORAGE` 与 :data:`PRICE_RULES`，
  建模脚本不得在别处硬编码这些数字。

本模块只依赖标准库，可被任何阶段（数据核查 / 求解 / 校验 / 绘图）安全导入。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# --------------------------------------------------------------------------- #
# 仓库根与题目根
# --------------------------------------------------------------------------- #
# 本文件位于 <repo>/CUMCM2026_C/common/code/paths.py，故向上 3 层即仓库根。
ROOT: Path = Path(__file__).resolve().parents[3]
"""仓库根目录。"""

CASE_ROOT: Path = ROOT / "CUMCM2026_C"
"""本题（CUMCM2026 C题）的工作根目录。"""

# --------------------------------------------------------------------------- #
# 路径
# --------------------------------------------------------------------------- #
PROBLEM_DIR: Path = CASE_ROOT / "00_problem"
"""题目原文与附件所在目录（只读，唯一权威输入）。"""

CASE_DIR: Path = ROOT / "CUMCM2026Problems" / "C题"
"""原始题目目录（只读；pdf 与附件的出厂副本，仅作核对用）。"""

PROBLEM_TXT: Path = PROBLEM_DIR / "C题.txt"
"""题目原文（权威文本，与 PDF 逐字节一致）。"""

RAW_DIR: Path = PROBLEM_DIR / "附件"
"""附件 1~4 与附件 5 结果模板所在目录（只读，禁止修改）。"""

ATTACHMENT_5_DIR: Path = RAW_DIR / "附件5"
"""附件 5 结果模板目录（只读）。"""

PROCESSED_DIR: Path = CASE_ROOT / "common" / "diagnostics"
"""清洗产物与核查报告输出目录（跨问共享）。"""

COMMON_DIR: Path = CASE_ROOT / "common"
"""跨问共享代码、文档与诊断报告的根目录。"""

COMMON_DOCS_DIR: Path = COMMON_DIR / "docs"
"""跨问口径文档与机读契约目录。"""

PAPER_DIR: Path = CASE_ROOT / "paper"
"""论文汇总与 Univer 分析容器目录。"""


def question_dir(n: int | str) -> Path:
    """返回第 ``n`` 问的目录，例如 ``question_dir(2)`` -> ``CUMCM2026_C/Q2``。"""
    return CASE_ROOT / f"Q{n}"


def question_outputs(n: int | str) -> Path:
    """返回第 ``n`` 问的结果输出目录（``Qn/outputs``）。"""
    return question_dir(n) / "outputs"


def question_figures(n: int | str) -> Path:
    """返回第 ``n`` 问的图形输出目录（``Qn/outputs/figures``）。"""
    return question_outputs(n) / "figures"


RESULTS_DIR: Path = question_outputs(1)
"""``result*.xlsx`` 生成目录的默认值（问题 1）。

注意：``result1`` 属问题 1，``result2`` 属问题 2，依此类推；
请用 :func:`result_path` 取正确路径，它按文件名自动路由到对应 ``Qn/outputs``。
"""

FIGURES_DIR: Path = question_figures(1)
"""图形输出目录的默认值（问题 1）；请优先用 :func:`question_figures`。"""

DOCS_DIR: Path = COMMON_DOCS_DIR
"""文档输出目录（跨问共享）。"""

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

# 结果文件名 -> 归属问题号（决定写入哪个 Qn/outputs）
RESULT_OWNER: dict[str, int] = {
    "result1": 1,
    "result2": 2,
    "result3": 3,
    "result4-2": 4,
    "result4-3": 4,
}
"""结果文件的归属问题号，供 :func:`result_path` 自动路由。"""

DATA_QUALITY_REPORT: Path = PROCESSED_DIR / "data_quality_report.json"
"""数据质量核查报告输出路径。"""

VALIDATION_REPORT: Path = PROCESSED_DIR / "result_validation_report.json"
"""结果文件验收报告输出路径。"""


def result_path(name: str) -> Path:
    """返回某份结果文件的写入路径，例如 ``result_path("result1")``。

    自动按 :data:`RESULT_OWNER` 路由到对应 ``Qn/outputs`` 目录。

    Args:
        name: 逻辑名之一：``result1`` / ``result2`` / ``result3`` /
            ``result4-2`` / ``result4-3``（也接受带 ``.xlsx`` 后缀的写法）。

    Returns:
        位于对应问题 ``Qn/outputs`` 下的目标路径（不保证已存在）。
    """
    stem = name[:-5] if name.endswith(".xlsx") else name
    owner = RESULT_OWNER.get(stem)
    if owner is None:
        return RESULTS_DIR / f"{stem}.xlsx"
    return question_outputs(owner) / f"{stem}.xlsx"


def ensure_output_dirs() -> None:
    """创建全部输出目录（幂等）。题目与附件目录不在其中，永不被创建或改动。

    建立：跨问诊断目录、四个问题的 ``Qn/outputs[/figures]``、论文目录。
    """
    targets = [PROCESSED_DIR, COMMON_DOCS_DIR, PAPER_DIR]
    for n in (1, 2, 3, 4):
        targets.append(question_dir(n))
        targets.append(question_figures(n))
    for directory in targets:
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
    "CASE_ROOT",
    "COMMON_DIR",
    "COMMON_DOCS_DIR",
    "DATA_END",
    "DATA_QUALITY_REPORT",
    "DATA_START",
    "DOCS_DIR",
    "FIGURES_DIR",
    "HOURS_PER_DAY",
    "INTERVALS_PER_DAY",
    "INTERVAL_MINUTES",
    "PAPER_DIR",
    "PRICE_RULES",
    "PROBLEM_DIR",
    "PROBLEM_TXT",
    "PROCESSED_DIR",
    "RAW_DIR",
    "RESULT2_END",
    "RESULT2_START",
    "RESULT_OWNER",
    "RESULT_TEMPLATES",
    "RESULTS_DIR",
    "ROOT",
    "STORAGE",
    "VALIDATION_REPORT",
    "PriceRules",
    "StorageParams",
    "ensure_output_dirs",
    "question_dir",
    "question_figures",
    "question_outputs",
    "result_path",
]
