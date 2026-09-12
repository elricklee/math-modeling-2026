# Solution Boundary

Use this reference to keep the solution chapter accurate and distinct from methodology.

## Allowed In 模型的求解

Numerical outputs from final files:

- RMSE, MAE, R2, AIC, BIC, accuracy, cross-validation scores.
- Fitted parameters and confidence intervals.
- Feature importance, entropy weights, composite scores.
- Prediction values, daily summaries, target-date tables.
- Risk counts, percentages, and detailed classifications.
- Sensitivity response values.

Result interpretation:

- Why one model was selected according to the stated criterion.
- What a figure shows.
- Which variables or indicators dominate the result.
- Whether a prediction is below/above a standard.
- Why a counterintuitive sign may appear in observational data.

## Not Allowed

Do not:

- Invent a missing value because it "should" be present.
- Edit result logic in prose after the user says the code/results are final.
- Hide poor metrics or unstable results.
- Re-run a different method unless the user asks for code modification.
- Treat feature importance or sensitivity as causal proof without qualification.
- Repeat long formulas already explained in "模型的建立"; cite them briefly instead.

## If Results Are Weak

Write them honestly:

- Prefer absolute errors when R2 is unstable due to low variance.
- Explain why the metric is weak or negative.
- Compare to baseline if available.
- State residual risk or limitation in restrained terms.

Example:

"2026-03后验段的 $R^2$ 为负，主要与该段目标方差较小有关。因此本文不把该值作为模型优劣的主要依据，而以 RMSE 和 MAE 评价绝对误差。"

## If The User Asked Not To Mention A Metric

Respect it. Do not include the metric in tables or prose. If needed, explain selection using allowed metrics.

## If Methodology And Results Differ

If the final "模型的建立" chapter says one model family but output files reflect another:

- Prefer the final code and final outputs for the solution chapter.
- Briefly align wording with the methodology if possible.
- Ask the user only if the mismatch changes the answer or would make the chapter internally inconsistent.

## Result Tables

When moving Excel data into Markdown:

- Keep the same units and date口径.
- Do not paste huge sheets. Distill them.
- Include all rows required by the problem statement.
- Use rounded values but preserve enough precision.
- Avoid "Unnamed" columns from Excel indexes; clean headers for publication.
