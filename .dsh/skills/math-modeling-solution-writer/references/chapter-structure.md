# Solution Chapter Structure

Use this reference to organize "模型的求解" chapters by task type.

## General Structure

A strong solution chapter usually follows:

1. Brief link to the established method.
2. Data/split/sample situation, if relevant to interpreting results.
3. Parameter estimation or indicator calculation results.
4. Model comparison and selected model.
5. Required prediction/classification/optimization answer.
6. Figure-by-figure interpretation.
7. Short conclusion that directly answers the subproblem.

Do not present this as a numbered list in the final prose. Convert it into natural section headings and paragraphs.

## Factor Screening And Function Fitting

Suggested sections:

- 主因素筛选结果
- 多变量函数拟合与参数解释
- 模型误差与外推检验
- 指定日期预测结果

Include:

- Top factor table with direction and strength.
- Candidate function comparison table.
- Parameters of the selected or representative function.
- Required target-date prediction table.
- Figure descriptions for factor ranking, function performance, residual/scatter, marginal effects, and target predictions.

Interpret carefully:

- A statistically significant variable may not be a main engineering factor.
- A weak or non-significant coefficient can still be included for process logic.
- Boundary-hit parameters indicate weak identifiability and should be described cautiously.

## Time-Lag Dynamic Modeling

Suggested sections:

- 时滞先验结果
- 候选模型训练与性能比较
- 变量-滞后敏感度分析
- 闭环预测结果

Include:

- CCF/MI lag table.
- Model comparison table.
- Attention or gradient lag interpretation table.
- Required prediction summary.
- Overall prediction error if actual target values are available.

Interpret carefully:

- CCF describes marginal lag; deep-model sensitivity describes conditional local influence.
- A strong autoregressive channel may dominate external variables.
- If R2 is misleading, report RMSE/MAE and avoid emphasizing R2.

## Mechanism-Data Hybrid Modeling

Suggested sections:

- 物理参数辨识结果
- 物理模型、纯数据模型与混合模型对比
- 多步预测结果
- 敏感性分析

Include:

- Physical parameter table.
- Multi-horizon error table.
- Model comparison table.
- Required rolling prediction table.
- Sensitivity summary table.

Interpret carefully:

- Check whether physical parameters remain in engineering ranges.
- State where the hybrid model improves over the pure physical baseline.
- Treat perturbation response as model sensitivity, not causal proof.

## Risk Evaluation Or Classification

Suggested sections:

- 缺失值插补或评价数据准备结果
- 日级指标与权重结果
- 风险等级判别结果
- 指定月份/对象的详细分类

Include:

- Imputation model diagnostics and feature importance, if used.
- Indicator distribution and entropy weight table.
- Level counts and percentages.
- Detailed classification table requested by the problem.
- Figure descriptions for time series, stacked proportions, indicator/weight distributions, and calendar/maps.

Interpret carefully:

- Separate hard-threshold triggers from score-based gray-zone triggers.
- State which outputs rely on imputed values.
- Explain high-risk or medium-risk cases by rule branches and observed indicators.
