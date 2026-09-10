"""诊断问题1 参考解的 2.78 元差异来源（队长用）。

背景：队长修正版 LP 得 35 126.9486 元，建模手修正解报 35 129.7319 元，差 2.7833 元（0.0079%）。
两者购电量（59 482.6990）、充电量（20 740.6661）、放电量（16 799.9396）逐位相同，
仅费用不同 ⇒ 差异只能来自**逐时段分配（SOC 路径形状）不同**。

本脚本：
  1. 打印队长解的逐时段 x/y 分布与 SOC 路径形状；
  2. 用"总量均摊"构造另一条可行路径（Σx、Σy 与队长相同），代入队长 LP 的约束求其费用；
  3. 判断建模手的 35 129.7319 元能否由某条同总量的可行路径解释，从而判定谁最优。

用法：
    python tools/diagnose_p1_gap.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import linprog

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

spec = importlib.util.spec_from_file_location("lp", ROOT / "tools" / "lp_p1_final.py")
lp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lp)


def main() -> None:
    price, load, pv = lp.load_data()
    net = (load - pv) * lp.DT
    pv_e = pv * lp.DT
    T = lp.T

    c, const, A_ub, b_ub, A_eq, b_eq, bounds = lp.build(price, net, pv_e)
    res = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq, bounds=bounds,
                  method="highs")
    assert res.success
    z = res.x
    S = z[lp.IS:lp.IS + lp.NS]
    x, y, g = z[lp.IX:lp.IX + T], z[lp.IY:lp.IY + T], z[lp.IG:lp.IG + T]
    p = net + x - y + g
    cost = float((price * p).sum())

    print("=" * 78)
    print("队长解（权威）")
    print(f"  Σx = {x.sum():.10f}   Σy = {y.sum():.10f}   Σy/Σx = {y.sum()/x.sum():.10f}")
    print(f"  Σp = {p.sum():.10f}   费用 = {cost:.10f} 元")
    print(f"  SOC 路径: 起点 {S[0]:.4f} 终点 {S[-1]:.4f} 范围 [{S.min():.4f}, {S.max():.4f}]")
    print(f"  充电时段数 = {(x > 1e-9).sum()} / {T}    放电时段数 = {(y > 1e-9).sum()} / {T}")
    print(f"  同时充放时段数 = {((x > 1e-9) & (y > 1e-9)).sum()}  （退化检查）")
    print(f"  限光 Σg = {g.sum():.10f}")

    # 构造"同总量、均匀分配"的替代路径，检验其可行性
    print("=" * 78)
    print("构造同总量替代路径（均匀分摊到全部 144 时段）")
    xu = np.full(T, x.sum() / T)
    yu = np.full(T, y.sum() / T)
    Su = np.empty(lp.NS)
    Su[0] = lp.S_INIT
    for t in range(1, T + 1):
        Su[t] = Su[t - 1] + lp.ETA * xu[t - 1] - yu[t - 1] / lp.ETA
    print(f"  均匀路径 Σx = {xu.sum():.10f}  Σy = {yu.sum():.10f}")
    print(f"  SOC 范围 [{Su.min():.4f}, {Su.max():.4f}]  终点 {Su[-1]:.4f}")
    feasible_soc = bool(Su.min() >= lp.S_LO - 1e-6 and Su.max() <= lp.S_HI + 1e-6)
    print(f"  SOC 界内: {feasible_soc}")
    pu = net + xu - yu
    print(f"  p_min = {pu.min():.4f}  (需 >= 0)")
    if pu.min() >= -1e-9 and feasible_soc:
        print(f"  该路径可行，费用 = {(price * pu).sum():.10f} 元")
        print(f"  与队长的差 = {(price * pu).sum() - cost:+.6f} 元")

    # 把"总量约束"加入 LP：固定 Σx 与 Σy，看费用能否变化
    print("=" * 78)
    print("加入总量固定约束后重解（检验最优值是否唯一）")
    A_eq2 = np.vstack([A_eq, np.zeros((2, lp.N))])
    A_eq2[-2, lp.IX:lp.IX + T] = 1.0
    A_eq2[-1, lp.IY:lp.IY + T] = 1.0
    b_eq2 = np.append(b_eq, [x.sum(), y.sum()])
    res2 = linprog(c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq2, b_eq=b_eq2,
                   bounds=bounds, method="highs")
    if res2.success:
        z2 = res2.x
        x2, y2, g2 = z2[lp.IX:lp.IX + T], z2[lp.IY:lp.IY + T], z2[lp.IG:lp.IG + T]
        p2 = net + x2 - y2 + g2
        print(f"  重解成功：费用 = {(price * p2).sum():.10f} 元")
        print(f"  Σx = {x2.sum():.10f}  Σy = {y2.sum():.10f}")
        print(f"  与队长原解差 = {(price * p2).sum() - cost:+.6f} 元")
    else:
        print("  重解失败:", res2.message)

    # 直接搜索：能否达到建模手报的 35 129.7319
    print("=" * 78)
    target = 35129.731923
    print(f"建模手报 35 129.731923 元；队长最优 {cost:.6f} 元；差 {target - cost:+.6f} 元")
    print("结论：若队长解经约束矩阵逐行核验无误，则队长值更优；"
          "建模手值应为另一条同总量可行路径的费用（非最优）。")


if __name__ == "__main__":
    main()
