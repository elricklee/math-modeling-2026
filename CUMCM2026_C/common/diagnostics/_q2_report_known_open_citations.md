# 验收报告的已知未修引用瑕疵（登记件）

> **为什么有这个文件**：`Q2_最终验收报告.md` 已被冻结（并由第三方在其冻结结论中引用过其 digest）。
> 为**不改动冻结件**而又不让这些已知项只存在于消息里，把登记与"一次落盘即可修完"的载荷放在这里。
> **本文件不修改任何交付物**；若队长裁定"修报告"（方案 A），照本文件载荷一次落盘即可。
>
> **登记人**：建模手　**登记时点**：2026-09-12 06:5x

---

## 一、被登记对象（冻结件五元组）

| 文件 | 行数 | 字节数 | mtime | sha256_16 |
|---|---|---|---|---|
| `CUMCM2026_C/Q2/Q2_最终验收报告.md` | 668（splitlines） | 56 536 | 2026-09-12 06:00:20 | `161a2aba87fa8c39` |

计数口径：行数 = `len(text.splitlines())`；字节数 = `len(path.read_bytes())`。

## 二、待修 6 处（目标已逐项预验证可解析）

| # | 位置 | 现写 | 应写 | 依据（实测） |
|---|---|---|---|---|
| 1 | 卷首版本块 + §5.6 | `result2.xlsx 05:32:25` / `diagnostics 05:32:36` / `analysis 05:52:20` / `analysis.py 05:46:10` | `06:19:24` / `06:19:34` / `06:35:15` / `06:32:47`（并附 digest） | 四份产物在停机后重跑；digest：`17687e2e31520217`（result2.xlsx）/ `d86c4474931dd5d9` / `26da65503431edb0` |
| 2 | §三、§5.4 的 48/48 出处 | `_q2_audit_thirdparty.json`（未带生成时刻/该轮基准落后） | `…@06:41:06` | 该轮 `generated_at = 2026-09-12T06:41:06`、48/48、fatal 0，覆盖 `result2.xlsx @06:19:24` |
| 3 | §1.4 出处（L93） | `Q2_analysis.json → variants[*].summary` | `variants[<口径>].summary` | `variants` 实为 **dict（6 键）**，每键下才有 `summary`（17 子键，含 `emergency_purchase_kwh`） |
| 4 | §5.0 表（L307 / L308） | `_q2_u4_multiple_optima.json → experiment_1` / `→ experiment_2` | `→ experiment_1_execution_convention` / `→ experiment_2_multiple_optima_scan` | 该文件顶层键恰为这三个：`experiment_1_execution_convention`、`experiment_2_multiple_optima_scan`、`daily_summary` |
| 5 | §5.7.2（L410 一带） | C1 `severity low` | C1 `severity info（原 low）` | 现行 `_q2_paper_audit.json → advisory_findings → C1`：`severity = info`、`resolution = accepted_no_change`、`blocking = false`；`captain_ruling` 记"由 low 下调为 info 系队长第十批裁定（纪录：info，原 low）" |
| 6 | §二（L138） | `conclusions[7]`（4.46 / 0.6148） | `conclusions[8]` | `conclusions` 共 9 条（0-based）：`[7]` 是"紧急购电量的决定因素是**预报误差**"，`[8]` 才是"5 倍电价的真实作用…4.46 元/kWh…0.6148" |

**第 6 条是本清单里唯一"引错条目"**（其余 5 条为口径/版本/键名不精确）：数值本身正确，但读者按 `[7]` 会落到另一条结论上。

## 三、机器证据（第三方工具，可复跑）

`CUMCM2026_C/Q2/Q2_field_path_check.py`（**v2.6**，`TOOL_VERSION = "2.6"`；诊断件 `_q2_field_path_check.json` 内 `frozen: true`）：
- `verdict = fail`；**非 OK 引用位点 6 处 = 文档 5 + 索引语义 1**；
- 文档档：`hits 27 / ok 22 / tolerated 3 / unresolved 2`，非 OK 项带行号与原文；
- 语义断言 2 次（均为 L138 的 `4.46` 与 `0.6148`）；E2 另有 3 条 advisory（不计入 verdict）；
- 覆盖 7 个产物。

## 四、若裁定方案 A：修复方式

1. 按第二节六行**逐条定点替换**（不改任何数值、不重排章节）；
2. 落盘后**重新取被登记对象的五元组**（行数/字节数/mtime/sha256_16），旧值 `161a2aba87fa8c39` 即作废；
3. 请编程手复跑 `Q2_field_path_check.py`（v2.6），**原样列出全部剩余项**（不预设 pass）；
4. 本文件追加一行"已按 A 修完 + 新五元组"，保留旧值备查。

## 五、附：等长改写已实证三例（升格"五元组"的依据）

| 实例 | 文件 | 行数/字节数 | digest 变化 | 性质 |
|---|---|---|---|---|
| 一 | `Q2_field_path_check.json` | 776 / 26 191 | `8b8abb27…` → `caa8b23f…` | 定宽 `generated_at` 秒级变化 |
| 二 | 同上 | 776 / 26 191 | `caa8b23f…` → `399e8e27…` | 同上 |
| 三 | 同上 | **777 / 26 214** | `8c54ae9c…` → `3da6f724…` | **同长，且已按协议另立版本号 v2.6**（脚本内注释留痕） |

**风险面**（重跑即等长改写的产物）：`_q2_audit_thirdparty.json`（`.generated_at` 19 字符）、`_q2_field_path_check.json`（同）、
`Q2_diagnostics.json`（`solver.elapsed_seconds` 等可变浮点，33.23→33.33 已实证）、`Q2_analysis.json`（六口径各带 `elapsed_seconds`）。
⇒ **结论**：现规则"四快照（行数/字节数/表号集合/占位符数）"不足以辨认版本，建议升格为**五元组：行数 / 字节数 / mtime / sha256_16**（章节另加表号集合、占位符数）；
并且**产物内写明 version 字段**能让"等长改写"变得**可归因**（实例三即为此种：虽然等长，但版本号已从 v2.5 变为 v2.6 并留痕）。

---

## 六、终局基线（各方定格，建模手 2026-09-12 06:58 复算）

**稳定件（待复核件与交付物，六项全部 MATCH）**

| 文件 | 行数 | 字节数 | mtime | sha256_16 |
|---|---|---|---|---|
| `Q2_field_path_check.py`（v2.6，冻结） | 511 | 27 137 | 06:56:23 | `631170830c4ad655` |
| `_q2_field_path_check.json`（`frozen: true`） | 777 | 26 214 | 06:56:26 | `3da6f7249e8a7a15` |
| `_q2_paper_audit.json` | 271 | 22 527 | 06:50:13 | `5a7f4b5b4321d463` |
| `问题二模型的求解.md` | 460 | 52 312 | 05:52:54 | `8fbaf0b6f6ff7b12` |
| `问题二模型的建立.md` | 350 | 34 528 | 04:18:32 | `c4ddbf165b73a843` |
| `Q2_最终验收报告.md`（本登记件所登记的对象） | 668 | 56 536 | 06:00:20 | `161a2aba87fa8c39` |

**不作锚的件**：`_q2_paper_audit.md` 是**增长型记录**（结论按条追加，实测 06:56:29 → 06:57:02 → 06:57:51 连续三版）。
**结论：增长型记录不对外报指纹**——"追加 → 取数 → 发消息"之间存在必然漂移窗口，**报它的指纹是结构性错误，不是失误**；需要引用时写"该记录 §X（引用时刻）"或当场现取。

**待决**：本文件第二节 6 处是否修（方案 A / B），等队长一字。在裁定之前，上述稳定件**均不再改动**。

