r"""问题 1 结果分析：论文"模型的求解"章节所需的定量证据。

本脚本**不重复求解主模型**（主模型见 ``Q1_solve_plan.py``），只做三件事：

1. 从 ``Q1/outputs/Q1_diagnostics.json``、``Q1/outputs/Q1_timeseries.csv``
   与 ``Q1/outputs/result1.xlsx`` 中提取结构化证据：电价分档、充放电时段画像、
   储电量轨迹事件、功率平衡账、与无储能基线的逐时段差异。
2. 做两项**独立再求解**的灵敏度实验：
   * 储能效率 $\eta$ 取 0.85 / 0.90 / 0.95 时最优费用与弃光量的变化；
   * 去掉弃光松弛项（``g_t ≡ 0``）后的最优费用，用于判断松弛是否被使用。
3. 把全部证据写入 ``Q1/outputs/Q1_analysis.json``，供求解章节引用。

用法（在仓库根目录）::

    .venv\\Scripts\\python.exe CUMCM2026_C\\Q1\\Q1_analysis.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scipy.optimize import linprog  # noqa: E402

from CUMCM2026_C.common.code import io_attachments as io  # noqa: E402
from CUMCM2026_C.common.code import paths  # noqa: E402

Q = 1
OUT_DIR = paths.question_outputs(Q)
DIAG = OUT_DIR / "Q1_diagnostics.json"
CSV = OUT_DIR / "Q1_timeseries.csv"
RESULT = paths.result_path("result1")
ANALYSIS = OUT_DIR / "Q1_analysis.json"

T = paths.INTERVALS_PER_DAY
DT = paths.INTERVAL_MINUTES / 60.0
S_LO = paths.STORAGE.soc_min_kwh
S_HI = paths.STORAGE.soc_max_kwh
S_INIT = paths.STORAGE.soc_init_kwh
CHG_MAX = paths.STORAGE.max_energy_per_interval_charge


def _log(msg: str) -> None:
    """打印带前缀的日志。"""
    print(f"[Q1-analysis] {msg}", flush=True)


def load_series() -> dict[str, np.ndarray]:
    """从逐时段 CSV 读回全部序列（**以落盘文件为准**，而非内存解）。

    Returns:
        含各列的字典，键名与 CSV 表头对应。
    """
    text = CSV.read_text(encoding="utf-8-sig").strip().splitlines()
    header = [h.strip() for h in text[0].split(",")]
    rows = [line.split(",") for line in text[1:]]
    out: dict[str, np.ndarray] = {}
    for j, name in enumerate(header):
        if j == 0:
            out[name] = np.array([int(r[j]) for r in rows])
        elif j == 1:
            out[name] = np.array([r[j] for r in rows], dtype=object)
        else:
            out[name] = np.array([float(r[j]) for r in rows])
    if out["时段序号"].size != T:
        raise ValueError(f"逐时段 CSV 行数异常：{out['时段序号'].size} != {T}")
    return out


def price_and_regime(series: dict[str, np.ndarray]) -> dict:
    """电价分档与"低储高放"运行画像。

    Args:
        series: :func:`load_series` 的返回值。

    Returns:
        电价分位数、充电/放电加权均价、分位数分档下的电量分布等。
    """
    price = series["电价(元/kWh)"]
    chg, dis, buy = series["充电量(kWh)"], series["放电量(kWh)"], series["计划购电量(kWh)"]
    load = series["小区负载(kW)"]
    lab = series["时间段"]

    q25, q50, q75 = (float(np.quantile(price, q)) for q in (0.25, 0.50, 0.75))
    low, high = price <= q25, price >= q75
    chg_slots = np.flatnonzero(chg > 1e-9)
    dis_slots = np.flatnonzero(dis > 1e-9)

    def blocks(idx: np.ndarray) -> list[list[object]]:
        """把不连续的下标集合合并成连续区段，返回 [起标签, 止标签, 时段数, 电量合计]。"""
        if idx.size == 0:
            return []
        out, start, prev = [], idx[0], idx[0]
        for cur in idx[1:]:
            if cur != prev + 1:
                out.append([start, prev])
                start = cur
            prev = cur
        out.append([start, prev])
        segs = []
        for a, b in out:
            segs.append([str(lab[a]), str(lab[b]), int(b - a + 1),
                         float(chg[a:b + 1].sum() + dis[a:b + 1].sum())])
        return segs

    charging_total = float(chg.sum())
    discharging_total = float(dis.sum())
    return {
        "price_quantiles": {"q25": q25, "median": q50, "q75": q75},
        "price_bins": {
            "low_count": int(low.sum()), "mid_count": int((~low & ~high).sum()),
            "high_count": int(high.sum()),
            "buy_share_low": float(buy[low].sum() / buy.sum()),
            "buy_share_high": float(buy[high].sum() / buy.sum()),
            "charge_share_low": float(chg[low].sum() / charging_total),
            "charge_share_high": float(chg[high].sum() / charging_total),
            "discharge_share_low": float(dis[low].sum() / discharging_total) if discharging_total else 0.0,
            "discharge_share_high": float(dis[high].sum() / discharging_total) if discharging_total else 0.0,
        },
        "charge_weighted_price": float((price * chg).sum() / charging_total) if charging_total else None,
        "discharge_weighted_price": float((price * dis).sum() / discharging_total) if discharging_total else None,
        "buy_weighted_price": float((price * buy).sum() / buy.sum()),
        "plain_price_mean": float(price.mean()),
        "charge_regimes": blocks(chg_slots),
        "discharge_regimes": blocks(dis_slots),
        "charge_slots": int(chg_slots.size),
        "discharge_slots": int(dis_slots.size),
        "peak_load_slot": str(lab[int(np.argmax(load))]),
        "peak_load_slot_kwh": float(series["负载电量(kWh)"][int(np.argmax(load))]),
    }


def storage_events(series: dict[str, np.ndarray]) -> dict:
    """储电量轨迹的分段走向与关键极值时刻。

    Args:
        series: :func:`load_series` 的返回值。

    Returns:
        极值时刻、触界时段数、上升/下降段统计等。
    """
    soc = series["时段末储电量(kWh)"]
    lab = series["时间段"]
    path = np.concatenate([[S_INIT], soc])
    d_soc = np.diff(path)
    up = d_soc > 1e-9
    down = d_soc < -1e-9

    def span(mask: np.ndarray) -> list[list[object]]:
        """把布尔掩码中的 True 连续段合并为 [起标签, 止标签, 段数]。"""
        idx = np.flatnonzero(mask)
        if idx.size == 0:
            return []
        segs, start, prev = [], idx[0], idx[0]
        for cur in idx[1:]:
            if cur != prev + 1:
                segs.append([str(lab[start]), str(lab[prev])])
                start = cur
            prev = cur
        segs.append([str(lab[start]), str(lab[prev])])
        return segs

    return {
        "soc_start": float(path[0]),
        "soc_end": float(path[-1]),
        "soc_min": float(path.min()),
        "soc_max": float(path.max()),
        "soc_min_clock": str(lab[int(np.argmin(path)) - 1]) if int(np.argmin(path)) >= 1 else "0:00",
        "soc_max_clock": str(lab[int(np.argmax(path)) - 1]) if int(np.argmax(path)) >= 1 else "0:00",
        "slots_at_upper_bound": int(np.sum(np.abs(path - S_HI) < 1e-6)),
        "slots_at_lower_bound": int(np.sum(np.abs(path - S_LO) < 1e-6)),
        "charge_span": span(up),
        "discharge_span": span(down),
        "idle_slots": int(np.sum(~up & ~down)),
    }


def energy_account(series: dict[str, np.ndarray]) -> dict:
    """全天功率平衡账（电量口径）。

    Args:
        series: :func:`load_series` 的返回值。

    Returns:
        各供给侧/需求侧电量与闭合残差。
    """
    pv = series["光伏电量(kWh)"]
    cur = series["弃光电量(kWh)"]
    dis = series["放电量(kWh)"]
    buy = series["计划购电量(kWh)"]
    load_e = series["负载电量(kWh)"]
    chg = series["充电量(kWh)"]

    supply = float(pv.sum() - cur.sum() + dis.sum() + buy.sum())
    demand = float(load_e.sum() + chg.sum())
    return {
        "pv_kwh": float(pv.sum()),
        "curtail_kwh": float(cur.sum()),
        "discharge_kwh": float(dis.sum()),
        "purchase_kwh": float(buy.sum()),
        "supply_total_kwh": supply,
        "load_kwh": float(load_e.sum()),
        "charge_kwh": float(chg.sum()),
        "demand_total_kwh": demand,
        "account_residual_kwh": abs(supply - demand),
        "storage_throughput_loss_kwh": float(chg.sum() - dis.sum()),
        "self_sufficiency_ratio": float(1.0 - buy.sum() / demand),
        "pv_consumption_ratio": float(1.0 - cur.sum() / pv.sum()),
    }


def baseline_comparison(series: dict[str, np.ndarray]) -> dict:
    """与不装储能基线 B0 的逐时段对比。

    Args:
        series: :func:`load_series` 的返回值。

    Returns:
        基线费用、削减额与削减率的时段分布、逐时段差值集中度。
    """
    price = series["电价(元/kWh)"]
    net = series["净负荷(kWh)"]
    buy = series["计划购电量(kWh)"]
    base = np.maximum(net, 0.0)
    b0 = float((price * base).sum())
    cost = float((price * buy).sum())
    delta = price * (base - buy)

    top = np.argsort(-delta)[:10]
    return {
        "baseline_B0_yuan": b0,
        "optimal_cost_yuan": cost,
        "saving_yuan": b0 - cost,
        "saving_ratio": (b0 - cost) / b0,
        "delta_total_yuan": float(delta.sum()),
        "delta_negative_slots": int((delta < -1e-9).sum()),
        "delta_negative_yuan": float(delta[delta < 0].sum()),
        "top_saving_slots": [
            {"slot": str(series["时间段"][i]), "price": float(price[i]),
             "baseline_kwh": float(base[i]), "plan_kwh": float(buy[i]),
             "saving_yuan": float(delta[i])}
            for i in top
        ],
        "baseline_zero_purchase_slots": int((base <= 1e-9).sum()),
        "plan_zero_purchase_slots": int((buy <= 1e-9).sum()),
        "baseline_peak_kw": float(base.max() / DT),
        "plan_peak_kw": float(buy.max() / DT),
    }


def solve_variant(price: np.ndarray, net: np.ndarray, pv_e: np.ndarray,
                  eta: float, allow_curtail: bool) -> dict:
    """在给定效率与是否允许弃光的设置下重新求解同一线性规划。

    Args:
        price: 144 维电价。
        net: 144 维净负荷电量。
        pv_e: 144 维光伏电量。
        eta: 储能充放电效率。
        allow_curtail: 是否保留弃光松弛项。

    Returns:
        含最优费用、购电量、充放电量与弃光量的字典。
    """
    n_soc = T + 1
    n_cur = T if allow_curtail else 0
    i_soc, i_chg, i_dis, i_cur = 0, n_soc, n_soc + T, n_soc + 2 * T
    n = n_soc + 2 * T + n_cur

    c = np.zeros(n)
    c[i_chg:i_chg + T] = price
    c[i_dis:i_dis + T] = -price
    if allow_curtail:
        c[i_cur:i_cur + T] = price
    const = float((price * net).sum())

    a_eq = np.zeros((T, n))
    for t in range(1, T + 1):
        r = t - 1
        a_eq[r, i_soc + t] = 1.0
        a_eq[r, i_soc + t - 1] = -1.0
        a_eq[r, i_chg + t - 1] = -eta
        a_eq[r, i_dis + t - 1] = 1.0 / eta

    nobs = T + n_cur
    a_ub = np.zeros((nobs, n))
    b_ub = np.zeros(nobs)
    for t in range(T):
        a_ub[t, i_dis + t] = 1.0
        a_ub[t, i_chg + t] = -1.0
        if allow_curtail:
            a_ub[t, i_cur + t] = -1.0
        b_ub[t] = net[t]
    if allow_curtail:  # 弃光不得超过可用光伏
        for t in range(T):
            a_ub[T + t, i_cur + t] = 1.0
            b_ub[T + t] = pv_e[t]

    bounds = ([(S_INIT, S_INIT)] + [(S_LO, S_HI)] * (T - 1) + [(S_INIT, S_INIT)]
              + [(0.0, CHG_MAX)] * T + [(0.0, CHG_MAX)] * T
              + ([(0.0, float(v)) for v in pv_e] if allow_curtail else []))

    res = linprog(c, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=np.zeros(T),
                  bounds=bounds, method="highs")
    if not res.success:
        return {"eta": eta, "allow_curtail": allow_curtail, "success": False,
                "message": str(res.message)}
    z = res.x
    chg = np.where(np.abs(z[i_chg:i_chg + T]) < 1e-9, 0.0, z[i_chg:i_chg + T])
    dis = np.where(np.abs(z[i_dis:i_dis + T]) < 1e-9, 0.0, z[i_dis:i_dis + T])
    cur = (np.where(np.abs(z[i_cur:i_cur + T]) < 1e-9, 0.0, z[i_cur:i_cur + T])
           if allow_curtail else np.zeros(T))
    buy = net + chg - dis + cur
    return {
        "eta": eta, "allow_curtail": allow_curtail, "success": True,
        "objective_yuan": float(const + res.fun),
        "recomputed_cost_yuan": float((price * buy).sum()),
        "purchase_kwh": float(buy.sum()),
        "charge_kwh": float(chg.sum()),
        "discharge_kwh": float(dis.sum()),
        "curtail_kwh": float(cur.sum()),
        "discharge_over_charge": float(dis.sum() / chg.sum()) if chg.sum() > 0 else None,
        "eta_squared": eta ** 2,
    }


def arbitrage_account(series: dict[str, np.ndarray]) -> dict:
    """把储能净收益拆成"放电替代外购"与"所耗存储电量成本"两项。

    放电时段的外购替代额按放电量 × 该时段电价计；所耗存储电量按其**充电加权
    平均电价**并计入效率损失折算。两者之差即套利本身的净收益，与对基线 $B_0$
    的总净收益之差则来自填谷侧的购电替代。

    Args:
        series: :func:`load_series` 的返回值。

    Returns:
        套利收益分解。
    """
    price = series["电价(元/kWh)"]
    chg, dis = series["充电量(kWh)"], series["放电量(kWh)"]
    eta = paths.STORAGE.efficiency
    chg_avg = float((price * chg).sum() / chg.sum())
    gross = float((price * dis).sum())
    stored_cost = chg_avg * float(dis.sum()) / eta
    total_saving = float((price * np.maximum(series["净负荷(kWh)"], 0.0)).sum()
                         - (price * series["计划购电量(kWh)"]).sum())
    return {
        "charge_weighted_price_yuan_per_kwh": chg_avg,
        "discharge_avoided_cost_yuan": gross,
        "stored_energy_cost_yuan": stored_cost,
        "arbitrage_net_yuan": gross - stored_cost,
        "total_saving_vs_baseline_yuan": total_saving,
        "valley_purchase_substitution_yuan": total_saving - (gross - stored_cost),
        "same_slot_charge_and_discharge_count": int(
            ((chg > 1e-9) & (dis > 1e-9)).sum()
        ),
    }


def attachment1_representativeness(data_root: Path | None = None) -> dict:
    """量化附件 1（典型日曲线）相对附件 2 全年逐日数据的代表性。

    Args:
        data_root: 保留参数，未使用（数据一律来自 :mod:`io_attachments`）。

    Returns:
        附件 1 净负荷合计、附件 2 逐日净负荷的均值与离散度、日负荷与日电价的相关性。
    """
    del data_root
    att1 = io.load_attachment_1()
    att2 = io.load_attachment_2()
    att4 = io.load_attachment_4()

    net1 = (io.interval_power_to_energy(att1.load.values)
            - io.interval_power_to_energy(att1.pv_forecast.values))
    net2 = io.interval_power_to_energy(att2.load) - io.interval_power_to_energy(att2.pv_actual)
    daily_load = att2.load.sum(axis=1)
    daily_price = att4.price.mean(axis=1)
    daily_net = net2.sum(axis=1)

    return {
        "att1_net_load_kwh": float(net1.sum()),
        "att2_daily_net_mean_kwh": float(daily_net.mean()),
        "att2_daily_net_std_kwh": float(daily_net.std(ddof=1)),
        "att2_daily_net_cv": float(daily_net.std(ddof=1) / daily_net.mean()),
        "att2_daily_net_min_kwh": float(daily_net.min()),
        "att2_daily_net_max_kwh": float(daily_net.max()),
        "att1_price_mean": float(att1.price.values.mean()),
        "att4_price_mean": float(att4.price.mean()),
        "corr_daily_load_vs_daily_price": float(np.corrcoef(daily_load, daily_price)[0, 1]),
    }


def main() -> int:
    """执行全部分析并写出 ``Q1_analysis.json``。

    Returns:
        进程退出码，``0`` 表示成功。
    """
    diag = json.loads(DIAG.read_text(encoding="utf-8"))
    series = load_series()
    att1 = io.load_attachment_1()
    price = np.asarray(att1.price.values, dtype=float)
    load_e = io.interval_power_to_energy(np.asarray(att1.load.values, dtype=float))
    pv_e = io.interval_power_to_energy(np.asarray(att1.pv_forecast.values, dtype=float))
    net = load_e - pv_e

    payload: dict = {
        "source_files": {"diagnostics": str(DIAG), "timeseries": str(CSV),
                         "result": str(RESULT)},
        "headline_metrics": {
            k: diag["metrics"][k] for k in (
                "total_purchase_kwh", "total_cost_yuan", "mean_purchase_price_yuan_per_kwh",
                "load_total_kwh", "pv_total_kwh", "net_load_total_kwh",
                "charge_total_kwh", "discharge_total_kwh", "charge_loss_kwh",
                "curtail_total_kwh", "curtail_slots",
                "soc_start_kwh", "soc_end_kwh", "soc_min_kwh", "soc_max_kwh",
                "baseline_B0_yuan", "storage_net_benefit_yuan", "storage_net_benefit_ratio",
                "purchase_peak_kw", "zero_purchase_slots", "charge_peak_kw", "discharge_peak_kw",
                "block_labels", "block_charge_kwh", "block_discharge_kwh",
            )
        },
        "price_and_regime": price_and_regime(series),
        "storage_events": storage_events(series),
        "energy_account": energy_account(series),
        "baseline_comparison": baseline_comparison(series),
        "arbitrage_account": arbitrage_account(series),
        "attachment1_representativeness": attachment1_representativeness(),
        "hourly_price_profile": {
            f"{h:02d}:00-{h + 1:02d}:00": float(price[6 * h:6 * h + 6].mean())
            for h in range(24)
        },
        "block_detail": {
            io.half_hour_block_labels()[b - 1]: {
                "charge_kwh": float(series["充电量(kWh)"][24 * (b - 1):24 * b].sum()),
                "discharge_kwh": float(series["放电量(kWh)"][24 * (b - 1):24 * b].sum()),
                "price_mean": float(price[24 * (b - 1):24 * b].mean()),
                "purchase_kwh": float(series["计划购电量(kWh)"][24 * (b - 1):24 * b].sum()),
            }
            for b in range(1, 7)
        },
        "sanity_checks": diag["sanity_checks"],
        "table1": diag["table1"],
        "table2": diag["table2"],
    }

    _log("灵敏度：储能效率 η ∈ {0.85, 0.90, 0.95}")
    payload["sensitivity_efficiency"] = [
        solve_variant(price, net, pv_e, eta, True) for eta in (0.85, 0.90, 0.95)
    ]
    _log("对照：关闭弃光松弛项（g_t ≡ 0）")
    payload["control_no_curtail"] = solve_variant(price, net, pv_e, 0.90, False)

    ANALYSIS.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(f"分析证据写出：{ANALYSIS}")

    acc = payload["energy_account"]
    _log(f"平衡账：供给 {acc['supply_total_kwh']:,.4f} vs 需求 {acc['demand_total_kwh']:,.4f}，"
         f"残差 {acc['account_residual_kwh']:.3e} kWh")
    _log(f"自给率 {acc['self_sufficiency_ratio']:.4%}；光伏消纳率 {acc['pv_consumption_ratio']:.4%}")
    for item in payload["sensitivity_efficiency"]:
        _log(f"  η={item['eta']:.2f} → 费用 {item['objective_yuan']:,.4f} 元，"
             f"充电 {item['charge_kwh']:,.2f} kWh，弃光 {item['curtail_kwh']:.6f} kWh")
    ctrl = payload["control_no_curtail"]
    _log(f"  无弃光松弛 → 费用 {ctrl['objective_yuan']:,.4f} 元（差 "
         f"{ctrl['objective_yuan'] - payload['sensitivity_efficiency'][1]['objective_yuan']:.3e} 元）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
