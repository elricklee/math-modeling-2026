"""CUMCM2026 C题 跨问共享代码包。

本包汇总四个问题共用的数据读取、口径常量与校验逻辑：

* :mod:`paths` —— 全部路径与题目参数（唯一权威来源，禁止别处硬编码）
* :mod:`io_attachments` —— 附件 1~4 与结果模板的读写（含模板列/行标签口径）
* :mod:`check_data` —— 附件数据质量核查
* :mod:`validate_results` —— ``result*.xlsx`` 结构与非负性/闭合性验收

调用方式（在仓库根目录执行）::

    python -m CUMCM2026_C.common.code.check_data
    python -m CUMCM2026_C.common.code.validate_results

各问脚本建议这样导入::

    from CUMCM2026_C.common.code import paths, io_attachments
"""

from __future__ import annotations

__all__ = ["check_data", "io_attachments", "paths", "validate_results"]
