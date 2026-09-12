# Result Boundary

Use this reference to keep "模型的建立" separate from "模型的求解".

## Allowed In 模型的建立

Design constants:

- Sampling interval, lookback length, forecast horizon.
- Thresholds required by the problem, such as national standards.
- Hyperparameters fixed before training, such as number of folds, maximum lag, optimizer type, or model candidates.
- Engineering bounds imposed on parameters.

Method descriptions:

- "The model compares several candidate functions using RMSE and MAE."
- "The validation period is used to choose the working model."
- "The final script exports point-level predictions and daily summaries."
- "A random forest is trained to impute missing target values before daily risk scoring."

Code-derived structures:

- Input variable lists.
- Feature definitions.
- Formula families.
- Loss functions.
- Classification rule conditions.
- Model architecture components.

## Not Allowed In 模型的建立

Numerical results:

- Actual RMSE, MAE, R2, AIC, accuracy, feature importance, entropy weights.
- Actual parameter estimates unless the user explicitly wants a combined establishment-and-solution chapter.
- Actual predicted values for target dates.
- Actual risk proportions or category counts.
- Statements naming the empirically best model from output rankings.

Interpretive result claims:

- "The results show..."
- "The best model is..."
- "The prediction is lower/higher than..."
- "The risk level of March 12 is..."
- "Feature X contributes 31.2%..."

Figure/table interpretation:

- Do not describe each generated figure's observed pattern.
- Do not quote output-table rows.
- Do not interpret residual scatter, final curves, or heatmap colors.

## How To Rephrase

Instead of:

"M3 has the lowest RMSE of 0.5239, so M3 is selected."

Write:

"The candidate functions are evaluated by RMSE and MAE on the designated validation data, and the function with the smallest absolute error is used for the target-period prediction."

Instead of:

"The entropy weight of EXC_RATIO is 0.3198."

Write:

"Indicators with lower entropy receive larger weights, so indicators that vary more across days have greater influence on the comprehensive risk score."

Instead of:

"The model predicts 2026-02-10 has the highest NTU."

Write:

"After the model is fitted, the three required operation days are passed through the same prediction function to obtain point-level and daily-summary tables."

## If The User Provides Figures

Use figures in this skill only to identify:

- What stage the code exports.
- Whether there are expected figure references in the paper.
- Which variables or model components are represented.

Save figure interpretation for the solution-writing skill.

## If Final Code And Result Files Disagree

Ask the user which source is authoritative only if the disagreement affects the methodology. Otherwise follow the final code for method descriptions and leave numerical result reconciliation for the solution chapter.
