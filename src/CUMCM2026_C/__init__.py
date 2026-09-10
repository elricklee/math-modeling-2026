"""CUMCM2026 C题（微网与外部电网电力调控策略）数据与代码骨架。

模块划分
--------
* :mod:`src.CUMCM2026_C.paths` —— 统一路径、时间轴与题目参数常量。
* :mod:`src.CUMCM2026_C.io_attachments` —— 附件 1~4 加载器与时间轴工具函数。
* :mod:`src.CUMCM2026_C.check_data` —— 数据质量核查，输出
  ``data/processed/CUMCM2026_C/data_quality_report.json``。
* :mod:`src.CUMCM2026_C.validate_results` —— ``result*.xlsx`` 验收校验。

命令行入口::

    python -m src.CUMCM2026_C.check_data
    python -m src.CUMCM2026_C.validate_results
"""

from __future__ import annotations

__all__ = [
    "check_data",
    "io_attachments",
    "paths",
    "validate_results",
]
