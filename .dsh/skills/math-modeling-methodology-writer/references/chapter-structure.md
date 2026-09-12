# Chapter Structure Patterns

Use this reference to shape a methodology-only "模型的建立" chapter.

## General Structure

For most subproblems, use this sequence:

1. 任务定位与建模思路
2. 符号与变量定义
3. 数据样本或指标构造
4. 核心模型建立
5. 参数估计、训练目标或判别规则
6. 预测、分类或优化流程
7. 方法小结

Convert numbered items into natural section headings and paragraphs in the final chapter. Do not leave a list-like skeleton.

## Factor Screening And Formula Fitting

Use when code performs factor screening, effect direction, or explicit functional relationships.

Suggested sections:

- 主因素筛选的统计学依据
- 影响方向与作用强度定义
- 多变量函数关系构造
- 参数估计与约束
- 指定日期预测流程

Formula ingredients:

- Spearman, Pearson, Kendall, Levene, ANOVA, Mann-Whitney U, mutual information.
- Composite effect size and significance count, if used.
- Candidate function formulas.
- Least squares or nonlinear curve fitting objective.
- Parameter confidence interval or boundary-check method, if coded.

## Time-Lag Dynamic Modeling

Use when the code handles lag effects, sequence windows, ARDL, TCN, GRU, LSTM, attention, or closed-loop prediction.

Suggested sections:

- 动态预测任务与输入变量
- 时滞先验估计
- 滑动窗口监督样本构造
- 自回归通道与闭环预测
- 候选模型族与训练目标
- 变量-滞后敏感度反演

Formula ingredients:

- Lagged cross-correlation.
- Mutual information.
- Window tensor definition.
- Standardization formula.
- Neural network prediction map.
- Loss function and early stopping rule.
- Recursive or closed-loop update rule.

## Mechanism-Data Hybrid Modeling

Use when code includes physical equations, conservation laws, PINN, state-space modeling, residual learning, or parameter bounds.

Suggested sections:

- 物理过程与状态变量
- 质量守恒或机理方程
- 离散化与物理基线
- 工程约束下的参数辨识
- 数据驱动残差模型
- 物理一致性损失与训练协议
- 多步预测与敏感性分析方法

Formula ingredients:

- Continuous state equation.
- Discrete rollout equation.
- Engineering-bounded parameterization.
- Huber/MSE objective for physical identification.
- Hybrid prediction equation, such as physical baseline plus gated residual.
- Total loss with data and physics terms.

## Risk Evaluation Or Classification

Use when code builds levels, risk scores, entropy weights, TOPSIS, CRITIC, thresholds, or daily/entity classification.

Suggested sections:

- 风险评价单元与硬约束
- 缺失目标的插补方法, if needed for a continuous evaluation sequence
- 日级或对象级指标体系
- 客观赋权方法
- 综合得分
- 混合判别规则
- 汇总输出流程

Formula ingredients:

- Indicator definitions.
- Exceedance magnitude and duration.
- Entropy weight normalization, entropy, redundancy, and weights.
- Composite score.
- Serial classification rules from high risk to safe.

## Tables That Belong In Methodology

Include tables for:

- Symbols and meanings.
- Input variables and roles.
- Candidate models and structural differences.
- Indicator definitions.
- Classification rules.
- Algorithm steps, if the code is complex.

Avoid tables that contain:

- Actual performance metrics.
- Final predictions.
- Final category counts.
- Result-ranked model lists with numerical outcomes.
