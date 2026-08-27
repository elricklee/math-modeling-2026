# math-modeling-2026

这是 2026 数学建模竞赛的基础工作仓库，用于统一存放数据、代码、图表、结果和论文材料。

## 目录结构

- `data/raw/`：原始数据，保持题目附件的原貌
- `data/processed/`：清洗后的数据和中间数据集
- `notebooks/`：探索性分析、建模实验和临时验证
- `src/`：可复用的 Python 代码
- `figures/`：论文中使用的图表
- `reports/`：论文草稿、最终论文和提交材料
- `results/`：模型输出、中间结果和评价指标

## 环境配置

项目已经配置了独立虚拟环境 `.venv`。如果需要重新创建环境，可以在仓库根目录执行：

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## VS Code 设置

用 VS Code 打开本文件夹后，工作区会默认使用：

`${workspaceFolder}\.venv\Scripts\python.exe`

如果 VS Code 询问 Python 解释器，请选择上面的虚拟环境解释器。

## 基本流程

1. 将题目附件和原始数据放入 `data/raw/`。
2. 将清洗后的数据保存到 `data/processed/`。
3. 在 `notebooks/` 中进行探索性分析和建模实验。
4. 将稳定、可复用的函数整理到 `src/`。
5. 将论文图表导出到 `figures/`。
6. 将论文草稿和最终提交文件保存到 `reports/`。

## 起始文件

- `notebooks/template.ipynb`：比赛用 notebook 模板
- `TEAM_COLLABORATION.md`：队伍协作规范
