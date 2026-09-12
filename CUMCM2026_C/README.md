# CUMCM2026 C题 · 目录说明

> 微网与外部电网电力调控策略。本目录是**本题唯一的工作根**，所有脚本与产物都在这里。

## 目录结构

```
CUMCM2026_C/
├── README.md                 ← 本文件：目录职责与命名规则（唯一权威说明）
│
├── 00_problem/               题目与附件（只读，禁止修改）
│   ├── C题.txt               题目原文（与 C题.pdf 逐字节一致的权威文本）
│   ├── C题_pdf_layout.txt    由 PDF 提取的版式文本（核对用）
│   ├── C题_pdf_raw.txt       由 PDF 提取的原始文本（核对用）
│   ├── 附件/                  ★ 唯一权威只读输入
│   │   ├── 附件1.xlsx         某天 10 分钟粒度的电价 / 负载 / 光伏预测
│   │   ├── 附件2.xlsx         2025 全年小区负载 + 光伏实际功率（365×145）
│   │   ├── 附件3.xlsx         2025 全年光伏预报（1460 行 × 4 预报时刻）
│   │   ├── 附件4.xlsx         2025 全年 10 分钟粒度实时电价（365×145）
│   │   └── 附件5/             result1~result4-3 结果模板（只读）
│   └── preview/              题目 PDF 的 3 页渲染图（核对表格排版用）
│
├── common/                   跨问共享（四个问题都用）
│   ├── code/                 通用代码包
│   │   ├── paths.py          ★ 全部路径与题目参数（唯一权威来源）
│   │   ├── io_attachments.py 附件读取 + 结果模板列/行标签口径
│   │   ├── check_data.py     数据质量核查
│   │   └── validate_results.py  result*.xlsx 验收校验
│   ├── docs/                 跨问口径文档与机读契约
│   │   ├── problem_c_contract.json        ★ 机读契约（口径裁定/假设/输出规格）
│   │   ├── model_variables.json           变量与参数契约
│   │   ├── C题_统一分析结论.md            四问统一结论 + P1 权威参考解
│   │   ├── C题_三方一致性核对.md          A1–A21 裁定与证据
│   │   ├── C题_问题分析与数学建模框架.md  四问数学模型
│   │   ├── C题_数据工程与结果规格.md      数据规格与写入规格
│   │   └── C题_论文框架与交付清单.md      论文结构、表1/2/3 定义、图清单
│   ├── diagnostics/          核查与验收报告（JSON）＋ 验证日志（txt）
│   └── tools/                可复现脚本（体检/核查/对账/重构）
│
├── Q1/  Q2/  Q3/  Q4/        按问分目录，四问结构完全一致
│   ├── Qn_<描述>.py          该问的求解脚本（单一自包含入口）
│   ├── outputs/
│   │   ├── resultN.xlsx      ★ 该问的提交结果文件（从模板复制后填数）
│   │   └── figures/          ★ 该问的论文插图 PNG
│   ├── 问题N模型的建立.md     只写方法（禁含结果数字）
│   └── 问题N模型的求解.md     只写结果与图表解读
│
└── paper/                    论文汇总
    ├── paper_skeleton.md     论文骨架（标题就位、表格空壳）
    └── CUMCM2026_C_analysis.univer   Univer 分析容器（6 Sheet + 4 Doc）
```

## 结果文件归属（重要）

每个 `result*.xlsx` 只属于一个问，**不要写错目录**：

| 结果文件 | 归属 | 写入位置 |
|---|---|---|
| `result1.xlsx` | 问题 1 | `Q1/outputs/` |
| `result2.xlsx` | 问题 2 | `Q2/outputs/` |
| `result3.xlsx` | 问题 3 | `Q3/outputs/` |
| `result4-2.xlsx` | 问题 4（对应问题 2） | `Q4/outputs/` |
| `result4-3.xlsx` | 问题 4（对应问题 3） | `Q4/outputs/` |

代码里用 `paths.result_path("result2")` 取路径，它会自动路由，**不要手拼字符串**。

## 命名规则

| 类型 | 规则 | 示例 |
|---|---|---|
| 求解脚本 | `Qn_<描述>.py`，放在 `Qn/` 根 | `Q1_solve_plan.py` |
| 结果文件 | `resultN.xlsx`（题目规定的文件名，不可改） | `result1.xlsx` |
| 图 | `fig_NN_<slug>.png`（遵循仓库 `TEAM_COLLABORATION.md`） | `fig_03_day_triplet.png` |
| 章节 | `问题N模型的建立.md` / `问题N模型的求解.md` | `问题一模型的建立.md` |
| 诊断日志 | `Qn_<描述>.log` 或结果簿里的 `诊断日志` 工作表 | — |

## 用法

在**仓库根目录**执行（`paths.py` 用相对层级定位，换目录会失败）：

```powershell
$env:PYTHONUTF8 = "1"

# 数据质量核查（输出到 common/diagnostics/）
.\.venv\Scripts\python.exe -m CUMCM2026_C.common.code.check_data

# 结果文件验收（result*.xlsx 生成后运行）
.\.venv\Scripts\python.exe -m CUMCM2026_C.common.code.validate_results

# 某问的求解脚本
.\.venv\Scripts\python.exe CUMCM2026_C\Q1\Q1_solve_plan.py
```

脚本内导入共享代码：

```python
from CUMCM2026_C.common.code import paths, io_attachments
```

图脚本必须按 skill 要求显式指定后端：

```python
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
```

## 两条硬纪律

1. **`00_problem/` 只读**。附件与模板永不修改；写结果一律"从 `附件5/result*.xlsx` 复制后填数"，不用 openpyxl 从零构造。
2. **口径以 `common/docs/problem_c_contract.json` 为准**。列名/行标签必须按**字符串**匹配，禁止按序号算术推断（模板存在整体错位一格的陷阱）。

## 已知环境事实

- Python：仓库根 `.venv`（54 个包），在仓库根调用，例如 `.\.venv\Scripts\python.exe`
- `read_document` / `read_image` 工具：由 `dsh-files` 插件提供，已装载
- matplotlib 默认后端即 `tkagg`，中文字体（Microsoft YaHei / SimHei 等）可用
- 无 OCR 引擎；若遇无文本层 PDF，需先加装 OCR

## 历史

本目录由 `common/tools/restructure_repo.py` 从"按类别分目录"（原 `data/`、`src/`、`docs/`、`tools/`、`reports/`）
重构而来，搬运清单见 `common/docs/_restructure_manifest.json`。
原始题目目录 `CUMCM2026Problems/` 未改动，作为出厂副本保留。
