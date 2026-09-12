r"""U4 独立复现：对照口径绝对量级差异的真实来源（t11 追加任务）。

待检验命题（队长转述）
======================
``Q2_audit.py`` 的独立计划阶段 LP 得全年紧急购电 19,054,624.74 kWh，
而流水线报 1,262,153.80 kWh（约 15.1 倍）；命题称二者差在
**同一模型存在多重最优解、两实现各选一个解**。

本脚本的做法
============
1. 自建计划阶段 LP（§ 口径③「仅光伏不可知、负载已知」），独立重解全部 334 天；
2. 在**同一个计划解**上，分别按两种执行阶段口径结算紧急购电量：

   * 口径 A（审计写法）：``need = load + x − y``；``e = max(need − q, 0)``
     —— 执行阶段**没有扣除实际光伏**；
   * 口径 B（契约/流水线写法）：``need = load − pv_act + x − y``；``e = max(need − q, 0)``。

3. 比较两个全年合计与两个被引用的数字，判定命题。
4. 另在参考日做**多重最优扫描**：换用不同求解方法 + 对目标系数加微小随机扰动，
   统计该日紧急购电量的取值范围。

产物：``_q2_u4_multiple_optima.json``（数据）与 ``_q2_u4_multiple_optima.md``（结论）。
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import openpyxl
from scipy.optimize import linprog

DIAG = Path(__file__).resolve().parent
CASE = DIAG.parents[1]
RAW = CASE / "00_problem" / "附件"
OUT_JSON = DIAG / "_q2_u4_multiple_optima.json"
OUT_MD = DIAG / "_q2_u4_multiple_optima.md"

T = 144
DT = 10.0 / 60.0
ETA = 0.90
S_LO, S_HI, S_INIT = 1200.0, 10800.0, 6000.0
CAP = 5000.0 * DT
MULT = 5.0
DAY0, DAY1 = date(2025, 2, 1), date(2025, 12, 31)
DAYS = [DAY0 + timedelta(days=i) for i in range((DAY1 - DAY0).days + 1)]

AUDIT_EMG = 19054624.739063878      # Q2_audit.json -> control_b2ii.independent_emergency_kwh
PIPE_EMG = 1262153.8043316873       # Q2_audit.json -> control_b2ii.json_emergency_kwh


def sheet_rows(path: Path, sheet: str | None = None) -> list[list[object]]:
    """读入整张工作表。"""
    wb = openpyxl.load_workbook(path, data_only=True)
    try:
        ws = wb[sheet] if sheet else wb[wb.sheetnames[0]]
        return [list(r) for r in ws.iter_rows(values_only=True)]
    finally:
        wb.close()


def num(v: object) -> float:
    """单元格 -> float。"""
    try:
        return float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return float("nan")


def as_date(v: object) -> date | None:
    """单元格 -> date（含 Excel 序列号与文本）。"""
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, (int, float)):
        return date(1899, 12, 30) + timedelta(days=int(round(float(v))))
    if v is None:
        return None
    parts = str(v).strip().replace("-", "/").split("/")
    if len(parts) == 3:
        try:
            return date(int(parts[0]), int(parts[1]), int(parts[2]))
        except ValueError:
            return None
    return None


def load_all() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """读入 附件1 电价、附件2 逐日负载/实际光伏（334 天）、附件3 的 0:00 预报。

    Returns:
        ``(price[144], load_e[334,144], pv_act_e[334,144], pv_fc_e[334,144])``，电量单位 kWh。
    """
    p = [r for r in sheet_rows(RAW / "附件1.xlsx")]
    price = np.array([num(r[1]) for r in p if num(r[1]) == num(r[1])])

    def wide(sheet: str) -> tuple[list[date], np.ndarray]:
        """读宽表。"""
        ds, mat = [], []
        for r in sheet_rows(RAW / "附件2.xlsx", sheet):
            d = as_date(r[0]) if r else None
            if d is None:
                continue
            ds.append(d)
            mat.append([num(v) for v in r[1:1 + T]])
        return ds, np.array(mat, dtype=float)

    ds_load, load_kw = wide("小区负载")
    ds_pv, pv_kw = wide("光伏发电实际功率")
    assert ds_load == ds_pv
    idx = {d: i for i, d in enumerate(ds_load)}
    rows = [idx[d] for d in DAYS]
    load_e = load_kw[rows] * DT
    pv_act_e = pv_kw[rows] * DT

    # 附件 3：第 d 日 0:00 发布的那条，按 R-Q2-5（f_d[k] 管 t=6(k-1)+1..6k）
    fc: dict[date, np.ndarray] = {}
    cur: date | None = None
    for r in sheet_rows(RAW / "附件3.xlsx"):
        d = as_date(r[0]) if r else None
        if d is not None:
            cur = d
        if cur is None or len(r) < 26:
            continue
        hour_txt = str(r[1]).split(":")[0].strip()
        if not hour_txt.isdigit() or int(hour_txt) != 0:
            continue
        vals = np.array([num(v) for v in r[2:26]], dtype=float)
        hourly = np.zeros(24)
        for k in range(1, 25):
            hourly[(0 + k - 1) % 24] = vals[k - 1]
        fc[cur] = np.repeat(hourly, 6) * DT
    pv_fc_e = np.array([fc[d] for d in DAYS], dtype=float)
    return price, load_e, pv_act_e, pv_fc_e


def solve_plan(net_f: np.ndarray, pv_f: np.ndarray, price: np.ndarray,
               *, method: str = "highs", jitter: float = 0.0,
               seed: int = 0) -> dict:
    """口径③ 的计划阶段 LP（自建，变量 ``[x|y|q|d]``）。

    ``min Σ c_t q_t`` s.t. ``q − d − x + y = n^f``、日终归位、SOC 上下界、
    ``y − x − d ≤ n^f``（即 q ≥ 0）、``0 ≤ d ≤ V^f``、``0 ≤ x,y ≤ CAP``。
    """
    rng = np.random.default_rng(seed)
    n = 4 * T
    i_x, i_y, i_q, i_d = 0, T, 2 * T, 3 * T
    c = np.zeros(n)
    c[i_q:i_q + T] = price
    if jitter:
        c[i_q:i_q + T] = price * (1.0 + jitter * rng.standard_normal(T))
    a_eq = np.zeros((T + 1, n))
    for t in range(T):
        a_eq[t, i_q + t] = 1.0
        a_eq[t, i_d + t] = -1.0
        a_eq[t, i_x + t] = -1.0
        a_eq[t, i_y + t] = 1.0
    a_eq[T, i_x:i_x + T] = ETA
    a_eq[T, i_y:i_y + T] = -1.0 / ETA
    b_eq = np.concatenate([net_f, [0.0]])

    lower = np.tril(np.ones((T, T)))
    a_ub = np.zeros((4 * T, n))
    b_ub = np.zeros(4 * T)
    rt = np.arange(T)
    a_ub[np.ix_(rt, np.arange(i_y, i_y + T))] = np.eye(T)
    a_ub[np.ix_(rt, np.arange(i_x, i_x + T))] = -np.eye(T)
    a_ub[np.ix_(rt, np.arange(i_d, i_d + T))] = -np.eye(T)
    b_ub[:T] = net_f
    a_ub[np.ix_(rt + T, np.arange(i_x, i_x + T))] = ETA * lower
    a_ub[np.ix_(rt + T, np.arange(i_y, i_y + T))] = -lower / ETA
    b_ub[T:2 * T] = S_HI - S_INIT
    a_ub[np.ix_(rt + 2 * T, np.arange(i_x, i_x + T))] = -ETA * lower
    a_ub[np.ix_(rt + 2 * T, np.arange(i_y, i_y + T))] = lower / ETA
    b_ub[2 * T:3 * T] = S_INIT - S_LO
    a_ub[np.ix_(rt + 3 * T, np.arange(i_d, i_d + T))] = np.eye(T)
    b_ub[3 * T:] = pv_f

    bounds = ([(0.0, CAP)] * T + [(0.0, CAP)] * T + [(0.0, None)] * T
              + [(0.0, None)] * T)
    r = linprog(c, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq,
                bounds=bounds, method=method)
    if not r.success:
        raise RuntimeError(f"计划 LP 失败：{r.message}")
    return {"x": r.x[i_x:i_x + T], "y": r.x[i_y:i_y + T],
            "q": r.x[i_q:i_q + T], "d": r.x[i_d:i_d + T],
            "obj": float(r.fun), "status": str(r.message)}


def main() -> int:
    """执行 U4 复现实验。"""
    price, load_e, pv_act_e, pv_fc_e = load_all()
    n_days = len(DAYS)
    res: dict[str, object] = {}

    e_A = np.zeros(n_days)   # 审计写法：执行阶段不扣实际光伏
    e_B = np.zeros(n_days)   # 契约写法：扣除实际光伏
    q_tot = np.zeros(n_days)
    d_tot = np.zeros(n_days)
    obj_tot = 0.0
    plans: list[dict] = []
    for i in range(n_days):
        net_f = load_e[i] - pv_fc_e[i]           # 口径③：负载已知 + 光伏用 0:00 预报
        sol = solve_plan(net_f, pv_fc_e[i], price)
        plans.append(sol)
        need_wo_pv = load_e[i] + sol["x"] - sol["y"]
        need_w_pv = load_e[i] - pv_act_e[i] + sol["x"] - sol["y"]
        e_A[i] = float(np.maximum(need_wo_pv - sol["q"], 0.0).sum())
        e_B[i] = float(np.maximum(need_w_pv - sol["q"], 0.0).sum())
        q_tot[i] = float(sol["q"].sum())
        d_tot[i] = float(sol["d"].sum())
        obj_tot += sol["obj"]

    res["experiment_1_execution_convention"] = {
        "annual_emergency_kwh_convention_A_no_pv": float(e_A.sum()),
        "annual_emergency_kwh_convention_B_with_pv": float(e_B.sum()),
        "audit_reported_kwh": AUDIT_EMG,
        "pipeline_reported_kwh": PIPE_EMG,
        "gap_A_vs_audit": abs(float(e_A.sum()) - AUDIT_EMG),
        "gap_B_vs_pipeline": abs(float(e_B.sum()) - PIPE_EMG),
        "annual_forecast_pv_kwh": float(pv_fc_e.sum()),
        "annual_actual_pv_kwh": float(pv_act_e.sum()),
    }

    # ---- 实验 2：参考日的多重最优扫描 ----
    ref_idx = int(np.argmax(e_B))
    ref_day = DAYS[ref_idx]
    net_f = load_e[ref_idx] - pv_fc_e[ref_idx]
    scan = []
    for method in ("highs", "highs-ds", "highs-ipm"):
        try:
            s = solve_plan(net_f, pv_fc_e[ref_idx], price, method=method)
            scan.append({"rule": f"method={method}", "obj": s["obj"],
                         "e_B_kwh": float(np.maximum(
                             load_e[ref_idx] - pv_act_e[ref_idx] + s["x"] - s["y"]
                             - s["q"], 0.0).sum())})
        except RuntimeError as exc:
            scan.append({"rule": f"method={method}", "error": str(exc)})
    for seed in range(8):
        s = solve_plan(net_f, pv_fc_e[ref_idx], price, jitter=1e-7, seed=seed)
        scan.append({"rule": f"jitter seed={seed}", "obj": s["obj"],
                     "e_B_kwh": float(np.maximum(
                         load_e[ref_idx] - pv_act_e[ref_idx] + s["x"] - s["y"]
                         - s["q"], 0.0).sum())})
    vals = [s["e_B_kwh"] for s in scan if "e_B_kwh" in s]
    objs = [s["obj"] for s in scan if "obj" in s]
    res["experiment_2_multiple_optima_scan"] = {
        "reference_day": ref_day.isoformat(),
        "n_solutions": len(vals),
        "e_B_min_kwh": float(min(vals)),
        "e_B_max_kwh": float(max(vals)),
        "e_B_pipeline_style_kwh": float(e_B[ref_idx]),
        "objective_min": float(min(objs)),
        "objective_max": float(max(objs)),
        "objective_spread_yuan": float(max(objs) - min(objs)),
        "detail": scan,
        "audit_daily_equivalent_kwh": float(AUDIT_EMG / n_days),
        "pipeline_daily_equivalent_kwh": float(PIPE_EMG / n_days),
    }
    res["daily_summary"] = {
        "convention_A_total_kwh": float(e_A.sum()),
        "convention_B_total_kwh": float(e_B.sum()),
        "plan_q_total_kwh": float(q_tot.sum()),
        "plan_discard_total_kwh": float(d_tot.sum()),
        "plan_objective_total_yuan": float(obj_tot),
        "days_with_A_emergency": int((e_A > 1e-9).sum()),
        "days_with_B_emergency": int((e_B > 1e-9).sum()),
    }
    OUT_JSON.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

    e1 = res["experiment_1_execution_convention"]     # type: ignore[index]
    e2 = res["experiment_2_multiple_optima_scan"]     # type: ignore[index]
    e3 = res["daily_summary"]                         # type: ignore[index]
    print("=== 实验 1：执行阶段口径 ===")
    print(f"  口径A（不扣实际光伏，审计写法）全年紧急购电 = {e1['annual_emergency_kwh_convention_A_no_pv']:,.2f} kWh")
    print(f"  口径B（扣实际光伏，契约写法）  全年紧急购电 = {e1['annual_emergency_kwh_convention_B_with_pv']:,.2f} kWh")
    print(f"  审计报告值 = {AUDIT_EMG:,.2f}  |  与口径A之差 = {e1['gap_A_vs_audit']:,.2f}")
    print(f"  流水线报告值 = {PIPE_EMG:,.2f}  |  与口径B之差 = {e1['gap_B_vs_pipeline']:,.2f}")
    print(f"  全年预报光伏 = {e1['annual_forecast_pv_kwh']:,.2f} kWh；全年实际光伏 = {e1['annual_actual_pv_kwh']:,.2f} kWh")
    print("=== 实验 2：多重最优扫描 ===")
    print(f"  参考日 {e2['reference_day']}，共 {e2['n_solutions']} 个解")
    print(f"  紧急购电(e_B) 取值范围 = [{e2['e_B_min_kwh']:,.2f}, {e2['e_B_max_kwh']:,.2f}] kWh")
    print(f"  目标值跨度 = {e2['objective_spread_yuan']:.3e} 元")
    print(f"  审计日均 {e2['audit_daily_equivalent_kwh']:,.2f} kWh / 流水线日均 {e2['pipeline_daily_equivalent_kwh']:,.2f} kWh")
    print("=== 汇总 ===")
    print(f"  计划购电合计 {e3['plan_q_total_kwh']:,.2f} kWh；计划弃光合计 {e3['plan_discard_total_kwh']:,.2f} kWh")
    print(f"  有紧急购电的天数：口径A {e3['days_with_A_emergency']} / 口径B {e3['days_with_B_emergency']}")
    print(f"\n写出：{OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
