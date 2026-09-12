# Style Guide

Use this reference when polishing the final "模型的求解" chapter.

## User's Default Requirements

Unless the user changes them, write:

- Draft first with `nature-writing`, then revise with `humanizer-zh`.
- Chinese Markdown.
- Detailed and paper-ready.
- Coherent paragraphs, not excessive bullet points.
- Strict LaTeX formulas where formulas are needed.
- Brief description for every final figure and table.
- Some important results directly as Markdown tables.
- Humanizer-style language: restrained, natural, and not template-like.

## Nature-Writing Drafting Pass

Before polishing, draft the solution chapter using `nature-writing` principles:

- Define the chapter's result argument: what the extracted metrics, tables, and figures collectively answer.
- Arrange evidence in a reader-friendly sequence rather than following raw file order mechanically.
- Connect every table and figure to the subproblem requirement.
- State limitations, weak metrics, or counterintuitive responses where the evidence requires it.
- Avoid re-deriving the full methodology already written in the establishment chapter.

## Tone

Use concrete contest-paper prose:

- "从表中可以看到..."
- "该结果说明..."
- "这一现象与...一致"
- "需要注意的是..."

Avoid:

- "充分证明", "显著优越", "极大提升" unless the evidence is strong and quantified.
- Repeated "首先、其次、最后".
- Empty endings such as "具有广阔应用前景".
- Long bullet lists that read like generated notes.

## Connection To 模型的建立

Start each subsection with a short bridge from the established method:

"按照上一节构造的六类候选函数，对段A样本进行参数估计..."

Then move quickly to results. Do not re-explain every formula.

## Figure Writing

For each figure:

1. Name what the figure displays.
2. Describe the main visible pattern.
3. Connect it to one result claim.

Example:

"图X给出了三类模型在不同预测步上的误差变化。随着预测步长增加，纯物理模型误差上升更快，而混合模型在中近视野保持较低误差，说明残差网络对清水池短期动态有补偿作用。"

## Table Writing

Before a table, say why the table is included. After it, explain the important rows, not every cell.

Use publication-friendly headers:

- `模型`
- `RMSE`
- `MAE`
- `运行日`
- `预测均值`
- `风险等级`

Clean raw Excel headers such as `Unnamed: 0`.

## Common Section Titles

- 主因素筛选结果
- 函数拟合与参数估计结果
- 模型比较与预测结果
- 时滞识别与模型性能
- 物理参数辨识结果
- 三日滚动预测结果
- 敏感性分析
- 风险等级判别结果
- 逐日分类详情

## Markdown File Naming

Save to the corresponding question folder when obvious:

- `问题一模型的求解.md`
- `问题二模型的求解.md`
- `问题三模型的求解.md`
- `问题四模型的求解.md`
