# math-modeling-2026（高教社杯 C 题：微网与外部电网电力调控策略）

2026 数学建模竞赛工作仓库。四问已全部采用统一的三层管线求解并落盘：**SARIMA 因果预测层 → 随机规划决策层 → 轨迹保护自适应储能执行层**。

## 四问最终结果

| 问题 | 结果文件 | 全年总费用 |
|---|---|---:|
| 问题1（典型日确定性 LP） | `results/CUMCM2026_C/result1.xlsx` | 35,126.95 元 |
| 问题2（日前计划 + 紧急购电） | `results/CUMCM2026_C/result2.xlsx` | 14,697,898 元 |
| 问题3（多时刻预报计划—调整，严格口径） | `results/CUMCM2026_C/result3.xlsx` | 14,620,483 元 |
| 问题4（波动电价重算 2/3） | `results/CUMCM2026_C/result4-2.xlsx`、`result4-3.xlsx` | 15,565,543 / 15,463,091 元 |

五份工作簿经 `python -m src.CUMCM2026_C.validate_results` 验收：67 项通过、0 失败。

## 目录结构

- `CUMCM2026Problems/C题/`：题面（PDF/TXT）与原始附件 1–5
- `data/raw/C题/`：附件的工作副本（gitignore，丢失时从上一条目录复制）
- `data/processed/CUMCM2026_C/`：中间结果与审计 JSON（逐时段明细、调参网格、验证报告、SARIMA 预测缓存）
- `src/CUMCM2026_C/`：求解管线——`dispatch.py`（因果仿真引擎）、`sarima_plan.py`（问题2 预测层）、`sp_plan.py`（问题2 两阶段随机规划）、`sp_rolling.py`（问题3 多阶段随机规划与通用情景 LP）、`sp_volatile.py`（问题4 波动电价）、`export_results.py`（写盘）、`validate_results.py`（验收）
- `tools/`：实验与工具脚本（SARIMA 预计算、调参、论文图 `make_paper_figures.py` 等）
- `tests/`：dispatch 行为测试
- `docs/`：口径裁定与采用记录（见下文索引）
- `paper/`：四份逐问论文框架（含目标方程、约束、策略表、口径声明、成品数字）
- `pictures/`：19 张论文图，按 `问题1`–`问题4` 分目录，编号与论文框架一一对应
- `results/CUMCM2026_C/`：五份结果工作簿（最终交付物）
- `figures/`、`reports/`：预留

## 环境配置

项目使用根目录虚拟环境 `.venv`（Python 3.13）。重建：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

依赖已合并为单文件 `requirements.txt`：必需项为 numpy / scipy / openpyxl / statsmodels / matplotlib（版本为实测可用组合），可选项（jupyter、pandas、black、ruff）供探索与格式化使用。

## 复现流程

```powershell
# 0) 确认 data/raw/C题/ 下有附件1-4.xlsx 与附件5/（没有则从 CUMCM2026Problems/C题/附件/ 复制）

# 1) 生成 SARIMA 预测缓存（约 3.5 分钟；问题2/3/4 的求解都依赖它）
python -m src.CUMCM2026_C.sarima_plan precompute A

# 2) 逐问求解（会写入 data/processed/CUMCM2026_C/*.json）
python -m src.CUMCM2026_C.sp_plan            # 问题2 调参网格（约 25 分钟；正式结果取 K=200, λ=1.0）
python -m src.CUMCM2026_C.sp_rolling --strict  # 问题3 严格口径（约 16 分钟）
python -m src.CUMCM2026_C.sp_volatile          # 问题4-2（约 6 分钟）
python -m src.CUMCM2026_C.sp_volatile --q3     # 问题4-3（约 16 分钟）

# 3) 结果验收
python -m src.CUMCM2026_C.validate_results

# 4) 论文图重生成（pictures/ 全部 19 张）
python tools/make_paper_figures.py
```

结果工作簿的正式写盘方式（`run(...) + export_results.export_scenario`，含 adaptive_storage=True）记录在各问采用文档中；`dispatch.py` 的可选项（预测器钩子、计划钩子、自适应储能）默认关闭，默认路径与历史基线逐位一致。

## 文档索引

- 口径总纲与数据勘察：`docs/C题_统一分析结论.md`
- 采用记录：`docs/C题_问题2方案三正式采用记录.md`、`docs/C题_问题3严格口径采用记录.md`、`docs/C题_问题4波动电价采用记录.md`
- 修订历史：`docs/C题_版本对照与修正记录.md`
- 论文写作入口：`paper/问题1_论文框架.md` … `paper/问题4_论文框架.md`

## 协作

队伍分工与提交规范见 `TEAM_COLLABORATION.md`。
