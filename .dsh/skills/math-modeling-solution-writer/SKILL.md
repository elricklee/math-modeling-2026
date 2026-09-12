---
name: math-modeling-solution-writer
description: 【数模国赛】个性化模型求解撰写skill。Write result-focused "模型的求解" chapters for mathematical modeling contest subproblems from the user's final adopted code, final "模型的建立" chapter, selected Excel/CSV outputs, figures, and logs. Use after math-modeling-methodology-writer when the user asks to write 问题一/二/三/四模型的求解, 求解章节, 结果分析章节, or a paper-ready solution section; extract key metrics, tables, predictions, classifications, and figure interpretations, while keeping terminology consistent with the established methodology chapter.
---

# Math Modeling Solution Writer

## Purpose

Write the "模型的求解" chapter for one mathematical modeling contest subproblem. This chapter turns final experiment outputs into paper-ready result analysis: model comparison, parameter estimates, predictions, classifications, sensitivity results, and figure/table descriptions.

This skill is normally used after `math-modeling-methodology-writer`. The final "模型的建立" chapter is an input, not something to rewrite. Use it to preserve symbols, method names, section logic, and wording continuity.

## Inputs To Inspect

Use the user's latest message to identify:

- Target subproblem and chapter title.
- Final adopted code file(s).
- Final "模型的建立" Markdown/DOCX section, if provided or obvious in the question folder.
- Selected result figures, Excel/CSV workbooks, logs, or folders the user says are final.
- Output format and save path.

If the user names final artifacts, treat them as authoritative because they may have manually modified outputs after the experiment-code skill. If several result files conflict, prefer the user-specified final files; ask only when the conflict changes the answer.

## What To Read

Always read:

- Final code, to understand what each output means.
- Final methodology chapter, to keep terminology and formulas consistent.
- Result workbooks and logs, to extract numerical evidence.
- Figure files when available; if embedded in a DOCX or missing locally, use figure captions and corresponding result tables.
- The figure filenames and relative paths in the corresponding question folder, such as `Q1/outputs/fig1_xxx.png`, so the chapter can include insertion markers.

For detailed extraction guidance, read `references/result-extraction.md`.

## Reading the Problem PDF & Attachments (dsh-files)

The `dsh-files` plugin exposes a `read_document` tool that reads PDF, DOCX, XLSX, and plain text by byte-sniffed format — it never trusts the extension. Use it for the contest PDF (赛题) and every attachment (附件) that is PDF/DOCX/XLSX. Use the plain `read` tool only for plain-text or code files.

- **PDF (赛题 or attachment)**: probe the structure first with a small first window (e.g. `limit: 100`), then page with `offset`/`limit`. Read only the sections the subproblem needs, then stop — do not dump the whole PDF into context.
- **Scanned PDF (no text layer)**: `read_document` returns an explicit notice like "[此 PDF 没有文本层…]" instead of an empty string. Do not treat it as empty and do not report the document as blank. **This environment has no OCR skill and no OCR engine** (no `tesseract`, no `pytesseract`/`easyocr`/`paddleocr`/`rapidocr`), so OCR cannot be performed — stop and tell the user the PDF has no text layer, and offer to add an OCR engine. Note that `pymupdf`/`pypdf`/`pdfplumber` also read a text layer only and cannot recover text from scans.
- **XLSX result workbooks & attachments**: call `read_document` with `list_sheets: true` first to list the numbered sheet names, then read the sheet you need with `sheet: <n>` (1-based). A `sheet` read returns that whole worksheet (no 200-row cap), so it is the reliable way to read a large result/data sheet; the tool window then paginates it with `offset`/`limit`. The default merged read caps each sheet at ~200 rows and the first ~5 sheets, so do not rely on it for large data. An out-of-range sheet index returns the valid sheet list.
- **Pagination**: every result carries a header `### document <path> (format) — offset X, N/totalLines lines`. When the document is longer than the window, continue with `offset = X + N` until you have what you need.
- **Format**: leave `format` as `auto`; byte sniffing overrides a wrong extension.

## Boundary With 模型的建立

Do not redo the derivation in full. Briefly remind the reader of the method only when needed to make a result understandable.

The solution chapter should include:

- Actual metrics, fitted parameters, model rankings, selected-model justification, prediction values, classification counts, or sensitivity responses.
- Tables distilled from final Excel sheets.
- Concise interpretation of every final figure the user expects in the paper.
- Statements that directly answer the subproblem requirements.
- Cautious explanation of weak, negative, unstable, or counterintuitive results.

Avoid:

- Long re-derivation of formulas already written in "模型的建立".
- Code-stage names such as `STAGE A`, unless the user explicitly wants them.
- Overclaiming causality from correlation, feature importance, or observational sensitivity.
- Inventing values not present in final outputs.

For more boundary examples, read `references/solution-boundary.md`.

## Required Writing Pipeline

Draft through `nature-writing` first, then revise through `humanizer-zh`.

When composing the chapter:

1. Use `nature-writing` as the drafting layer. Treat the chapter as a Chinese academic results/solution section: identify the result argument, arrange tables and figures into a coherent evidence chain, and connect numerical findings to the subproblem requirements.
2. Then apply `humanizer-zh` as the editing layer. Remove AI-like traces, mechanical transitions, overclaiming, empty praise, and list-like rhythm while preserving exact metrics, table values, figure references, formulas, and limitations.
3. The final Markdown should reflect the `humanizer-zh` revision, not the raw first draft.

## Workflow

1. Read the final methodology chapter first when available. Note section numbering, model names, symbols, and promised outputs.
2. Read the final code and identify output files, sheet names, figure names, metrics, and target-answer tables.
3. Load the final Excel/CSV outputs and extract high-signal tables. Keep exact values from files; round only for prose tables and state units.
4. Inspect or infer figures. For each final figure, write a short description of what it shows and what conclusion it supports. At the exact place where the figure should be inserted, add a red-text marker naming the corresponding image file in the question folder, for example `<span style="color:red">Insert figure here: Q1/outputs/fig1_xxx.png</span>` in Markdown. If also producing DOCX, render this marker as real red text, not only plain text.
5. Build the chapter outline according to the subproblem type:
   - Results of preprocessing or screening.
   - Model/parameter estimation results.
   - Model comparison and selected model.
   - Required target predictions/classifications/optimization results.
   - Figure descriptions and result interpretation.
   - Final answer to the problem.
6. Draft the chapter using the `nature-writing` approach: build a result argument first, then write around metrics, tables, figures, required answers, and limitations.
7. Apply `humanizer-zh` editing: reduce template phrases, avoid exaggerated claims, and keep explanations grounded in the output files.
8. Save the Markdown file in the target question folder if requested or obvious.

For chapter templates by task type, read `references/chapter-structure.md`.

## Result Writing Rules

- Use the exact result口径 from the output files, such as `OPERATION_DATE` vs `NATURAL_DATE`.
- Report absolute-error metrics such as RMSE and MAE when R2 is misleading or the user asked not to mention R2.
- Explain negative or weak metrics honestly; do not hide them by changing the table.
- For model rankings, state the selection criterion before naming the selected model.
- For predictions, include both point-level and aggregated tables when required by the problem.
- For risk/classification, include counts, percentages, and required detailed classifications.
- For sensitivity analysis, separate statistical response from causal interpretation.
- If figures are referenced, describe every figure briefly and connect it to the result table.
- At every intended image insertion point, include a red marker with the exact figure filename/path from the corresponding folder. Prefer relative paths rooted at the question folder, such as `Q2/outputs/fig3_model_diagnostics.png`, to make manual insertion unambiguous.

## Writing Requirements

Follow these defaults unless the user says otherwise:

- Markdown output.
- Strict LaTeX syntax for formulas that remain in the solution chapter.
- Long and detailed enough for a contest paper.
- Coherent paragraphs; avoid excessive bullets.
- Include selected result tables directly in the chapter when useful.
- Briefly describe each figure/table.
- Use red text for image insertion markers. In Markdown, use an HTML span such as `<span style="color:red">Insert figure here: Q1/outputs/fig2_correlation_heatmap.png</span>`. In DOCX outputs, create the same marker as bold red text.
- Match the style of the existing final paper or methodology chapter.
- Save to names such as `问题二模型的求解.md` in the corresponding `Q2` folder when obvious.

## Final Response

After writing, report:

- Saved Markdown path, if saved.
- Final code and result artifacts used.
- That `nature-writing` drafting and `humanizer-zh` revision were applied.
- Key result categories covered, such as metrics, predictions, classification tables, or sensitivity results.
- Any files that were missing or any result ambiguity that remains.

