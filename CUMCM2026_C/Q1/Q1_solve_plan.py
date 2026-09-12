"""问题 1 求解脚本 —— 单日（电价与负载每日相同）计划购电与储能充放电优化。

模型（线性规划）
================
决策变量（单位 kWh，``t = 1..144`` 为 10 分钟时段）：

* ``buy[t]``   计划购电量（微网从外网购入）
* ``chg[t]``   储能充电量（**入网侧**，即未计效率的充入电量）
* ``dis[t]``   储能放电量（**出网侧**，即馈入微网的放电电量）
* ``cur[t]``   弃光 / 限光电量（可行域松弛，见下）
* ``soc[t]``   第 ``t`` 时段**末**储电量，另含 ``soc[0]``（0:00 初值）

约束：

* 功率平衡（微网供电不低于小区负载，取等号最优）::

      buy[t] + dis[t] + (PV[t] - cur[t]) = load[t] + chg[t]

  其中负载/光伏已按 ``E = P * 10/60`` 折算为电量（kWh）。
  等价于 ``buy[t] = (load[t] - PV[t])/6 + chg[t] - dis[t] + cur[t]``。

* 储能递推：``soc[t] = soc[t-1] + eta*chg[t] - dis[t]/eta``，覆盖 ``t = 1..144`` 全部时段。
* 储能边界：``soc[0] = soc[144] = 6000``，``1200 <= soc[t] <= 10800``。
* 功率限值：``0 <= chg[t], dis[t] <= 5000/6``（= 833.3333 kWh/时段）。
* 弃光松弛：``0 <= cur[t] <= PV[t]/6``。

目标：``min Σ_t price[t] * buy[t]``。

.. note::
   ``cur[t]`` 只用于保证可行域非空（当光伏过剩且储能充满时）。本题附件 1 的
   数据下最优解 ``Σ cur = 0``，即**不存在弃光**——论文中不得写成"必须限光"。

口径（与 ``common/docs/C题_数据工程与结果规格.md`` 及队长裁定一致）
==================================================================
* ``result1.xlsx/计划购电量``：**144 行**，行标签采用**附件 1 口径**
  ``0:00-0:10 … 23:50-0:00+1``（队长裁定 R8）；第 ``r+1`` 行 = 时段 ``t = r``。
* ``result1.xlsx/充放电量``：**5 列**（无日期列）、6 个 4 小时区块，
  ``时刻`` 列仅第 2/3 行有值（``0:00`` / 文本 ``24:00``），``储电量`` 同为 0:00 / 24:00。

运行方式（在仓库根目录 ``D:\\MathModeling\\math-modeling-2026`` 下）::

    .venv\\Scripts\\python.exe CUMCM2026_C\\Q1\\Q1_solve_plan.py

产物
====
* ``Q1/outputs/result1.xlsx``                —— 提交结果文件（模板结构）
* ``Q1/outputs/Q1_timeseries.csv``           —— 144 时段全量明细（论文表格/复核用）
* ``Q1/outputs/figures/Q1_fig1..fig7*.png``  —— 论文插图
* ``Q1/outputs/Q1_diagnostics.json``         —— 指标、残差与自检记录
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

# --------------------------------------------------------------------------- #
# STAGE 0  环境与常量
# --------------------------------------------------------------------------- #
# 允许「直接 python Q1/Q1_solve_plan.py」运行：把仓库根加入 sys.path
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import matplotlib  # noqa: E402

matplotlib.use("TkAgg")  # 本项目约定：不使用 Agg
import matplotlib.pyplot as plt  # noqa: E402
import openpyxl  # noqa: E402
from openpyxl.styles import Alignment, Font, PatternFill  # noqa: E402
from scipy.optimize import linprog  # noqa: E402

from CUMCM2026_C.common.code import io_attachments as io  # noqa: E402
from CUMCM2026_C.common.code import paths  # noqa: E402

Q = 1
Q_DIR = paths.question_dir(Q)
OUT_DIR = paths.question_outputs(Q)
FIG_DIR = paths.question_figures(Q)
RESULT_FILE = paths.result_path("result1")
CSV_FILE = OUT_DIR / "Q1_timeseries.csv"
DIAG_FILE = OUT_DIR / "Q1_diagnostics.json"

T = paths.INTERVALS_PER_DAY            # 144
DT = paths.INTERVAL_MINUTES / 60.0     # 1/6 h
ETA = paths.STORAGE.efficiency         # 0.9
S_LO = paths.STORAGE.soc_min_kwh       # 1200
S_HI = paths.STORAGE.soc_max_kwh       # 10800
S_INIT = paths.STORAGE.soc_init_kwh    # 6000
CHG_MAX = paths.STORAGE.max_energy_per_interval_charge   # 833.3333…

# 字体：按可用性挑选，避免中文豆腐块
_FONT_CANDIDATES = ("Microsoft YaHei", "SimHei", "DengXian", "SimSun", "KaiTi")
_AVAILABLE_FONTS = {f.name for f in matplotlib.font_manager.fontManager.ttflist}
_CJK_FONT = next((f for f in _FONT_CANDIDATES if f in _AVAILABLE_FONTS), "DejaVu Sans")
plt.rcParams["font.sans-serif"] = [_CJK_FONT, *_FONT_CANDIDATES, "DejaVu Sans"]
plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 120
plt.rcParams["savefig.dpi"] = 200
plt.rcParams["savefig.bbox"] = "tight"
plt.rcParams["axes.grid"] = True
plt.rcParams["grid.alpha"] = 0.30
plt.rcParams["grid.linestyle"] = ":"

C_LOAD, C_PV, C_BUY = "#c0392b", "#e59f1b", "#2c6fbb"
C_CHG, C_DIS, C_SOC = "#1f8a4c", "#7b4fa8", "#2c6fbb"

# 表 1 要求的 6 个指定时段（题目原文：10:00-10:10、12:00-12:10、14:00-14:10、
# 16:00-16:10、18:00-18:10、20:00-20:10）
TABLE1_SLOTS = ["10:00-10:10", "12:00-12:10", "14:00-14:10",
                "16:00-16:10", "18:00-18:10", "20:00-20:10"]


def _log(msg: str) -> None:
    """打印带前缀的进度信息。"""
    print(f"[Q1] {msg}", flush=True)


def slot_to_interval(slot: str) -> int:
    """把 ``"10:00-10:10"`` 形式的时间段标签转成时段序号 ``t``（1..144）。

    标签的**起始分钟数**除以 10 再加 1 即时段序号：``10:00-10:10`` → ``61``。
    这里显式解析而**不是**用列表下标推断，避免与模板错位口径混淆。

    Args:
        slot: 形如 ``"H:MM-H:MM"`` 的时间段标签。

    Returns:
        时段序号 ``1..144``。

    Raises:
        ValueError: 标签格式不合法或超出一天范围。
    """
    head = slot.split("-")[0].strip()
    if ":" not in head:
        raise ValueError(f"时间段标签格式不合法：{slot!r}")
    hour_text, minute_text = head.split(":", 1)
    start_minutes = int(hour_text) * 60 + int(minute_text)
    if start_minutes % paths.INTERVAL_MINUTES or not 0 <= start_minutes < 24 * 60:
        raise ValueError(f"时间段标签不在 10 分钟网格上或超范围：{slot!r}")
    return start_minutes // paths.INTERVAL_MINUTES + 1


# --------------------------------------------------------------------------- #
# STAGE A  读取附件 1 并核查
# --------------------------------------------------------------------------- #
def load_data() -> dict:
    """读取附件 1 并构造建模所需的电量序列。

    Returns:
        含 ``price``/``load_kw``/``pv_kw``/``load_e``/``pv_e``/``net_e`` 等键的字典。
        ``net_e`` 为 ``(load - pv) * DT``，即不含储能时的净购电需求（可为负）。
    """
    att1 = io.load_attachment_1()
    price = np.asarray(att1.price.values, dtype=float)
    load_kw = np.asarray(att1.load.values, dtype=float)
    pv_kw = np.asarray(att1.pv_forecast.values, dtype=float)

    if not (len(price) == len(load_kw) == len(pv_kw) == T):
        raise ValueError(f"附件 1 长度异常：price={len(price)} load={len(load_kw)} pv={len(pv_kw)}")
    for name, arr in (("电价", price), ("负载", load_kw), ("光伏", pv_kw)):
        if not np.isfinite(arr).all():
            raise ValueError(f"附件 1 的{name}列存在非有限值（空值/文本）")
    if (load_kw < 0).any() or (pv_kw < 0).any():
        raise ValueError("附件 1 的负载或光伏列存在负值")
    if (price <= 0).any():
        raise ValueError("附件 1 的电价列存在非正值")

    load_e = io.interval_power_to_energy(load_kw)
    pv_e = io.interval_power_to_energy(pv_kw)
    net_e = load_e - pv_e

    _log(f"附件 1 读取完成：{T} 个时段；"
         f"负载 {load_e.sum():,.2f} kWh（峰值 {load_kw.max():,.2f} kW）；"
         f"光伏 {pv_e.sum():,.2f} kWh（峰值 {pv_kw.max():,.2f} kW）；"
         f"电价区间 [{price.min():.4f}, {price.max():.4f}] 元/kWh（均值 {price.mean():.4f}）")
    _log(f"净负荷（不含储能）{net_e.sum():,.2f} kWh；"
         f"光伏过剩时段数 {(net_e < 0).sum()}（最大过剩 {max(0.0, -net_e.min()):,.2f} kWh）")
    return {
        "price": price, "load_kw": load_kw, "pv_kw": pv_kw,
        "load_e": load_e, "pv_e": pv_e, "net_e": net_e,
    }


# --------------------------------------------------------------------------- #
# STAGE B  构造线性规划
# --------------------------------------------------------------------------- #
def build_lp(data: dict) -> dict:
    """组装线性规划的系数矩阵。

    变量排布：``[soc(145) | chg(144) | dis(144) | cur(144)]``，共 ``n = 577``。

    Args:
        data: :func:`load_data` 的返回值。

    Returns:
        含 ``c``/``A_ub``/``b_ub``/``A_eq``/``b_eq``/``bounds``/``n``/``slices``
        及 ``const``（目标中的常数项）的字典。
    """
    price, pv_e, net_e = data["price"], data["pv_e"], data["net_e"]

    n_soc = T + 1                      # soc[0] .. soc[144]
    i_soc, i_chg, i_dis, i_cur = 0, n_soc, n_soc + T, n_soc + 2 * T
    n = n_soc + 3 * T

    # 目标：buy[t] = net[t] + chg[t] - dis[t] + cur[t]
    #   =>  Σ price*buy = Σ price*net  +  Σ price*chg - Σ price*dis + Σ price*cur
    c = np.zeros(n)
    c[i_chg:i_chg + T] = price
    c[i_dis:i_dis + T] = -price
    c[i_cur:i_cur + T] = price
    const = float((price * net_e).sum())

    # 等式：储能递推 soc[t] - soc[t-1] - eta*chg[t] + dis[t]/eta = 0,  t = 1..144
    a_eq = np.zeros((T, n))
    for t in range(1, T + 1):
        row = t - 1
        a_eq[row, i_soc + t] = 1.0
        a_eq[row, i_soc + t - 1] = -1.0
        a_eq[row, i_chg + t - 1] = -ETA
        a_eq[row, i_dis + t - 1] = 1.0 / ETA
    b_eq = np.zeros(T)

    # 不等式：buy[t] >= 0  <=>  dis[t] - chg[t] - cur[t] <= net[t]
    a_ub = np.zeros((T, n))
    for t in range(T):
        a_ub[t, i_dis + t] = 1.0
        a_ub[t, i_chg + t] = -1.0
        a_ub[t, i_cur + t] = -1.0
    b_ub = net_e.copy()

    bounds = (
        [(S_INIT, S_INIT)]                            # soc[0] 钉死为 0:00 初值
        + [(S_LO, S_HI)] * (T - 1)                    # soc[1] .. soc[143]
        + [(S_INIT, S_INIT)]                          # soc[144] 日终归位
        + [(0.0, CHG_MAX)] * T                        # chg
        + [(0.0, CHG_MAX)] * T                        # dis
        + [(0.0, float(v)) for v in pv_e]             # cur <= 该时段光伏电量
    )

    return {
        "c": c, "const": const, "A_ub": a_ub, "b_ub": b_ub,
        "A_eq": a_eq, "b_eq": b_eq, "bounds": bounds, "n": n,
        "slices": {"soc": (i_soc, i_soc + n_soc), "chg": (i_chg, i_chg + T),
                   "dis": (i_dis, i_dis + T), "cur": (i_cur, i_cur + T)},
    }


# --------------------------------------------------------------------------- #
# STAGE C  求解与残差自检
# --------------------------------------------------------------------------- #
def solve(lp: dict) -> tuple[np.ndarray, dict]:
    """求解线性规划，并返回解向量与求解器信息。

    Args:
        lp: :func:`build_lp` 的返回值。

    Returns:
        ``(z, info)``：``z`` 为最优解向量，``info`` 含求解器状态与可行性结论。

    Raises:
        RuntimeError: 线性规划未求得最优解。
    """
    feas = linprog(np.zeros(lp["n"]), A_ub=lp["A_ub"], b_ub=lp["b_ub"],
                   A_eq=lp["A_eq"], b_eq=lp["b_eq"], bounds=lp["bounds"], method="highs")
    res = linprog(lp["c"], A_ub=lp["A_ub"], b_ub=lp["b_ub"],
                  A_eq=lp["A_eq"], b_eq=lp["b_eq"], bounds=lp["bounds"], method="highs")
    info = {
        "feasibility_status": int(feas.status),
        "feasibility_success": bool(feas.success),
        "optimizer_status": int(res.status),
        "optimizer_success": bool(res.success),
        "optimizer_message": str(res.message),
        "objective_from_solver": float(res.fun) if res.success else None,
        "n_variables": int(lp["n"]),
        "n_eq_constraints": int(lp["A_eq"].shape[0]),
        "n_ub_constraints": int(lp["A_ub"].shape[0]),
    }
    if not res.success:
        raise RuntimeError(f"线性规划求解失败：{res.message}")
    _log(f"求解成功：迭代 {getattr(res, 'nit', '?')} 次，"
         f"目标函数（含常数项）{lp['const'] + res.fun:,.6f} 元")
    return np.asarray(res.x, dtype=float), info


def extract(z: np.ndarray, lp: dict, data: dict) -> dict:
    """从解向量中还原各变量的时间序列，并按平衡式回代出购电量。

    Args:
        z: 最优解向量。
        lp: :func:`build_lp` 的返回值。
        data: :func:`load_data` 的返回值。

    Returns:
        含全部 144 维序列与派生量的字典。
    """
    s0, s1 = lp["slices"]["soc"]
    c0, c1 = lp["slices"]["chg"]
    d0, d1 = lp["slices"]["dis"]
    g0, g1 = lp["slices"]["cur"]

    # 数值清理：把 |v| < 1e-9 的抖动量归零，避免 -0.0 与 1e-13 级噪声进入结果文件
    def clean(a: np.ndarray) -> np.ndarray:
        """把求解器产生的亚容差抖动量归零。"""
        return np.where(np.abs(a) < 1e-9, 0.0, a)

    soc = clean(z[s0:s1])
    chg = clean(z[c0:c1])
    dis = clean(z[d0:d1])
    cur = clean(z[g0:g1])
    soc[0], soc[-1] = S_INIT, S_INIT
    buy = data["net_e"] + chg - dis + cur
    buy = clean(buy)
    return {"soc": soc, "chg": chg, "dis": dis, "cur": cur, "buy": buy}


def verify(sol: dict, lp: dict, data: dict) -> dict:
    """对最优解做独立残差与守恒自检（不依赖求解器自报结果）。

    Args:
        sol: :func:`extract` 的返回值。
        lp: :func:`build_lp` 的返回值。
        data: :func:`load_data` 的返回值。

    Returns:
        残差与自检指标字典。
    """
    price, load_e, pv_e = data["price"], data["load_e"], data["pv_e"]
    buy, chg, dis, cur, soc = (sol["buy"], sol["chg"], sol["dis"], sol["cur"], sol["soc"])

    # 1) 目标与费用：用回代出的 buy 重算，检验线性化是否闭合
    cost = float((price * buy).sum())
    cost_linear = float(lp["const"] + lp["c"] @ np.concatenate([soc, chg, dis, cur]))
    # 2) 储能递推逐时段残差（用 sol 自身，不用求解器矩阵）
    rec_resid = np.abs(np.diff(soc) - (ETA * chg - dis / ETA))
    # 3) 功率平衡残差：buy + dis + pv - cur - load - chg == 0
    bal_resid = np.abs(buy + dis + pv_e - cur - load_e - chg)
    # 4) 边界检查
    soc_violation = float(max(0.0, soc[1:-1].max() - S_HI, S_LO - soc[1:-1].min()))
    chg_violation = float(max(0.0, chg.max() - CHG_MAX, dis.max() - CHG_MAX))
    cur_violation = float(max(0.0, (cur - pv_e).max()))
    buy_violation = float(max(0.0, -buy.min()))

    # 5) 关键自检量：无额外损耗时 Σdis / Σchg 必等于 eta^2（本题为 0.81）
    ratio = float(dis.sum() / chg.sum()) if chg.sum() > 0 else float("nan")

    return {
        "cost_yuan": cost,
        "cost_from_linear_objective_yuan": cost_linear,
        "cost_objective_residual_yuan": abs(cost - cost_linear),
        "max_recurrence_residual_kwh": float(rec_resid.max()),
        "max_balance_residual_kwh": float(bal_resid.max()),
        "max_eq_matrix_residual": float(np.abs(lp["A_eq"] @ np.concatenate([soc, chg, dis, cur]) - lp["b_eq"]).max()),
        "soc_bounds_violation_kwh": soc_violation,
        "power_limit_violation_kwh": chg_violation,
        "curtail_limit_violation_kwh": cur_violation,
        "buy_nonneg_violation_kwh": buy_violation,
        "discharge_over_charge": ratio,
        "eta_squared_reference": ETA ** 2,
        "discharge_over_charge_gap": abs(ratio - ETA ** 2),
        "charge_equals_discharge_condition": bool(abs(chg.sum() - dis.sum()) > 0),
    }


# --------------------------------------------------------------------------- #
# STAGE D  指标汇总
# --------------------------------------------------------------------------- #
def summarise(sol: dict, data: dict) -> dict:
    """汇总论文与表格所需的全部指标。

    Args:
        sol: :func:`extract` 的返回值。
        data: :func:`load_data` 的返回值。

    Returns:
        指标字典（金额单位元、电量单位 kWh、功率单位 kW）。
    """
    price, load_e, pv_e = data["price"], data["load_e"], data["pv_e"]
    buy, chg, dis, cur, soc = (sol["buy"], sol["chg"], sol["dis"], sol["cur"], sol["soc"])

    # 公平基线 B0：不装储能（chg = dis = 0），不足部分全部外购、允许弃光
    net_e = data["net_e"]
    baseline_b0 = float((price * np.maximum(net_e, 0.0)).sum())
    baseline_no_curtail = float((price * net_e.clip(min=0)).sum())

    cost = float((price * buy).sum())
    blocks_chg = np.array([io.block_energy_from_intervals(chg, b) for b in range(1, 7)])
    blocks_dis = np.array([io.block_energy_from_intervals(dis, b) for b in range(1, 7)])

    peak_hours = price >= np.quantile(price, 0.75)
    valley_hours = price <= np.quantile(price, 0.25)

    return {
        "n_intervals": int(T),
        "interval_minutes": int(paths.INTERVAL_MINUTES),
        "price_mean_yuan_per_kwh": float(price.mean()),
        "price_min_yuan_per_kwh": float(price.min()),
        "price_max_yuan_per_kwh": float(price.max()),
        "load_total_kwh": float(load_e.sum()),
        "load_peak_kw": float(data["load_kw"].max()),
        "pv_total_kwh": float(pv_e.sum()),
        "pv_peak_kw": float(data["pv_kw"].max()),
        "net_load_total_kwh": float(net_e.sum()),
        "total_purchase_kwh": float(buy.sum()),
        "total_cost_yuan": cost,
        "mean_purchase_price_yuan_per_kwh": float(cost / buy.sum()),
        "baseline_B0_yuan": baseline_b0,
        "baseline_B0_note": "不安装储能：缺额全部外购，溢出不外送（公平基线）",
        "baseline_no_curtail_yuan": baseline_no_curtail,
        "storage_net_benefit_yuan": baseline_b0 - cost,
        "storage_net_benefit_ratio": (baseline_b0 - cost) / baseline_b0,
        "curtail_total_kwh": float(cur.sum()),
        "curtail_slots": int((cur > 1e-9).sum()),
        "charge_total_kwh": float(chg.sum()),
        "discharge_total_kwh": float(dis.sum()),
        "charge_loss_kwh": float(chg.sum() - dis.sum()),
        "charge_peak_kw": float(chg.max() / DT),
        "discharge_peak_kw": float(dis.max() / DT),
        "charge_slots": int((chg > 1e-9).sum()),
        "discharge_slots": int((dis > 1e-9).sum()),
        "soc_start_kwh": float(soc[0]),
        "soc_end_kwh": float(soc[-1]),
        "soc_min_kwh": float(soc.min()),
        "soc_max_kwh": float(soc.max()),
        "soc_min_at_interval": int(np.argmin(soc)),
        "soc_max_at_interval": int(np.argmax(soc)),
        "soc_min_at_clock": io.interval_label(int(np.argmin(soc))) if np.argmin(soc) >= 1
        else "0:00",
        "soc_max_at_clock": io.interval_label(int(np.argmax(soc))) if np.argmax(soc) >= 1
        else "0:00",
        "purchase_slots": int((buy > 1e-9).sum()),
        "zero_purchase_slots": int((buy <= 1e-9).sum()),
        "purchase_peak_kw": float(buy.max() / DT),
        "purchase_total_peak_quarter_kwh": float(buy[peak_hours].sum()),
        "purchase_total_valley_quarter_kwh": float(buy[valley_hours].sum()),
        "charge_in_valley_kwh": float(chg[valley_hours].sum()),
        "discharge_in_peak_kwh": float(dis[peak_hours].sum()),
        "block_labels": io.half_hour_block_labels(),
        "block_charge_kwh": [float(v) for v in blocks_chg],
        "block_discharge_kwh": [float(v) for v in blocks_dis],
        "table1_slots": TABLE1_SLOTS,
        "table1_purchase_kwh": [
            float(buy[slot_to_interval(slot) - 1]) for slot in TABLE1_SLOTS
        ],
        "table1_full_day_purchase_kwh": float(buy.sum()),
        "table1_full_day_cost_yuan": cost,
    }


# --------------------------------------------------------------------------- #
# STAGE E1  导出 result1.xlsx
# --------------------------------------------------------------------------- #
_PLAN_HEADER_FILL = PatternFill("solid", fgColor="DDEBF7")
_HEADER_FONT = Font(bold=True)


def write_result1(sol: dict, data: dict, sumry: dict) -> Path:
    """按附件 5 模板结构写出 ``result1.xlsx``。

    结构（与模板逐项一致，**只含模板的两个工作表**——验收脚本会逐字符比对
    工作表序列，多写辅助表会导致 ``工作表序列`` 校验失败；口径说明请见
    ``Q1/outputs/Q1_diagnostics.json``）：

    * ``计划购电量``：2 列 × 145 行（表头 + 144 个时段）；
      行标签用 ``io.result1_row_labels_decision()``（队长裁定 R8）。
    * ``充放电量``：5 列 × 7 行（表头 + 6 个 4 小时区块）；
      ``时刻`` 列仅第 2/3 行，写 ``0:00`` / 文本 ``24:00``，``储电量`` 与之同行。

    Args:
        sol: :func:`extract` 的返回值。
        data: :func:`load_data` 的返回值。
        sumry: :func:`summarise` 的返回值。

    Returns:
        写出的文件路径。
    """
    del data, sumry  # 结果文件只承载解本身；指标另见诊断 JSON
    buy, chg, dis, soc = sol["buy"], sol["chg"], sol["dis"], sol["soc"]
    wb = openpyxl.Workbook()

    # ---- 工作表 1：计划购电量 ----
    ws = wb.active
    ws.title = "计划购电量"
    ws.append(["时间段", "购电量"])
    for label, value in zip(io.result1_row_labels_decision(), buy.tolist()):
        ws.append([label, round(float(value), 4)])

    # ---- 工作表 2：充放电量 ----
    ws2 = wb.create_sheet("充放电量")
    ws2.append(["时间段", "充电量", "放电量", "时刻", "储电量"])
    for b, label in enumerate(io.half_hour_block_labels(), start=1):
        block_chg = io.block_energy_from_intervals(chg, b)
        block_dis = io.block_energy_from_intervals(dis, b)
        row = [label, round(block_chg, 4), round(block_dis, 4)]
        if b == 1:
            row += ["0:00", round(float(soc[0]), 4)]
        elif b == 2:
            row += ["24:00", round(float(soc[-1]), 4)]
        ws2.append(row)

    # ---- 样式 ----
    for sheet, widths in ((ws, (16, 14)), (ws2, (14, 14, 14, 10, 14))):
        for i, w in enumerate(widths, start=1):
            sheet.column_dimensions[openpyxl.utils.get_column_letter(i)].width = w
        for cell in sheet[1]:
            cell.font = _HEADER_FONT
            cell.fill = _PLAN_HEADER_FILL
            cell.alignment = Alignment(horizontal="center", vertical="center")
    for row in ws.iter_rows(min_row=2, min_col=2, max_col=2):
        row[0].number_format = "0.0000"
    for row in ws2.iter_rows(min_row=2, min_col=2, max_col=5):
        for cell in row:
            if cell.column_letter in {"B", "C", "E"}:
                cell.number_format = "0.0000"
    for coord in ("D2", "D3"):
        ws2[coord].number_format = "@"

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    wb.save(RESULT_FILE)
    wb.close()
    _log(f"结果文件写出：{RESULT_FILE}")
    return RESULT_FILE


# --------------------------------------------------------------------------- #
# STAGE E2  导出逐时段明细 CSV
# --------------------------------------------------------------------------- #
def write_csv(sol: dict, data: dict) -> Path:
    """导出 144 时段逐时刻明细（论文表格、复核与作图复用）。

    Args:
        sol: :func:`extract` 的返回值。
        data: :func:`load_data` 的返回值。

    Returns:
        写出的文件路径。
    """
    price, load_kw, pv_kw = data["price"], data["load_kw"], data["pv_kw"]
    buy, chg, dis, cur, soc = (sol["buy"], sol["chg"], sol["dis"], sol["cur"], sol["soc"])
    header = ["时段序号", "时间段", "电价(元/kWh)", "小区负载(kW)", "光伏预测功率(kW)",
              "负载电量(kWh)", "光伏电量(kWh)", "净负荷(kWh)", "计划购电量(kWh)",
              "充电量(kWh)", "放电量(kWh)", "弃光电量(kWh)", "时段末储电量(kWh)",
              "该时段购电费(元)"]
    lines = [",".join(header)]
    for t in range(1, T + 1):
        row = [t, io.interval_label(t), f"{price[t - 1]:.6f}", f"{load_kw[t - 1]:.6f}",
               f"{pv_kw[t - 1]:.6f}", f"{load_kw[t - 1] * DT:.6f}", f"{pv_kw[t - 1] * DT:.6f}",
               f"{data['net_e'][t - 1]:.6f}", f"{buy[t - 1]:.6f}", f"{chg[t - 1]:.6f}",
               f"{dis[t - 1]:.6f}", f"{cur[t - 1]:.6f}", f"{soc[t]:.6f}",
               f"{price[t - 1] * buy[t - 1]:.6f}"]
        lines.append(",".join(str(v) for v in row))
    CSV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    _log(f"逐时段明细写出：{CSV_FILE}")
    return CSV_FILE


# --------------------------------------------------------------------------- #
# STAGE E3  论文插图
# --------------------------------------------------------------------------- #
def _clock_labels() -> tuple[list[int], list[str]]:
    """生成横轴刻度位置与 ``HH:MM`` 标签（每 2 小时一格）。"""
    pos = [i for i in range(0, T + 1, 12)]
    labels = [f"{int(i * paths.INTERVAL_MINUTES) // 60:02d}:00" for i in pos]
    labels[-1] = "24:00"
    return pos, labels


def _apply_time_axis(ax: plt.Axes) -> None:
    """把横轴设置为 0:00–24:00 的时钟刻度。"""
    pos, labels = _clock_labels()
    ax.set_xlim(0, T)
    ax.set_xticks(pos)
    ax.set_xticklabels(labels)


def make_figures(sol: dict, data: dict, sumry: dict) -> list[Path]:
    """生成论文用插图。

    Args:
        sol: :func:`extract` 的返回值。
        data: :func:`load_data` 的返回值。
        sumry: :func:`summarise` 的返回值。

    Returns:
        生成的 PNG 路径列表。
    """
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    price, load_kw, pv_kw = data["price"], data["load_kw"], data["pv_kw"]
    buy, chg, dis, cur, soc = (sol["buy"], sol["chg"], sol["dis"], sol["cur"], sol["soc"])
    x = np.arange(1, T + 1)
    made: list[Path] = []

    # 图 1：电价与净负荷图谱（建模依据）
    fig, ax = plt.subplots(figsize=(9, 3.6))
    ax.fill_between(x, 0, load_kw, color=C_LOAD, alpha=0.20, label="小区负载")
    ax.plot(x, load_kw, color=C_LOAD, lw=1.4)
    ax.fill_between(x, 0, pv_kw, color=C_PV, alpha=0.45, label="光伏发电预测")
    ax.plot(x, pv_kw, color=C_PV, lw=1.4)
    ax.set_ylabel("功率 / kW")
    ax.set_xlabel("时刻")
    _apply_time_axis(ax)
    ax2 = ax.twinx()
    ax2.plot(x, price, color="#333333", lw=1.8, ls="--", label="电价")
    ax2.set_ylabel("电价 / (元·kWh$^{-1}$)")
    ax2.grid(False)
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", ncol=3, fontsize=8, framealpha=0.9)
    ax.set_title("图1  附件 1 电价、小区负载与光伏发电预测功率")
    fig.savefig(FIG_DIR / "Q1_fig1_price_load_pv.png")
    made.append(FIG_DIR / "Q1_fig1_price_load_pv.png")
    plt.close(fig)

    # 图 2：最优购电与充放电策略
    fig, ax = plt.subplots(figsize=(9, 3.8))
    ax.bar(x, buy, width=0.9, color=C_BUY, alpha=0.55, label="计划购电量")
    ax.bar(x, chg, width=0.9, bottom=buy, color=C_CHG, alpha=0.75, label="储能充电量")
    ax.bar(x, -dis, width=0.9, color=C_DIS, alpha=0.75, label="储能放电量")
    ax.axhline(0, color="#444444", lw=0.8)
    ax.set_ylabel("电量 / kWh（每 10 分钟）")
    ax.set_xlabel("时刻")
    _apply_time_axis(ax)
    ax.legend(loc="upper left", ncol=3, fontsize=8)
    ax.set_title("图2  问题 1 最优计划购电量与储能充放电量")
    fig.savefig(FIG_DIR / "Q1_fig2_dispatch.png")
    made.append(FIG_DIR / "Q1_fig2_dispatch.png")
    plt.close(fig)

    # 图 3：储电量轨迹与运行边界
    fig, ax = plt.subplots(figsize=(9, 3.4))
    ax.plot(np.arange(0, T + 1), soc, color=C_SOC, lw=2.0, label="储电量轨迹")
    ax.fill_between(np.arange(0, T + 1), S_LO, S_HI, color=C_SOC, alpha=0.08)
    ax.axhline(S_HI, color="#b03a2e", ls="--", lw=1.1, label=f"运行上界 {S_HI:.0f} kWh")
    ax.axhline(S_LO, color="#b03a2e", ls=":", lw=1.1, label=f"运行下界 {S_LO:.0f} kWh")
    _apply_time_axis(ax)
    ax.set_xlabel("时刻")
    ax.set_ylabel("储电量 / kWh")
    ax.legend(loc="lower left", fontsize=8, ncol=3)
    ax.set_title("图3  储电量轨迹与运行区间约束")
    fig.savefig(FIG_DIR / "Q1_fig3_soc.png")
    made.append(FIG_DIR / "Q1_fig3_soc.png")
    plt.close(fig)

    # 图 4：供电来源堆叠图与功率平衡
    fig, ax = plt.subplots(figsize=(9, 3.6))
    pv_used = data["pv_e"] - cur
    ax.stackplot(x, pv_used, dis, buy,
                 labels=["光伏发电", "储能放电", "外网购电"],
                 colors=[C_PV, C_DIS, C_BUY], alpha=1.0, edgecolor="none")
    ax.plot(x, data["load_e"], color="#111111", lw=1.7, label="小区负载")
    ax.plot(x, data["load_e"] + chg, color="#0b3d1f", lw=1.3, ls="--",
            label="负载 + 储能充电")
    ax.set_ylabel("电量 / kWh（每 10 分钟）")
    ax.set_xlabel("时刻")
    _apply_time_axis(ax)
    ax.legend(loc="upper left", ncol=3, fontsize=8, framealpha=0.95)
    ax.set_title("图4  微网供电来源构成与功率平衡校核")
    fig.savefig(FIG_DIR / "Q1_fig4_balance.png")
    made.append(FIG_DIR / "Q1_fig4_balance.png")
    plt.close(fig)

    # 图 5：有无储能对比
    fig, ax = plt.subplots(figsize=(9, 3.5))
    base = np.maximum(data["net_e"], 0.0)
    w = 0.42
    idx = np.arange(T)
    ax.bar(idx - w / 2, base, width=w, color="#9aa5b1", label="不装储能：外网购电")
    ax.bar(idx + w / 2, buy, width=w, color=C_BUY, label="装储能：计划购电")
    ax.set_ylabel("电量 / kWh（每 10 分钟）")
    ax.set_xlabel("时刻")
    _apply_time_axis(ax)
    ax.legend(loc="upper left", fontsize=8)
    ax.set_title("图5  有无储能两种情形下的逐时段购电量对比")
    fig.savefig(FIG_DIR / "Q1_fig5_vs_baseline.png")
    made.append(FIG_DIR / "Q1_fig5_vs_baseline.png")
    plt.close(fig)

    # 图 6：4 小时区块充放电量
    fig, ax = plt.subplots(figsize=(7.2, 3.4))
    labels = io.half_hour_block_labels()
    pos = np.arange(len(labels))
    bc = np.array(sumry["block_charge_kwh"])
    bd = np.array(sumry["block_discharge_kwh"])
    ax.bar(pos - 0.19, bc, width=0.38, color=C_CHG, label="充电量")
    ax.bar(pos + 0.19, bd, width=0.38, color=C_DIS, label="放电量")
    ax.set_xticks(pos)
    ax.set_xticklabels(labels, fontsize=8)
    ax.set_ylabel("电量 / kWh")
    ax.legend(fontsize=8)
    ax.set_title("图6  储能在 6 个 4 小时区块的充放电量（表 2 内容）")
    fig.savefig(FIG_DIR / "Q1_fig6_blocks.png")
    made.append(FIG_DIR / "Q1_fig6_blocks.png")
    plt.close(fig)

    # 图 7：经济性对比
    fig, ax = plt.subplots(figsize=(6.0, 3.4))
    names = ["不装储能基线\n$B_0$", "装储能最优\n$C^*$", "储能净收益\n$B_0-C^*$"]
    vals = [sumry["baseline_B0_yuan"], sumry["total_cost_yuan"],
            sumry["storage_net_benefit_yuan"]]
    bars = ax.bar(names, vals, color=["#9aa5b1", C_BUY, C_CHG], width=0.55)
    for bar, v in zip(bars, vals):
        ax.text(bar.get_x() + bar.get_width() / 2, v, f"{v:,.2f}", ha="center",
                va="bottom", fontsize=9)
    ax.set_ylabel("费用 / 元")
    ax.set_ylim(0, max(vals) * 1.18)
    ax.set_title("图7  储能带来的费用削减（单日）")
    fig.savefig(FIG_DIR / "Q1_fig7_economics.png")
    made.append(FIG_DIR / "Q1_fig7_economics.png")
    plt.close(fig)

    _log(f"插图写出 {len(made)} 张 → {FIG_DIR}")
    return made


# --------------------------------------------------------------------------- #
# STAGE E4  诊断日志
# --------------------------------------------------------------------------- #
def write_diagnostics(data: dict, lp: dict, info: dict, sol: dict, sumry: dict,
                      checks: dict, figures: list[Path]) -> Path:
    """写出诊断日志 JSON。

    Args:
        data: :func:`load_data` 的返回值。
        lp: :func:`build_lp` 的返回值。
        info: :func:`solve` 返回的求解器信息。
        sol: :func:`extract` 的返回值。
        sumry: :func:`summarise` 的返回值。
        checks: :func:`verify` 的返回值。
        figures: 生成的插图路径列表。

    Returns:
        写出的文件路径。
    """
    payload = {
        "question": "问题1",
        "result_file": str(RESULT_FILE),
        "timeseries_csv": str(CSV_FILE),
        "figures": [str(p) for p in figures],
        "solver": info,
        "model_spec": {
            "objective": "min Σ_t c_t·buy_t（c_t 为附件 1 电价，buy_t 为计划购电量）",
            "variables": "buy(144), chg(144), dis(144), cur(144), soc(145)；回代后线性规划变量 577 个",
            "balance": "buy_t + dis_t + (PV_t - cur_t) = load_t + chg_t",
            "recurrence": "soc_t = soc_{t-1} + η·chg_t - dis_t/η，t = 1..144",
            "bounds": "soc_0 = soc_144 = 6000；1200 ≤ soc_t ≤ 10800；"
                      "0 ≤ chg_t, dis_t ≤ 5000/6 = 833.3333；0 ≤ cur_t ≤ PV_t；buy_t ≥ 0",
            "energy_conversion": "电量(kWh) = 功率(kW) × 10/60",
            "fair_baseline": "B0 = Σ_t c_t·max(load_t - PV_t, 0)（不装储能、缺额全外购）",
        },
        "result_file_sheets": {
            "计划购电量": "2 列 × 145 行：表头 + io.result1_row_labels_decision() 的 144 个行标签",
            "充放电量": "5 列 × 7 行（无日期列）：6 个 4 小时区块；时刻列 = 0:00 / '24:00'，"
                        "储电量列与之同行，均为 6000 kWh",
        },
        "table1": {
            "slots": sumry["table1_slots"],
            "purchase_kwh": sumry["table1_purchase_kwh"],
            "full_day_purchase_kwh": sumry["table1_full_day_purchase_kwh"],
            "full_day_cost_yuan": sumry["table1_full_day_cost_yuan"],
        },
        "table2": {
            "slots": sumry["block_labels"],
            "charge_kwh": sumry["block_charge_kwh"],
            "discharge_kwh": sumry["block_discharge_kwh"],
            "soc_0_00_kwh": sumry["soc_start_kwh"],
            "soc_24_00_kwh": sumry["soc_end_kwh"],
        },
        "sanity_checks": checks,
        "metrics": sumry,
        "independent_reference": {
            "source": "common/diagnostics/problem1_reference_solution.json（重构前队长独立 LP）",
            "total_purchase_kwh": 59482.69899835392,
            "total_cost_yuan": 35126.948589289634,
            "charge_kwh": 20740.66613168725,
            "discharge_kwh": 16799.939566666668,
            "baseline_B0_yuan": 48052.046590846665,
            "match_purchase_kwh": abs(sumry["total_purchase_kwh"] - 59482.69899835392),
            "match_cost_yuan": abs(sumry["total_cost_yuan"] - 35126.948589289634),
            "match_charge_kwh": abs(sumry["charge_total_kwh"] - 20740.66613168725),
            "match_discharge_kwh": abs(sumry["discharge_total_kwh"] - 16799.939566666668),
            "match_baseline_yuan": abs(sumry["baseline_B0_yuan"] - 48052.046590846665),
        },
        "conventions": {
            "row_labels": "io.result1_row_labels_decision()（附件 1 口径，队长裁定 R8）",
            "charge_discharge_sheet": "5 列（无日期列），时刻列第 2/3 行 = 0:00 / '24:00'",
            "energy_conversion": "kWh = kW × 10/60",
            "curtailment": "cur 为可行域松弛；本数据下最优解 Σcur = 0，不存在弃光",
        },
        "limitations": [
            "附件 1 为典型日参数（2025 全年逐时段均值），其最优策略不能直接外推至全年费用。",
            "电价与负载被假定每日完全相同；问题 2 起逐日变化，本问结论不适用于彼。",
            "模型为确定性线性规划，未考虑光伏预测误差；问题 3 引入多时刻预报后再讨论。",
        ],
    }
    DIAG_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(f"诊断日志写出：{DIAG_FILE}")
    return DIAG_FILE


# --------------------------------------------------------------------------- #
# 主流程
# --------------------------------------------------------------------------- #
def main() -> int:
    """执行问题 1 的完整求解与落盘流程。

    Returns:
        进程退出码；``0`` 表示全部自检通过，``1`` 表示存在超容差残差。
    """
    paths.ensure_output_dirs()
    _log(f"输出目录 {OUT_DIR}；中文字体 {_CJK_FONT}")

    data = load_data()
    lp = build_lp(data)
    z, info = solve(lp)
    sol = extract(z, lp, data)
    checks = verify(sol, lp, data)
    sumry = summarise(sol, data)

    _log("—— 关键指标 ——")
    for key in ("total_purchase_kwh", "total_cost_yuan", "charge_total_kwh",
                "discharge_total_kwh", "curtail_total_kwh", "soc_min_kwh", "soc_max_kwh",
                "baseline_B0_yuan", "storage_net_benefit_yuan"):
        _log(f"  {key:26s} = {sumry[key]:,.6f}")
    _log("—— 自检残差 ——")
    for key in ("cost_objective_residual_yuan", "max_recurrence_residual_kwh",
                "max_balance_residual_kwh", "max_eq_matrix_residual",
                "discharge_over_charge", "eta_squared_reference",
                "discharge_over_charge_gap"):
        _log(f"  {key:34s} = {checks[key]:.3e}"
             if isinstance(checks[key], float) else f"  {key:34s} = {checks[key]}")

    result = write_result1(sol, data, sumry)
    csv_path = write_csv(sol, data)
    figures = make_figures(sol, data, sumry)
    write_diagnostics(data, lp, info, sol, sumry, checks, figures)

    # ---- 写入后立即回读，确认落盘内容与内存解一致 ----
    del result, csv_path
    import importlib

    validator = importlib.import_module("CUMCM2026_C.common.code.validate_results")
    report = validator.validate_result1(RESULT_FILE)
    _log("—— 结果文件回读验收 ——")
    for check in report.checks:
        _log(f"  [{check.status:>7s}] {check.criterion}  {check.detail}")
    n_failed = len(report.failed)

    ok_residuals = (
        checks["cost_objective_residual_yuan"] < 1e-6
        and checks["max_recurrence_residual_kwh"] < 1e-6
        and checks["max_balance_residual_kwh"] < 1e-6
        and checks["discharge_over_charge_gap"] < 1e-9
    )
    if not ok_residuals:
        _log("！！存在超容差残差，请检查模型构造")
    if n_failed:
        _log(f"！！结果文件验收有 {n_failed} 项失败")
    _log("完成。" if (ok_residuals and n_failed == 0) else "完成（存在告警）。")
    return 0 if (ok_residuals and n_failed == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
