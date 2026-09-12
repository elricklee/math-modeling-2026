r"""只读探针：核对问题二 (A) 附件 3 映射覆盖 与 (B) 计划阶段 LP 的结构事实。

用途
====

回答"计划阶段目标里的 :math:`\lambda\sum|\theta-q|` 到底起什么作用"这类质疑，
给出**可复跑**的实测数字：

* (A) ``release_hourly_blocks(release_hour=0)`` 在全部 334 天是否零缺口；
  以及三种统计口径下的 MAE（新映射 371.2208 / 旧映射 448.3124 / 仅覆盖 138 时段 387.3608）。
* (B) 计划阶段 LP 的三条事实：``q`` 被平衡等式钉住（``max|q-need|=0``）、
  ``m = p = 0``（罚项对最优值无贡献：把 λ 置 0 只差 4.6e-07 元）、
  放开 ``q ≥ 0`` 会给出虚假售电收益（2025-06-21 单日目标被压到 2 334.61 元）。

约定：本探针**故意**导入流水线模块（``Q2_analysis`` / ``Q2_solve_plan``）以复现其
行为，因此它**不是**独立审计；独立审计见 ``Q2_audit``（零导入被复核代码）。

运行（仓库根目录）::

    $env:PYTHONIOENCODING="utf-8"
    .venv\Scripts\python.exe CUMCM2026_C\common\diagnostics\Q2_planstage_probe.py
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import csr_matrix

ROOT = r"D:\MathModeling\math-modeling-2026"
sys.path.insert(0, ROOT)

from CUMCM2026_C.common.code import io_attachments as io  # noqa: E402
from CUMCM2026_C.Q2 import Q2_analysis as qa  # noqa: E402
from CUMCM2026_C.Q2 import Q2_solve_plan as sp  # noqa: E402

T = 144
CAP = 5000.0 * 10.0 / 60.0
ETA = 0.9
S_LO, S_HI, S_INIT = 1200.0, 10800.0, 6000.0
MULT = 5.0

print("=" * 78)
print("A) 映射覆盖：release_hourly_blocks(release_hour=0) 全 334 天")
print("=" * 78)
att3 = io.load_attachment_3()
data = sp.load_data()
allday = []
bad = 0
for d in data["dates"]:
    hourly, cov, unc = qa.release_hourly_blocks(att3, d, 0, d)
    allday.append(hourly)
    if cov != list(range(24)) or unc:
        bad += 1
print(f"334 天中 covered != [0..23] 的天数：{bad}")
h0 = allday[0]
raw0 = np.asarray(att3.forecast[att3.row_index(date(2025, 2, 1), 0)], dtype=float)
print(f"2025-02-01：hourly[0]={h0[0]:.4f}  raw[0]={raw0[0]:.4f}（应相等）")
print(f"2025-02-01：hourly[6]={h0[6]:.4f}  raw[6]={raw0[6]:.4f}（应相等，6:00-7:00）")
print(f"2025-02-01：hourly[23]={h0[23]:.4f} raw[23]={raw0[23]:.4f}（应相等，23:00-24:00）")

pv_actual = data["pv_kw"]
fc_new = np.stack([np.repeat(h, 6) for h in allday])
# 旧映射（r+k，即块 1..24 → 当天 h=1..23，h=0 无列按 0 计入）
fc_old = np.zeros_like(fc_new)
for i, d in enumerate(data["dates"]):
    vals = np.asarray(att3.forecast[att3.row_index(d, 0)], dtype=float)
    hourly = np.zeros(24)
    for k in range(1, 25):
        abs_block = k                  # 旧实现：release_hour + k（r=0 → 块 1..24）
        if d + timedelta(days=abs_block // 24) != d:
            continue                   # 只有 k=24 会被剔除（落到次日）
        hourly[abs_block % 24] = vals[k - 1]
    fc_old[i] = np.repeat(hourly, 6)
mae_new = float(np.abs(fc_new - pv_actual).mean())
mae_old = float(np.abs(fc_old - pv_actual).mean())
print(f"全天 144 时段 MAE：新映射（f_d[k]→块 k-1，零缺口）= {mae_new:.4f} kW")
print(f"                   旧映射（块 1..24，hour 0 计 0）      = {mae_old:.4f} kW")
print(f"                   仅被覆盖 138 时段（剔除 hour 0）    = "
      f"{float(np.abs(fc_new - pv_actual)[:, 6:].mean()):.4f} kW")

print()
print("=" * 78)
print("B) 计划阶段 LP 的结构事实（复制 solve_plan_stage 的等式/目标，只读复算）")
print("=" * 78)


def build_plan_lp(net, price, lam_on=True, q_floor=0.0):
    n = 6 * T
    i_x, i_y, i_q, i_d, i_m, i_p = 0, T, 2 * T, 3 * T, 4 * T, 5 * T
    lam = MULT * float(price.max())
    a_energy = np.zeros((T, n))
    a_energy[:, i_q:i_q + T] = np.eye(T)
    a_energy[:, i_d:i_d + T] = -np.eye(T)
    a_energy[:, i_x:i_x + T] = -np.eye(T)
    a_energy[:, i_y:i_y + T] = np.eye(T)
    a_gap = np.zeros((T, n))
    a_gap[:, i_x:i_x + T] = np.eye(T)
    a_gap[:, i_y:i_y + T] = -np.eye(T)
    a_gap[:, i_d:i_d + T] = np.eye(T)
    a_gap[:, i_q:i_q + T] = -np.eye(T)
    a_gap[:, i_m:i_m + T] = -np.eye(T)
    a_gap[:, i_p:i_p + T] = np.eye(T)
    a_final = np.zeros((1, n))
    a_final[0, i_x:i_x + T] = ETA
    a_final[0, i_y:i_y + T] = -1.0 / ETA
    a_eq = csr_matrix(np.vstack([a_energy, a_gap, a_final]))
    b_eq = np.concatenate([net, -net, [0.0]])
    soc = qa._soc_inequalities()[0].toarray()
    a_ub = csr_matrix(np.hstack([soc, np.zeros((2 * T, n - 2 * T))]))
    b_ub = qa._soc_inequalities()[1]
    c = np.zeros(n)
    c[i_q:i_q + T] = price
    c[i_m:i_m + T] = lam if lam_on else 0.0
    c[i_p:i_p + T] = lam if lam_on else 0.0
    c[i_d:i_d + T] = price * 1e-9
    bounds = ([(0.0, CAP)] * T + [(0.0, CAP)] * T
              + [(q_floor, None)] * T + [(0.0, None)] * T
              + [(0.0, None)] * T + [(0.0, None)] * T)
    res = linprog(c, A_ub=a_ub, b_ub=b_ub, A_eq=a_eq, b_eq=b_eq,
                  bounds=bounds, method="highs")
    return res, (i_x, i_y, i_q, i_d, i_m, i_p)


for di in (0, data["dates"].index(date(2025, 6, 21))):
    d = data["dates"][di]
    net = data["net_e"][di]
    price = data["price_row"]
    res, idx = build_plan_lp(net, price, lam_on=True)
    i_x, i_y, i_q, i_d, i_m, i_p = idx
    z = res.x
    q, x, y, dd = z[i_q:i_q + T], z[i_x:i_x + T], z[i_y:i_y + T], z[i_d:i_d + T]
    need = net + x - y + dd
    print(f"--- {d}（预报净负荷合计 {net.sum():,.2f} kWh）---")
    print(f"  λ 项在用时：目标 {res.fun:,.6f} 元；纯购电费 Σc·q = {float((price * q).sum()):,.6f} 元")
    print(f"  max|q - need| = {np.abs(q - need).max():.3e}；max(m) = {z[i_m:i_m + T].max():.3e}；"
          f"max(p) = {z[i_p:i_p + T].max():.3e}")
    res0, _ = build_plan_lp(net, price, lam_on=False)
    print(f"  把 λ 置 0（罚项失效）：目标 {res0.fun:,.6f} 元；"
          f"与 λ>0 的目标差 {abs(res0.fun - res.fun):.3e} 元；"
          f"max|x−x0| = {np.abs(res0.x[i_x:i_x + T] - x).max():.3e}")
    resf, _ = build_plan_lp(net, price, lam_on=True, q_floor=-np.inf)
    zf = resf.x
    qf = zf[i_q:i_q + T]
    print(f"  放开 q ≥ 0（允许 q<0）：目标 {resf.fun:,.6f} 元"
          f"（比正确模型低 {res.fun - resf.fun:,.2f} 元 = 虚假售电收益）；"
          f"min(q) = {qf.min():,.2f} kWh；负值时段数 = {int((qf < -1e-9).sum())}/{T}")
