# Output And Leakage Checklist

Read this before finalizing any experiment script.

## Mandatory Output Files

A question script should normally create:

- One main `.py` script in the target question folder.
- One or more `.xlsx` workbooks with contest answers and method diagnostics.
- Paper-ready figures with Chinese titles/labels when the paper is Chinese.
- A text log or Excel "方法说明/诊断" sheet containing sample counts, split rules, model choices, metrics, and warnings.

Use stable sheet names such as:

- `性能排名`
- `模型参数`
- `预测结果`
- `日均汇总`
- `变量时滞`
- `敏感性分析`
- `方法说明`
- `诊断日志`

## Required Diagnostics

Include the following counts or checks when relevant:

- Raw rows, usable rows, rows removed or skipped, and reason.
- Missing count for target and key input variables.
- Train/validation/posterior/target sample counts.
- Date range of every split.
- Required target-date coverage: expected rows vs actual rows.
- Feature list used by each model.
- Metric definitions, including RMSE/MAE/R2/MAPE only when meaningful.
- Best model selection criterion.
- Any clipped negative predictions or boundary-hit parameters.
- Runtime device for deep learning and seed values.

## Leakage Checks

Before finalizing, verify:

- The target prediction period is not used as labeled training data.
- Interpolation or imputation does not fill the target variable for contest prediction before modeling.
- Scalers, imputers, feature selectors, PCA, and model selection are fitted on training data only.
- Lag features use only current/past observations relative to the prediction timestamp.
- Rolling statistics are shifted when they summarize target history.
- Autoregressive channels use true lagged values during training and closed-loop predicted values during prediction when the true future target is unavailable.
- Cross-validation does not mix future and past rows for time series unless explicitly used only for an imputation model or non-temporal diagnostic.
- Posterior observed periods are labeled as robustness checks, not as ordinary validation if they occur after the target month.
- Natural date and operation date are not mixed in required outputs.

## Spreadsheet And Figure Checks

Excel outputs should:

- Use clear Chinese sheet names.
- Include the exact answer table requested by the problem statement.
- Include both point-level and aggregated results when the problem asks for days and times.
- Use explicit units in column names when useful.
- Avoid hiding assumptions in code only; add a method/rule sheet.

Figures should:

- Be readable as standalone paper figures.
- Use Chinese labels, legends, and titles for Chinese papers.
- Avoid subplot-heavy figures when the user asks for separate figures.
- Use stable axes and avoid connecting across missing time gaps.
- Show hard thresholds such as standards or risk limits when central to interpretation.
- If the script uses matplotlib, verify the import block is exactly:

```python
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
```

## Failure Handling

If the requested method fails or performs poorly:

- Do not fabricate good results.
- Keep the failed model diagnostics.
- Add a simpler baseline and compare.
- Explain in the final response what should be inspected or changed.
- If a metric is misleading because variance is tiny or the target distribution shifts, report absolute-error metrics and avoid over-interpreting R2.

## Final Script Review

Before reporting completion, run at least:

```powershell
python -m py_compile path\to\script.py
```

If runtime is acceptable, run the script once and inspect output files. If not, state that only syntax/static checks were performed.
