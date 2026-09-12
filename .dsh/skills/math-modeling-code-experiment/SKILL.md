---
name: math-modeling-code-experiment
description: 【数模国赛】个性化代码编写skill。Write runnable experiment code for mathematical modeling contest subproblems. Use when the user asks DeepSeek to solve one contest question/subquestion with Python, MATLAB, R, or similar code; generate modeling experiments from a brief description such as "do question 2 with LSTM", "use entropy weight method for this part", or "I have no idea, design the method"; read problem statements, attachments, prior cleaned data, existing Q folders, and produce executable scripts with Excel/CSV result tables, figures, diagnostic logs, and leakage/validity checks.
---

# Math Modeling Code Experiment

## Purpose

Build the experiment-code part of a mathematical modeling contest answer. The output should be code the user can run, plus result files that later support "模型的建立" and "模型的求解" writing.

The skill must be flexible: if the user names a method, implement it unless it is clearly inconsistent with the data or problem; if the user gives no method, design a defensible method family and explain the choice briefly before coding.

## Required Inputs

Use whatever the user provides, then inspect local context to fill gaps:

- Target question or subquestion, such as "问题 2" or "第二问的预测".
- Any method preference, model preference, data scope, target dates, output folder, or constraints.
- Problem statement, attachments, previous preprocessing files, existing code, and result folders in the workspace.

Ask a concise question only if the target question cannot be inferred or if multiple incompatible interpretations would lead to different code.

## Reading the Problem PDF & Attachments (dsh-files)

The `dsh-files` plugin exposes a `read_document` tool that reads PDF, DOCX, XLSX, and plain text by byte-sniffed format — it never trusts the extension. Use it for the contest PDF (赛题) and every attachment (附件) that is PDF/DOCX/XLSX. Use the plain `read` tool only for plain-text or code files.

- **PDF (赛题 or attachment)**: probe the structure first with a small first window (e.g. `limit: 100`), then page with `offset`/`limit`. Read only the sections the subproblem needs, then stop — do not dump the whole PDF into context.
- **Scanned PDF (no text layer)**: `read_document` returns an explicit notice like "[此 PDF 没有文本层…]" instead of an empty string. Do not treat it as empty and do not report the document as blank. **This environment has no OCR skill and no OCR engine** (no `tesseract`, no `pytesseract`/`easyocr`/`paddleocr`/`rapidocr`), so OCR cannot be performed — stop and tell the user the PDF has no text layer, and offer to add an OCR engine. Note that `pymupdf`/`pypdf`/`pdfplumber` also read a text layer only and cannot recover text from scans.
- **XLSX attachments**: call `read_document` with `list_sheets: true` first to list the numbered sheet names, then read the sheet you need with `sheet: <n>` (1-based). A `sheet` read returns that whole worksheet (no 200-row cap), so it is the reliable way to read a large data sheet; the tool window then paginates it with `offset`/`limit`. The default merged read caps each sheet at ~200 rows and the first ~5 sheets, so do not rely on it for large data. An out-of-range sheet index returns the valid sheet list.
- **Pagination**: every result carries a header `### document <path> (format) — offset X, N/totalLines lines`. When the document is longer than the window, continue with `offset = X + N` until you have what you need.
- **Format**: leave `format` as `auto`; byte sniffing overrides a wrong extension.

## Workflow

1. Read the problem statement and relevant attachments using `read_document` (see the section above). Identify the exact deliverables: predicted dates/times, required metrics, tables, figures, risk levels, sensitivity analysis, or parameter estimates.
2. Inspect existing preprocessing and prior question folders before writing new code. Prefer established cleaned datasets and naming conventions over re-reading raw data when a trusted cleaned table exists.
3. Decide the modeling route:
   - If the user supplied a method, use it as the main route. Add a simple baseline when it helps validate the method.
   - If no method was supplied, choose a contest-appropriate route balancing accuracy, interpretability, implementation risk, and paper-writing value.
   - If the supplied method is risky, still implement it when feasible, but include a safer baseline and a diagnostic note in the output log.
4. Draft a compact implementation plan naming input files, target variable, split rule, candidate models, validation metrics, prediction targets, and output files.
5. Write one self-contained script in the requested question folder, such as `Q2/Q2_1.py`. Keep paths relative to the script location and robust to Chinese filenames.
6. The script must create result tables, figures, and a diagnostic log. Use Excel workbooks for main contest answers and PNG/PDF figures for paper use.
7. Run static checks or a lightweight execution check when feasible. If runtime is heavy, at least run syntax checks and inspect the generated code for missing imports, path mistakes, and output declarations.
8. Report what was created, how to run it, and what outputs should be inspected after the user runs it.

## Method Design Rules

Always align model complexity with the question:

- Factor screening or relationship fitting: start with statistical tests, explicit formulas, parameter fitting, and direction/strength summaries. Use machine learning only as supporting evidence unless the question asks for predictive accuracy above interpretability.
- Time-lag dynamics: include lag discovery such as CCF, mutual information, cross-validation over lags, distributed-lag regression, ARDL, or sequence models. Avoid using future target values.
- Multi-step forecasting: define lookback, horizon, direct vs recursive prediction, seed values, and how target history is updated in prediction mode.
- Mechanism-data hybrid modeling: write the physical baseline explicitly, estimate interpretable parameters under engineering bounds, then add residual learning or PINN-style constraints.
- Risk evaluation or ranking: construct daily/region/entity-level indicators first, then scoring/weighting/classification rules. Keep hard standards as explicit hard constraints rather than hiding them inside weights.
- If using deep learning, include a simple statistical or linear baseline and keep seeds, scaling, train/validation splits, and device handling explicit.

For more detailed method-selection patterns, read `references/method-patterns.md`.

## Code Output Contract

Generated scripts must:

- Preserve original data and write outputs into the target question folder.
- Use deterministic seeds for stochastic models.
- Parse dates and grouped records deliberately; do not trust spreadsheet date columns blindly when filenames, sheet names, or row order define the actual time axis.
- Keep raw target columns when the target is missing in the prediction period. Never fill a contest prediction target and then treat it as truth.
- Separate train, validation, posterior/check, and target-prediction periods by time or contest-defined group.
- Produce at least one result workbook and enough figures to support later paper writing.
- Include a diagnostics sheet or log covering sample counts, missingness, splits, selected features/models, metric definitions, prediction target coverage, and known limitations.
- Include leakage checks: target availability, future-feature use, fit-on-train-only transforms, closed-loop handling of autoregressive channels, and correct date口径.

For the full checklist, read `references/output-and-leakage-checklist.md` before finalizing a script.

## Contest Code Style

Prefer a single readable script per question unless the user asks for a package. Organize it by stages:

```text
STAGE A  Load and validate data
STAGE B  Feature/indicator/sample construction
STAGE C  Model fitting and validation
STAGE D  Required prediction/classification/optimization
STAGE E  Export Excel, figures, diagnostics
```

If a generated Python script uses matplotlib, import and configure it exactly in this order:

```python
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
```

Do not use another backend such as `Agg` unless the user explicitly overrides this requirement for a headless environment.

Use Chinese labels in figures and Excel sheets when the contest paper is Chinese. Put formulas, model names, parameter meanings, and metric definitions into method sheets so the later writing skills can quote them without reverse-engineering code.

## Final Response

After creating or updating code, answer with:

- Script path and how to run it.
- Main method and why it matches the question.
- Output files expected.
- Validation or syntax checks performed.
- Any limitations the user should inspect after running.

Do not write the paper chapter in this skill. Stop at experiment code and result artifacts.
