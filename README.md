# math-modeling-2026

这是 2026 数学建模竞赛的基础工作仓库，用于统一存放数据、代码、图表、结果和论文材料。

## 目录结构

**本题（CUMCM2026 C题）的工作根是 `CUMCM2026_C/`，采用"按问分目录"结构。**
完整说明见 [`CUMCM2026_C/README.md`](CUMCM2026_C/README.md)。

```
CUMCM2026_C/
├── 00_problem/     题目原文 + 附件（只读，唯一权威输入）
├── common/         跨问共享：code / docs / diagnostics / tools
├── Q1/ Q2/ Q3/ Q4/ 每问：求解脚本 + outputs/(结果与图) + 两份章节 Markdown
└── paper/          论文骨架与 Univer 分析容器
```

仓库级目录：

- `CUMCM2026Problems/`：官方题目与附件的**出厂副本**（只读，不改动，仅作核对）
- `notebooks/`：探索性分析（`template.ipynb` 为比赛模板）
- `.dsh/skills/`：本仓库挂载的数模专用 skill
- `.venv/`：独立虚拟环境

> 注：`data/`、`src/`、`docs/`、`tools/`、`figures/`、`reports/`、`results/` 是**重构前的按类别目录**，
> 内容已迁入 `CUMCM2026_C/`，现仅保留空骨架与 `.gitkeep`。

## 环境配置

项目已配置独立虚拟环境 `.venv`（Python 3.13，含 pandas/numpy/scipy/matplotlib/openpyxl 等 54 个包）。

> ⚠️ **在 DSH 会话内不要执行 `pip install`** —— 文件沙箱会拒绝 pip 的临时目录操作。
> 手工装包请在普通 PowerShell 窗口执行：
>
> ```powershell
> cd D:\MathModeling\math-modeling-2026
> .\.venv\Scripts\python.exe -m pip install <包名>
> ```

## VS Code 设置

用 VS Code 打开本文件夹后，工作区会默认使用：

`${workspaceFolder}\.venv\Scripts\python.exe`

如果 VS Code 询问 Python 解释器，请选择上面的虚拟环境解释器。

## 基本流程

1. 题目与附件放在 `CUMCM2026_C/00_problem/`（只读）。
2. 数据核查与通用代码放在 `CUMCM2026_C/common/`。
3. 第 N 问的求解脚本、结果、图与章节放在 `CUMCM2026_C/QN/`。
4. 结果文件 `result*.xlsx` 从 `00_problem/附件/附件5/` 模板复制后填数，写入对应 `QN/outputs/`。
5. 论文汇总放在 `CUMCM2026_C/paper/`。
6. 运行任何脚本前先 `Set-Location` 到仓库根目录（`paths.py` 依赖相对层级定位）。

## 起始文件

- `CUMCM2026_C/README.md`：本题目录职责与命名规则（**先看这个**）
- `notebooks/template.ipynb`：比赛用 notebook 模板
- `TEAM_COLLABORATION.md`：队伍协作规范
