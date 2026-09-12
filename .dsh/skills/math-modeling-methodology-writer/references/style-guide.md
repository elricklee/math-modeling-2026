# Style Guide

Use this reference when polishing the final methodology chapter.

## Default Tone

Write like a serious Chinese mathematical modeling paper:

- Concrete and explanatory.
- Method-focused, not promotional.
- Moderate sentence length.
- Connected paragraphs instead of list-like fragments.
- Technical terms preserved exactly.

## Common User Requirements

The user usually wants:

- Draft first with `nature-writing`, then revise with `humanizer-zh`.
- Detailed formulas and text-table descriptions.
- Coherent language, not excessive bullet points.
- Long and detailed methodology.
- Markdown output.
- Strict LaTeX formulas for later recognition.
- Humanizer-style removal of AI traces.
- No result writing in the establishment chapter.

## Nature-Writing Drafting Pass

Before polishing, draft the methodology chapter using `nature-writing` principles:

- Define the chapter's one-sentence argument: what modeling idea connects the task, variables, and algorithm.
- Build a clear evidence chain from problem requirement to variables, formulas, model structure, and procedure.
- Use section structure to guide the reader, but avoid exposing code-stage labels.
- Keep method choices tied to the contest question and final code, not generic textbook exposition.
- Leave result claims for the solution chapter.

## Humanizer-Style Editing Rules

Apply these edits silently:

- Remove empty praise such as "具有重要意义", "充分体现", "显著优越" unless supported by results and appropriate for the solution chapter.
- Avoid repeated transitions such as "首先、其次、最后" in every paragraph.
- Avoid "不仅...而且..." and other mechanical parallel structures.
- Avoid vague attributions like "研究表明" unless a specific source is cited.
- Replace overclaims such as "证明" with "表明", "用于", "支持", or "刻画".
- Keep formulas close to the paragraph that explains them.
- Use tables for symbol lists and model components, not for decorative summaries.

## Section Headings

Prefer headings such as:

- 任务定位与建模思路
- 主因素的统计学筛选
- 多变量函数关系的构造
- 时滞先验估计
- 滑动窗口样本构造
- 清水池质量守恒模型
- 物理一致性损失
- 日级风险指标体系
- 综合得分与判别规则

Avoid code labels such as:

- STAGE A
- stage_b
- Step 1 / Step 2 as visible headings

## Formula Formatting

Use Markdown math:

- Inline: `$x_t$`
- Display:

```latex
$$
L(\theta)=\frac{1}{n}\sum_{i=1}^{n}(y_i-\hat y_i)^2 .
$$
```

Keep variable names readable. If raw variable names contain slashes or dots, introduce mathematical aliases:

```text
记原水浊度 `R/W NTU` 为 $x_{1,t}$，滤后水浊度 `FILT. NTU` 为 $x_{2,t}$。
```

## Markdown Output

If saving a file, use a filename like:

- `问题一模型的建立.md`
- `问题二模型的建立.md`
- `模型的建立.md`

Place it in the corresponding `Q1`, `Q2`, `Q3`, or `Q4` folder when obvious or requested.
