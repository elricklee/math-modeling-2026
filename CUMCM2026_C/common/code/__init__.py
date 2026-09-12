"""CUMCM2026 C题 共享代码模块。

模块划分
--------
* :mod:`paths` —— 统一路径、时间轴与题目参数常量（唯一权威来源）。
* :mod:`io_attachments` —— 附件 1~4 加载器与结果模板读写工具。
* :mod:`check_data` —— 数据质量核查，输出
  ``CUMCM2026_C/common/diagnostics/data_quality_report.json``。
* :mod:`validate_results` —— ``result*.xlsx`` 结构与非负性/闭合性验收，
  输出 ``CUMCM2026_C/common/diagnostics/result_validation_report.json``。

命令行入口（在仓库根目录执行）::

    python -m CUMCM2026_C.common.code.check_data
    python -m CUMCM2026_C.common.code.validate_results
"""

from __future__ import annotations

__all__ = [
    "check_data",
    "io_attachments",
    "paths",
    "validate_results",
]
