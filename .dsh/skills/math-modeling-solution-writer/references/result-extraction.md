# Result Extraction

Use this reference before writing a "模型的求解" chapter.

## Extraction Order

1. Read the final methodology chapter to learn symbols, model names, and promised outputs.
2. Read the final code to understand sheet names, figure names, and how outputs were computed.
3. Load final Excel/CSV outputs and inspect all sheet names.
4. Open figures when files are present. If images are embedded in a DOCX or absent, use their captions plus corresponding result tables.
5. Extract only values that will support the paper's claims.

## What To Extract From Workbooks

For model comparison:

- Model names and IDs.
- Selection criterion.
- Main metrics, such as RMSE, MAE, MAPE, R2, AIC, BIC, accuracy.
- Train/validation/test/posterior split names and sample counts.
- The selected model and why it is selected.

For parameter estimation:

- Parameter names and meanings.
- Estimates, confidence intervals, direction, significance, or boundary status.
- Engineering-domain checks.

For prediction:

- Required dates/times or entities.
- Point-level predictions.
- Aggregated daily/monthly summaries.
- Whether target truth exists or is missing.
- Any clipping or physical-bound correction.

For classification/risk evaluation:

- Detailed classification table required by the problem.
- Level counts and percentages.
- Thresholds and triggered rule branches.
- High-risk or special cases worth describing.

For sensitivity analysis:

- Perturbation variables.
- Perturbation levels.
- Response metrics by horizon/date/entity.
- Direction, magnitude, and stability of response.

## Tables To Include In The Chapter

Include small, high-signal tables rather than entire workbooks:

- Top factors or key variables.
- Candidate model performance table.
- Selected model parameter table.
- Required prediction summary table.
- Required detailed answer table.
- Risk level proportion table.
- Sensitivity summary table.

Round consistently. Keep enough precision for contest credibility:

- Metrics: usually 3 or 4 decimals.
- Percentages: usually 2 decimals.
- Prediction values: use the same precision as the problem context, often 3 decimals for NTU.

## Figure Description

For every final figure, write 1-3 sentences:

- What is shown.
- What pattern is visible.
- What conclusion it supports.

Do not over-read decorative details. If a figure contradicts a table, flag the issue instead of forcing consistency.

## Missing Or Modified Outputs

If the user says some outputs were manually modified, trust the specified final files. If only code exists but result files are absent, say the chapter cannot contain verified numerical results unless the code is run or outputs are provided.
