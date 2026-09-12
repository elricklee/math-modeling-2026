# Method Patterns

Use this reference when the user gives only a question number, gives a vague idea, or asks for a method choice.

## Start From The Question Verb

Map the problem requirement to a method family before coding:

| Requirement wording | Good first method family | Useful baselines |
|---|---|---|
| 筛选主要因素 / 解释方向与程度 | Statistical tests, correlation, mutual information, explicit regression formulas | Linear regression, robust regression |
| 建立函数关系 / 参数拟合 | Multiple interpretable formulas with parameter tables and confidence intervals | Linear/additive formula |
| 存在时滞 / 动态响应 | CCF/MI lag analysis, ARDL, distributed lag model, sequence model | ARDL-LASSO, lagged linear model |
| 预测未来 1-n 小时 | Sliding windows, direct multi-output model, recursive/closed-loop model | Persistence, AR model |
| 结合机理 / 质量守恒 / 守恒方程 | Physical baseline plus residual model or constrained optimization | Pure physical rollout |
| 风险评价 / 分级 / 排名 | Indicator system, hard threshold rules, entropy weight/CRITIC/TOPSIS, rule audit | Single-threshold rule |
| 优化投放 / 调度 / 参数寻优 | Objective function plus constraints, grid search, differential evolution, PSO/GA, local polish | Current-operation baseline |

## If The User Supplies A Method

Treat it as the main route, but check four things:

1. Does the data contain the required target during training?
2. Does the method need future variables that are unavailable at prediction time?
3. Does the method answer all required deliverables, including specified dates/tables?
4. Is there a simpler baseline needed to prove the complex method is worthwhile?

If a mismatch exists, implement the requested method with a baseline or fallback rather than silently changing the method.

## If The User Gives No Method

Choose a route with this priority:

1. Satisfy the exact contest deliverable.
2. Avoid data leakage and impossible assumptions.
3. Prefer interpretable models when the question asks for factors, mechanisms, or formulas.
4. Use complex predictive models when the question asks for accuracy, nonlinear dynamics, or multi-step forecasting.
5. Add enough diagnostics to support later paper writing.

## Data-Scope Heuristics

Use time-aware splits for time series. Do not random-split rows unless the task is clearly non-temporal or the output is only descriptive.

For contest datasets with prediction periods:

- Historical complete period: train.
- Closest observed period before target: validation.
- Observed period after target: posterior robustness check, if allowed.
- Target period with missing target: prediction only.

Keep both natural-date and operation-date concepts if the process crosses midnight. Use the date口径 required by the question for final outputs.

## Model Families To Keep Handy

For factor/formula tasks:

- Spearman, Pearson, Kendall, Levene, ANOVA, Mann-Whitney U, mutual information.
- Linear, polynomial, log-linear, power-law, Hill/saturation, interaction, Cobb-Douglas-like formulas.
- Parameter table with estimates, confidence intervals, sign, significance, and boundary checks.

For lag/dynamic tasks:

- CCF/MI lag table across 0 to max lag.
- ARDL/lagged linear model as a baseline.
- TCN, GRU/LSTM with attention, CNN-LSTM, random forest/GBDT with lag features.
- Gradient or permutation sensitivity over variable and lag position.

For hybrid mechanism tasks:

- Define physical state equation and discretization.
- Estimate physical parameters under engineering bounds.
- Compare pure physical, pure data-driven, and hybrid residual/PINN models.
- Report whether learned parameters remain in a plausible domain.

For risk/ranking tasks:

- Build interpretable indicators before scoring.
- Preserve hard standards as direct rules.
- Use objective weights only for soft ranking or gray-zone decisions.
- Export daily/entity-level detailed classification and aggregate statistics.
