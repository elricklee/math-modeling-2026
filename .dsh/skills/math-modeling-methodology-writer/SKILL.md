---
name: math-modeling-methodology-writer
description: 【数模国赛】个性化模型建立撰写skill。Write methodology-only "模型的建立" chapters for mathematical modeling contest subproblems from the user's final adopted code, problem statement, variables, and selected artifacts. Use after experiment code has been generated or revised, when the user asks to write 问题一/二/三/四模型的建立, 模型建立, 建模方法章节, or a method-only paper section; do not report numerical results, rankings, prediction values, or run conclusions that belong in "模型的求解".
---

# Math Modeling Methodology Writer

## Purpose

Write the "模型的建立" chapter for one mathematical modeling subproblem. The chapter must explain the method, variables, formulas, assumptions, and algorithm flow based on the final code the user actually adopted.

This skill is normally used after `math-modeling-code-experiment`. The user may specify final code and selected result figures/tables because they may have manually modified the experiment outputs. Treat the user-specified code as authoritative.

## Inputs To Inspect

Use the user's latest message to identify:

- The target subproblem and chapter name.
- The final adopted code file(s), not merely the first generated script.
- Selected figures, Excel files, logs, or result folders the user says are final.
- Any requested output path, Markdown/DOCX preference, section numbering, or style constraints.

Then read the problem statement (usually the contest PDF) with `read_document` and the final code with the plain `read` tool. Read result files only to understand available artifacts, variable names, figure titles, and workflow consistency. Do not extract numerical findings into the methodology chapter unless the number is a fixed design constant or hyperparameter, such as a threshold, lookback length, model horizon, number of folds, or national standard.

## Reading the Problem PDF & Attachments (dsh-files)

The `dsh-files` plugin exposes a `read_document` tool that reads PDF, DOCX, XLSX, and plain text by byte-sniffed format — it never trusts the extension. Use it for the contest PDF (赛题) and every attachment (附件) that is PDF/DOCX/XLSX. Use the plain `read` tool only for plain-text or code files.

- **PDF (赛题 or attachment)**: probe the structure first with a small first window (e.g. `limit: 100`), then page with `offset`/`limit`. Read only the sections the subproblem needs, then stop — do not dump the whole PDF into context.
- **Scanned PDF (no text layer)**: `read_document` returns an explicit notice like "[此 PDF 没有文本层…]" instead of an empty string. Do not treat it as empty and do not report the document as blank. **This environment has no OCR skill and no OCR engine** (no `tesseract`, no `pytesseract`/`easyocr`/`paddleocr`/`rapidocr`), so OCR cannot be performed — stop and tell the user the PDF has no text layer, and offer to add an OCR engine. Note that `pymupdf`/`pypdf`/`pdfplumber` also read a text layer only and cannot recover text from scans.
- **XLSX attachments**: call `read_document` with `list_sheets: true` first to list the numbered sheet names, then read the sheet you need with `sheet: <n>` (1-based). A `sheet` read returns that whole worksheet (no 200-row cap), so it is the reliable way to read a large data sheet; the tool window then paginates it with `offset`/`limit`. The default merged read caps each sheet at ~200 rows and the first ~5 sheets, so do not rely on it for large data. An out-of-range sheet index returns the valid sheet list.
- **Pagination**: every result carries a header `### document <path> (format) — offset X, N/totalLines lines`. When the document is longer than the window, continue with `offset = X + N` until you have what you need.
- **Format**: leave `format` as `auto`; byte sniffing overrides a wrong extension.

## Hard Boundary

The "模型的建立" chapter must not contain:

- Model performance values such as RMSE, MAE, R2, accuracy, AIC, or ranking results.
- Final predicted values, class counts, risk proportions, or sensitivity response values.
- Statements such as "results show", "the best model is", or "prediction indicates".
- Figure-by-figure result interpretation.

It may contain:

- Task definition and why the method fits the task.
- Variable definitions and symbol tables.
- Mathematical formulas and loss functions.
- Feature construction, sample construction, split principles, constraints, and training protocol.
- Candidate model families and model-selection criteria, stated without reporting the selected numerical outcome.
- Output artifact descriptions in methodological terms, such as "the script exports a prediction table", without giving the prediction values.

For detailed boundary examples, read `references/result-boundary.md`.

## Required Writing Pipeline

Draft through `nature-writing` first, then revise through `humanizer-zh`.

When composing the chapter:

1. Use `nature-writing` as the drafting layer. Treat the chapter as a Chinese academic methods/methodology section: clarify the one-sentence argument, arrange the evidence chain, choose section structure, and write connected method prose from the final code.
2. Then apply `humanizer-zh` as the editing layer. Remove AI-like traces, mechanical transitions, overclaiming, empty praise, and list-like rhythm while preserving formulas, variable names, technical facts, and the method/result boundary.
3. The final Markdown should reflect the `humanizer-zh` revision, not the raw first draft.

## Workflow

1. Read the user-specified final code carefully. If multiple scripts exist, prefer the one the user explicitly names; otherwise inspect the target folder and use the newest or main script.
2. Extract method stages from code: data source, target variable, input variables, feature engineering, model family, parameter estimation, validation design, prediction/classification target, exported artifacts.
3. Map code variables to contest terms. Preserve original variable names such as `FILT. NTU`, `R/W NTU`, `ALUM`, and provide Chinese meanings when useful.
4. Reconstruct formulas from code and problem logic. Use strict LaTeX syntax for all equations.
5. Build a coherent chapter outline. Use paragraphs rather than bullet lists; tables are allowed when they clarify symbols, variables, model components, or algorithm steps.
6. Draft the chapter using the `nature-writing` approach: build the argument line first, then write the methods section around variables, formulas, model flow, and assumptions.
7. Apply `humanizer-zh` editing: remove empty praise, overclaiming, repeated transitions, and AI-like template language while preserving technical content.
8. Save the Markdown file if the user requests a path or if there is an obvious target folder. Otherwise provide Markdown in the response and offer the path used if saved.

## Chapter Shape

A typical chapter should include:

- Task positioning and modeling idea.
- Symbols and variables.
- Data/sample construction or indicator construction.
- Core model formulas.
- Parameter estimation or training objective.
- Candidate model comparison/design, if used.
- Prediction/classification/optimization procedure, method-only.
- Method summary linking the stages.

For more detailed structure patterns, read `references/chapter-structure.md`.

## Writing Requirements

Follow these defaults unless the user says otherwise:

- Write in Markdown.
- Use strict LaTeX formulas with `$...$` or `$$...$$`.
- Prefer natural paragraphs; avoid excessive bullets and numbered lists.
- Include detailed formulas and text-form table descriptions.
- Do not use code-stage labels such as "STAGE A" in final prose unless the user explicitly wants them. Replace them with section names like "时滞先验估计" or "日级指标构造".
- Use concise section headings, matching the paper's numbering style when visible.
- Keep method and result separated. Result interpretation belongs to the later `math-modeling-solution-writer` skill.

## Final Response

After writing, report:

- The saved Markdown path, if saved.
- Which final code file(s) were used.
- That `nature-writing` drafting and `humanizer-zh` revision were applied.
- That the chapter is methodology-only and excludes results.
- Any missing information or assumptions that may affect the next "模型的求解" chapter.
