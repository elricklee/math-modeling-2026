"""Generate all paper figures listed in paper/问题*_论文框架.md.

Output: pictures/问题1..问题4/图N_*.png, numbered to match the frameworks.
Chinese labels use Microsoft YaHei (Windows default CJK font).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.CUMCM2026_C import io_attachments as io, paths
from src.CUMCM2026_C.dispatch import history_prediction
from src.CUMCM2026_C.solve_problem2 import solve_day_solution
from src.CUMCM2026_C.sp_plan import build_inputs
from src.CUMCM2026_C.sp_rolling import build_pv_release_errors

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei"]
plt.rcParams["axes.unicode_minus"] = False
plt.rcParams["figure.dpi"] = 150

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "pictures"
for q in ("问题1", "问题2", "问题3", "问题4"):
    (OUT / q).mkdir(parents=True, exist_ok=True)

HOURS = np.arange(144) / 6.0
DT = paths.INTERVAL_MINUTES / 60.0
C_BLUE, C_ORANGE, C_GREEN, C_RED, C_GRAY = "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#7f7f7f"


def save(fig, name):
    path = OUT / name
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
    print("saved", path)


def load_records(fname):
    return json.loads((paths.PROCESSED_DIR / fname).read_text(encoding="utf-8"))["daily"]


# ---------------- 问题1 ----------------
def q1_figures():
    a1, a2, a3, a4 = io.load_all()
    price = np.asarray(a1.price.values, float)
    load = np.asarray(a1.load.values, float)
    pv = np.asarray(a1.pv_forecast.values, float)
    _, arr = solve_day_solution(a2.dates[0], price, load, pv)
    p, x, y, soc = arr["purchase"], arr["charge"], arr["discharge"], arr["soc"]

    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(HOURS, load - pv, color=C_GRAY, lw=1.2, label="净负荷 (load−PV)")
    ax.step(HOURS, p / DT, where="mid", color=C_BLUE, lw=1.4, label="计划购电功率")
    ax.set_xlabel("时刻 (h)")
    ax.set_ylabel("功率 (kW)")
    ax2 = ax.twinx()
    ax2.plot(HOURS, price, color=C_ORANGE, lw=1.2, alpha=0.85, label="电价")
    ax2.set_ylabel("电价 (元/kWh)")
    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=9)
    ax.set_title("问题1 图1  典型日净负荷、计划购电与电价")
    save(fig, "问题1/图1_典型日净负荷购电计划与电价.png")

    fig, ax = plt.subplots(figsize=(9, 4))
    ax.plot(HOURS, soc[1:], color=C_BLUE, lw=1.5)
    ax.axhline(1200, color=C_RED, ls="--", lw=1, label="下限 1200")
    ax.axhline(10800, color=C_RED, ls="--", lw=1, label="上限 10800")
    ax.axhline(6000, color=C_GREEN, ls=":", lw=1.2, label="首末 6000")
    ax.set_xlabel("时刻 (h)"); ax.set_ylabel("储电量 (kWh)")
    ax.legend(fontsize=9); ax.set_title("问题1 图2  典型日 SOC 轨迹")
    save(fig, "问题1/图2_典型日SOC轨迹.png")

    fig, ax = plt.subplots(figsize=(9, 4.5))
    w = 10 / 60
    ax.bar(HOURS - w / 2, x / DT, width=w * 0.9, color=C_GREEN, label="充电功率")
    ax.bar(HOURS + w / 2, y / DT, width=w * 0.9, color=C_ORANGE, label="放电功率")
    ax.set_xlabel("时刻 (h)"); ax.set_ylabel("功率 (kW)")
    ax2 = ax.twinx()
    ax2.plot(HOURS, price, color=C_RED, lw=1.2, alpha=0.8, label="电价")
    ax2.set_ylabel("电价 (元/kWh)")
    h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=9)
    ax.set_title("问题1 图3  分时充放电与电价对比")
    save(fig, "问题1/图3_分时充放电与电价.png")


# ---------------- 问题2 ----------------
def q2_figures():
    a1, a2, a3, a4 = io.load_all()
    recs = load_records("problem2_plan3_final.json")

    fig, (axa, axb) = plt.subplots(2, 1, figsize=(10, 6), sharex=True)
    days = np.arange(len(recs))
    plan = np.array([r["plan_cost_yuan"] for r in recs]) / 1e4
    emg = np.array([r["emergency_cost_yuan"] for r in recs]) / 1e4
    axa.bar(days, plan, color=C_BLUE, label="计划购电费")
    axa.bar(days, emg, bottom=plan, color=C_RED, label="紧急购电费")
    axa.set_ylabel("费用 (万元)"); axa.legend(fontsize=9)
    axa.set_title("问题2 图1  全年逐日费用分解与紧急购电")
    emgk = np.array([r["emergency_kwh"] for r in recs])
    axb.bar(days, emgk, color=C_GRAY)
    axb.set_xlabel("天数 (2月1日起)"); axb.set_ylabel("紧急购电 (kWh)")
    save(fig, "问题2/图1_全年逐日费用与紧急购电.png")

    # 图2: 再现 day-200 的 K=200 情景带（与正式运行同随机种子）
    inputs = build_inputs()
    lm, pv_point = inputs["lm"], inputs["pv_point"]
    err_l, err_p = inputs["err_load"], inputs["err_pv"]
    i = 200
    rng = np.random.default_rng(1_000_003 + i)
    past = list(range(31, i))
    pick = rng.choice(len(past), size=200, replace=True)
    sl = err_l[[past[j] for j in pick]]
    spv = err_p[[past[j] for j in pick]]
    net_scen = ((lm[i] + sl) - np.maximum(pv_point[i] + spv, 0)) / 6.0
    rec = next(r for r in recs if r["date"] == a2.dates[i].isoformat())
    actual_net = (np.asarray(a2.load[i]) - np.asarray(a2.pv_actual[i])) / 6.0
    lo, med, hi = np.percentile(net_scen, [5, 50, 95], axis=0)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.fill_between(HOURS, lo, hi, color=C_BLUE, alpha=0.2, label="情景 5–95 分位带 (K=200)")
    ax.plot(HOURS, med, color=C_BLUE, lw=1.2, label="情景中位数")
    ax.plot(HOURS, actual_net, color=C_RED, lw=1.4, label="实际净需求")
    ax.step(HOURS, np.asarray(rec["plan_by_interval_kwh"]), where="mid",
            color=C_GREEN, lw=1.3, label="计划购电")
    ax.set_xlabel("时刻 (h)"); ax.set_ylabel("电量 (kWh/10min)")
    ax.legend(fontsize=9); ax.set_title(f"问题2 图2  情景带与实际净需求（{a2.dates[i]}）")
    save(fig, "问题2/图2_情景带与实际净需求.png")

    plan_all = np.concatenate([r["plan_by_interval_kwh"] for r in recs])
    net_all = np.concatenate([
        (np.asarray(a2.load[k]) - np.asarray(a2.pv_actual[k])) / 6.0
        for k in range(31, 365)])
    fig, ax = plt.subplots(figsize=(5.5, 5.5))
    ax.scatter(net_all, plan_all, s=2, alpha=0.06, color=C_BLUE, edgecolors="none")
    lim = [0, max(net_all.max(), plan_all.max()) * 1.02]
    ax.plot(lim, lim, color=C_RED, lw=1, ls="--", label="y=x")
    ax.set_xlabel("实际净需求 (kWh/10min)"); ax.set_ylabel("计划购电 (kWh/10min)")
    ax.legend(); ax.set_title("问题2 图3  计划 vs 实际净需求（全年 48096 点）")
    save(fig, "问题2/图3_计划与实际净需求散点.png")


# ---------------- 问题3 ----------------
def q3_figures():
    a1, a2, a3, a4 = io.load_all()
    recs = load_records("problem3_sp_strict.json")

    i = 200
    rec = next(r for r in recs if r["date"] == a2.dates[i].isoformat())
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.step(HOURS, rec["plan_by_interval_kwh"], where="mid", color=C_BLUE, lw=1.3, label="0:00 计划购电")
    ax.step(HOURS, rec["purchase_by_interval_kwh"], where="mid", color=C_ORANGE, lw=1.3,
            label="调整后购电")
    ax.fill_between(HOURS, rec["plan_by_interval_kwh"], rec["purchase_by_interval_kwh"],
                    step="mid", color=C_ORANGE, alpha=0.25)
    for h in (6, 12, 18):
        ax.axvline(h, color=C_GRAY, ls=":", lw=1)
    ax.set_xlabel("时刻 (h)"); ax.set_ylabel("电量 (kWh/10min)")
    ax.legend(fontsize=9); ax.set_title(f"问题3 图1  计划 vs 调整后购电（{a2.dates[i]}，严格口径）")
    save(fig, "问题3/图1_计划与调整购电对比.png")

    fig, ax = plt.subplots(figsize=(10, 4.5))
    days = np.arange(len(recs))
    plan = np.array([r["plan_cost_yuan"] for r in recs]) / 1e4
    adj = np.array([r["adjustment_cost_yuan"] for r in recs]) / 1e4
    emg = np.array([r["emergency_cost_yuan"] for r in recs]) / 1e4
    ax.bar(days, plan, color=C_BLUE, label="计划费")
    ax.bar(days, adj, bottom=plan, color=C_ORANGE, label="调整费")
    ax.bar(days, emg, bottom=plan + adj, color=C_RED, label="紧急费")
    ax.set_xlabel("天数 (2月1日起)"); ax.set_ylabel("费用 (万元)")
    ax.legend(fontsize=9); ax.set_title("问题3 图2  全年逐日费用三分解")
    save(fig, "问题3/图2_全年逐日费用三分解.png")

    pv_err = build_pv_release_errors()
    pv = np.asarray([np.asarray(r, float) for r in a2.pv_actual])
    data, labels = [], []
    for h in (0, 6, 12, 18):
        e = np.abs(pv_err[h][31:])
        mask = pv[31:, 6 * h:] > 0
        data.append(e[mask])
        labels.append(f"{h}:00 发布")
    fig, ax = plt.subplots(figsize=(7, 4.5))
    bp = ax.boxplot(data, tick_labels=labels, showfliers=False, patch_artist=True)
    for b in bp["boxes"]:
        b.set_facecolor(C_BLUE); b.set_alpha(0.5)
    ax.set_ylabel("|预报误差| (kW)")
    ax.set_title("问题3 图3  分发布时刻的光伏预报误差分布（白天时段）")
    save(fig, "问题3/图3_分时刻预报误差分布.png")


# ---------------- 问题4 ----------------
def q4_figures():
    a1, a2, a3, a4 = io.load_all()
    price = np.asarray([np.asarray(r, float) for r in a4.price])
    recs = load_records("problem4_2_sp.json")

    fig, ax = plt.subplots(figsize=(9, 4.5))
    vals = price.ravel()
    ax.hist(vals, bins=120, color=C_BLUE, alpha=0.75)
    ax.axvline(0.05, color=C_RED, ls="--", lw=1.2, label="0.05 元/kWh")
    ax.annotate(f"9 个极端低价样本 (<0.05)\n最低 {vals.min():.4f}",
                xy=(0.05, ax.get_ylim()[1] * 0.9), xytext=(0.25, ax.get_ylim()[1] * 0.85),
                arrowprops=dict(arrowstyle="->", color=C_RED), color=C_RED, fontsize=9)
    ax.set_xlabel("电价 (元/kWh)"); ax.set_ylabel("频数")
    ax.legend(); ax.set_title("问题4 图1  附件4 电价分布与极端样本")
    save(fig, "问题4/图1_电价分布与极端样本.png")

    dmean = price.mean(axis=1)
    hi_i, lo_i = int(np.argmax(dmean[31:])), int(np.argmin(dmean[31:]))
    center = np.zeros_like(price)
    for i in range(len(a4.dates)):
        center[i] = history_prediction(a4.price, i, a4.dates, 0.5, 28, 1.0)
    fig, axes = plt.subplots(2, 1, figsize=(9, 7))
    for ax, i, tag in ((axes[0], hi_i, "最高价日"), (axes[1], lo_i, "最低价日")):
        rec = next(r for r in recs if r["date"] == a4.dates[i].isoformat())
        ax.plot(HOURS, price[i], color=C_RED, lw=1.3, label="实际电价")
        ax.plot(HOURS, center[i], color=C_GRAY, lw=1.2, ls="--", label="因果预测（28天中位数）")
        ax.set_xlabel("时刻 (h)"); ax.set_ylabel("电价 (元/kWh)")
        ax2 = ax.twinx()
        ax2.step(HOURS, rec["plan_by_interval_kwh"], where="mid", color=C_BLUE, lw=1.1,
                 label="计划购电")
        ax2.set_ylabel("计划购电 (kWh/10min)")
        h1, l1 = ax.get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels()
        ax.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8)
        ax.set_title(f"问题4 图2  {tag} {a4.dates[i]}（日均价 {price[i].mean():.3f}）")
    fig.tight_layout()
    save(fig, "问题4/图2_高低价日价格与购电时序.png")

    inputs = build_inputs()
    _, pcenter, perr = None, None, None
    from src.CUMCM2026_C.sp_volatile import build_price_history
    _, pcenter, perr = build_price_history()
    el = np.abs(inputs["err_load"][31:]).mean(axis=1)
    ep = np.abs(perr[31:]).mean(axis=1)
    r = np.corrcoef(el, ep)[0, 1]
    fig, ax = plt.subplots(figsize=(5.5, 5))
    ax.scatter(el, ep, s=6, alpha=0.4, color=C_BLUE, edgecolors="none")
    ax.set_xlabel("日平均 |负载预测误差| (kW)")
    ax.set_ylabel("日平均 |价格预测误差| (元/kWh)")
    ax.set_title(f"问题4 图3  负载与价格误差的日级联合（r = {r:.3f}）")
    save(fig, "问题4/图3_负载价格误差联合散点.png")


def pred_actual_figures():
    """预测 vs 实际对比图：Q2 两张、Q3 两张、Q4 三张（编号接续各问已有图）。"""
    from src.CUMCM2026_C.dispatch import forecast_vector
    from src.CUMCM2026_C.sp_volatile import build_price_history

    a1, a2, a3, a4 = io.load_all()
    inputs = build_inputs()
    lm, ls = inputs["lm"], inputs["ls"]
    pm, ps = inputs["pm"], inputs["ps"]
    pv_point = inputs["pv_point"]
    i = 200
    day = a2.dates[i]
    load = np.asarray(a2.load[i], float)
    pv = np.asarray(a2.pv_actual[i], float)
    weekday_cn = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][day.weekday()]
    date_tag = f"{day} {weekday_cn}"

    def band(ax, center, lo, hi, c, label_center):
        ax.fill_between(HOURS, lo, hi, color=c, alpha=0.18, label="95% 置信带")
        ax.plot(HOURS, center, color=c, lw=1.4, label=label_center)

    # ---- Q2 图4: 负载 ----
    fig, ax = plt.subplots(figsize=(9, 4.2))
    band(ax, lm[i], lm[i] - 1.96 * ls[i], lm[i] + 1.96 * ls[i], C_BLUE, "SARIMA 预测（中位数）")
    ax.plot(HOURS, load, color=C_RED, lw=1.2, alpha=0.9, label="实际负载")
    ax.set_xlabel("时刻 (h)"); ax.set_ylabel("负载 (kW)")
    ax.legend(fontsize=9); ax.set_title(f"问题2 图4  负载预测与实际对比（{date_tag}）")
    save(fig, "问题2/图4_负载预测与实际对比.png")

    # ---- Q2 图5: 光伏 ----
    lo = np.maximum(pm[i] - 1.96 * ps[i], 0) ** 2
    hi = (pm[i] + 1.96 * ps[i]) ** 2
    fig, ax = plt.subplots(figsize=(9, 4.2))
    band(ax, pv_point[i], lo, hi, C_GREEN, "SARIMA 预测（sqrt 尺度反变换）")
    ax.plot(HOURS, pv, color=C_RED, lw=1.2, alpha=0.9, label="实际光伏")
    ax.set_xlabel("时刻 (h)"); ax.set_ylabel("光伏功率 (kW)")
    ax.legend(fontsize=9); ax.set_title(f"问题2 图5  光伏预测与实际对比（{date_tag}）")
    save(fig, "问题2/图5_光伏预测与实际对比.png")

    # ---- Q3 图4: 负载（严格口径，与问题2 同源预测器）----
    fig, ax = plt.subplots(figsize=(9, 4.2))
    band(ax, lm[i], lm[i] - 1.96 * ls[i], lm[i] + 1.96 * ls[i], C_BLUE, "SARIMA 预测（中位数）")
    ax.plot(HOURS, load, color=C_RED, lw=1.2, alpha=0.9, label="实际负载")
    ax.set_xlabel("时刻 (h)"); ax.set_ylabel("负载 (kW)")
    ax.legend(fontsize=9)
    ax.set_title(f"问题3 图4  负载预测与实际对比·严格口径（{date_tag}）")
    save(fig, "问题3/图4_负载预测与实际对比.png")

    # ---- Q3 图5: 滚动采用的预报（拼合曲线）vs 实际，仅两条线 ----
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.plot(HOURS, pv, color=C_RED, lw=1.4, label="实际光伏")
    composite = np.full(144, np.nan)
    for h in (0, 6, 12, 18):
        fv = forecast_vector(a3, day, h, scale=1.0)
        s0, s1 = 6 * h, min(6 * h + 36, 144)      # 该发布实际覆盖的规划段
        composite[s0:s1] = fv[s0:s1]
    m = np.isfinite(composite)
    ax.plot(HOURS[m], composite[m], color=C_BLUE, lw=1.8,
            label="滚动采用的预测（0/6/12/18 发布各管 6 小时）")
    for h in (6, 12, 18):
        ax.axvline(h, color=C_GRAY, ls=":", lw=1)
    ax.set_xlabel("时刻 (h)"); ax.set_ylabel("光伏功率 (kW)")
    ax.legend(fontsize=9)
    ax.set_title(f"问题3 图5  滚动采用的光伏预测与实际（{date_tag}）")
    save(fig, "问题3/图5_光伏预报与实际对比.png")

    # ---- Q4 图4: 负载 ----
    fig, ax = plt.subplots(figsize=(9, 4.2))
    band(ax, lm[i], lm[i] - 1.96 * ls[i], lm[i] + 1.96 * ls[i], C_BLUE, "SARIMA 预测（中位数）")
    ax.plot(HOURS, load, color=C_RED, lw=1.2, alpha=0.9, label="实际负载")
    ax.set_xlabel("时刻 (h)"); ax.set_ylabel("负载 (kW)")
    ax.legend(fontsize=9); ax.set_title(f"问题4 图4  负载预测与实际对比（{date_tag}）")
    save(fig, "问题4/图4_负载预测与实际对比.png")

    # ---- Q4 图5: 光伏（两种信息源）----
    fig, ax = plt.subplots(figsize=(9, 4.4))
    ax.plot(HOURS, pv, color=C_RED, lw=1.4, label="实际光伏")
    ax.plot(HOURS, pv_point[i], color=C_GREEN, lw=1.2, ls="--", label="自建 SARIMA（4-2 使用）")
    fv0 = forecast_vector(a3, day, 0, scale=1.0)
    m = np.isfinite(fv0)
    ax.plot(HOURS[m], fv0[m], color=C_BLUE, lw=1.2, ls="--", label="附件3 0:00 发布（4-3 使用）")
    ax.set_xlabel("时刻 (h)"); ax.set_ylabel("光伏功率 (kW)")
    ax.legend(fontsize=9); ax.set_title(f"问题4 图5  光伏两种信息源的预测与实际（{date_tag}）")
    save(fig, "问题4/图5_光伏预测与实际对比.png")

    # ---- Q4 图6: 电价 ----
    _, pcenter, _ = build_price_history()
    price_i = np.asarray(a4.price[i], float)
    fig, ax = plt.subplots(figsize=(9, 4.2))
    ax.plot(HOURS, price_i, color=C_RED, lw=1.3, label="实际电价（附件4）")
    ax.plot(HOURS, pcenter[i], color=C_GRAY, lw=1.4, ls="--", label="因果预测（28 天同星期几中位数）")
    ax.set_xlabel("时刻 (h)"); ax.set_ylabel("电价 (元/kWh)")
    ax.legend(fontsize=9)
    ax.set_title(f"问题4 图6  电价预测与实际对比（{date_tag}）")
    save(fig, "问题4/图6_电价预测与实际对比.png")


def main():
    q1_figures()
    q2_figures()
    q3_figures()
    q4_figures()
    pred_actual_figures()
    print("all figures done ->", OUT)


if __name__ == "__main__":
    raise SystemExit(main())
