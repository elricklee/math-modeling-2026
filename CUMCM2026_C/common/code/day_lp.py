r"""微网日前调度线性规划的**单一事实来源**（问题 1/2/3/4 共用）。

本模块把"多日微网购电—储能调度"的线性规划**矩阵构造**集中到一处，
使四个问题只在**数据入口**与**费用口径**上不同，约束构造完全一致
（问题二契约 §7 自检 12：

    "问题一可视为本问在负载与光伏恒为附件 1 典型曲线时的特例，
     两者的模型代码应共享同一套约束构造，差异只在数据入口。"

模型（与 ``问题一模型的建立.md`` 的符号体系一致，单位 kWh）
----------------------------------------------------------

变量（对第 :math:`d` 天、时段 :math:`t = 1..144`）：

* :math:`q_{d,t}` —— 计划/实际购电量（**决策量**；在本队口径下计划量 = 实际量，
  故只有一个变量，见 :mod:`CUMCM2026_C.Q2.Q2_solve_plan` 的说明）
* :math:`x_{d,t}` —— 储能充电量（入网侧，未计效率）
* :math:`y_{d,t}` —— 储能放电量（出网侧，已计效率）
* :math:`S_{d,t}` —— 第 :math:`t` 时段末储电量（另含 :math:`S_{d,0}`）
* :math:`g_{d,t}` —— 弃光电量（可行域松弛项，仅当 :math:`\text{allow\_surplus}` 为真）

约束：

.. math::

    q_{d,t} + y_{d,t} + V_{d,t} - g_{d,t} &= L_{d,t} + x_{d,t} \quad(\text{功率平衡})\\
    S_{d,t} &= S_{d,t-1} + \eta x_{d,t} - y_{d,t}/\eta \\
    1200 \le S_{d,t} &\le 10800,\qquad S_{d,0} = S_{d,\text{end}} = 6000\\
    0 \le q_{d,t},\quad 0 \le x_{d,t}, y_{d,t} &\le P^{\max}\Delta t = 833.3333,\quad
    0 \le g_{d,t} \le V_{d,t}

目标：:math:`\min \sum_{d,t} c_{d,t}\, q_{d,t}`。

**消元说明（为什么矩阵里没有 :math:`q`）**
    :math:`q` 只出现在功率平衡的等式中、目标系数又恒为正，故最优解必有
    :math:`q_{d,t} = \max\{L_{d,t} - V_{d,t} + x_{d,t} - y_{d,t} + g_{d,t},\,0\}`。
    把该式代入目标即得本模块使用的**等价压缩形式**——变量只剩
    :math:`(x, y, S, g)`，常数项 :math:`\sum c_{d,t}\,N_{d,t}` 由
    :meth:`DayBatchLP.const` 单独返回。购电量 :math:`q` 由 :func:`split_days`
    按平衡式**回代**得到，其非负性与平衡闭合性由调用方逐时段复核。

.. warning::
    压缩形式与"显式含 :math:`q` 的原始形式"在**最优值上等价**，但只在
    :math:`c_{d,t} > 0` 时成立（电价非正时 :math:`q` 无下界，等价性被破坏）。
    因此 :func:`build_day_batch_lp` 显式校验电价严格为正。

.. note::
    约束矩阵以 **SciPy 稀疏格式**（``csr_matrix``）构造：334 天合起来是
    ``48096 x 193000`` 的块对角矩阵，稠密表示需要约 70 GiB，
    稀疏表示只有约 150 万个非零元。单日（问题 1）时稀疏与稠密等价。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import csr_matrix

from . import paths

INTERVALS: int = paths.INTERVALS_PER_DAY
"""一天 10 分钟时段数 = 144。"""

HOURS: float = paths.INTERVAL_MINUTES / 60.0
"""单个时段的小时数 = 10/60。"""


def _soc_difference_matrix(n: int) -> np.ndarray:
    """返回储能递推的状态差分矩阵 ``D*``（形状 ``n x (n + 1)``）。

    ``D*[t, t] = 1``、``D*[t, t + 1] = -1``，其余为 0；左乘状态块
    ``[S_0, S_1, ..., S_n]`` 得 ``S_{t+1} - S_t``（``t = 0..n-1``），
    即"下一时刻减当前时刻"。

    Args:
        n: 时段数 ``T``（一天 144）。

    Returns:
        形状 ``(n, n + 1)`` 的差分矩阵。
    """
    mat = np.zeros((n, n + 1))
    diag = np.arange(n)
    mat[diag, diag + 1] = 1.0
    mat[diag, diag] = -1.0
    return mat


@dataclass(frozen=True)
class DayBatchLP:
    r"""多日微网调度 LP 的矩阵与维度切片（压缩形式，不含购电量变量）。

    Attributes:
        n_days: 天数 ``D``。
        n_intervals: 每天时段数 ``T``（恒为 144）。
        n_vars: 变量总数。
        c: 目标系数向量（长度 ``n_vars``），斜率为正部分已含电价。
        const: 目标中的常数项（元），即 :math:`\sum_{d,t} c_{d,t} N_{d,t}`；
            ``N`` 为净负荷电量 :math:`L - V`。
        A_eq: 等式约束矩阵（储能递推）。
        b_eq: 等式右端。
        A_ub: 不等式矩阵（购电量非负 + 储电量上界 + 储电量下界 + 弃光上限）。
        b_ub: 不等式右端。
        bounds: 变量上下界序列。
        slices: ``{"x": (start, stop), "y": ..., "s": ..., "g": ...}``
            （``g`` 仅在 ``allow_surplus=True`` 时存在）。
        meta: 构造口径备忘（``eta``、``s_init``、``s_end``、``allow_surplus`` 等）。
    """

    n_days: int
    n_intervals: int
    n_vars: int
    c: np.ndarray
    const: float
    A_eq: np.ndarray
    b_eq: np.ndarray
    A_ub: np.ndarray
    b_ub: np.ndarray
    bounds: list[tuple[float, float]]
    slices: dict[str, tuple[int, int]]
    meta: dict[str, object]

    @property
    def n_rows_ub(self) -> int:
        """不等式约束条数。"""
        return int(self.A_ub.shape[0])


def build_day_batch_lp(
    load_energy: np.ndarray,
    pv_energy: np.ndarray,
    price: np.ndarray,
    *,
    eta: float | None = None,
    s_init: float | None = None,
    s_end: float | None = None,
    allow_surplus: bool = True,
) -> DayBatchLP:
    r"""构造 ``D`` 天微网日前调度 LP（块对角结构，跨日解耦）。

    Args:
        load_energy: 形状 ``(D, 144)`` 的小区负载电量（kWh），
            ``= 负载功率(kW) x 10/60``。
        pv_energy: 形状 ``(D, 144)`` 的光伏可用电量（kWh），口径同上。
        price: 形状 ``(D, 144)`` 的购电电价（元/kWh）。**必须逐元素严格为正**
            （压缩形式的等价性前提；问题 2 用附件 1 的单日曲线做 ``tile``）。
        eta: 充放电效率，默认 :data:`CUMCM2026_C.common.code.paths.STORAGE`
            的 0.90。
        s_init: 每天 0:00 的储电量（kWh），默认 6000（逐日归位口径 B1(i)）。
        s_end: 每天 24:00 的储电量（kWh）；``None``（默认）表示与 ``s_init``
            相同（**逐日归位**）。
        allow_surplus: 是否保留弃光松弛项 :math:`g`。为 ``True``（默认）时
            允许 :math:`0 \le g_{d,t} \le V_{d,t}`，保证光照过剩且储电已满时
            仍可行；为 ``False`` 时强制光伏全部消纳（用于对照实验）。

    Returns:
        组装好的 :class:`DayBatchLP`。

    Raises:
        ValueError: 形状不一致、存在非有限值、负载或光伏为负、电价非正，
            或 ``s_end < s_init`` 之外的边界设置不合法。
    """
    load = np.asarray(load_energy, dtype=float)
    pv = np.asarray(pv_energy, dtype=float)
    cost = np.asarray(price, dtype=float)
    if load.ndim != 2 or pv.shape != load.shape or cost.shape != load.shape:
        raise ValueError(
            f"形状必须一致且为二维：load{load.shape} pv{pv.shape} price{cost.shape}"
        )
    if load.shape[1] != INTERVALS:
        raise ValueError(f"每天时段数必须为 {INTERVALS}，收到 {load.shape[1]}")
    for name, arr in (("负载", load), ("光伏", pv), ("电价", cost)):
        if not np.isfinite(arr).all():
            raise ValueError(f"{name}矩阵存在非有限值（空值/文本）")
    if (load < 0).any() or (pv < 0).any():
        raise ValueError("负载或光伏存在负值")
    if (cost <= 0).any():
        raise ValueError("电价必须逐元素严格为正（压缩形式的等价性前提）")

    eta_value = float(paths.STORAGE.efficiency if eta is None else eta)
    if not 0.0 < eta_value <= 1.0:
        raise ValueError(f"效率必须在 (0, 1] 内，收到 {eta_value}")
    s0 = float(paths.STORAGE.soc_init_kwh if s_init is None else s_init)
    s1 = float(s0 if s_end is None else s_end)
    s_lo = float(paths.STORAGE.soc_min_kwh)
    s_hi = float(paths.STORAGE.soc_max_kwh)
    if not s_lo <= s0 <= s_hi or not s_lo <= s1 <= s_hi:
        raise ValueError(
            f"储电量边界 {s0}/{s1} 必须落在 [{s_lo}, {s_hi}] 内"
        )
    cap = float(paths.STORAGE.max_energy_per_interval_charge)

    n_days, n_t = load.shape
    # 变量分块（**扁平顺序 = 分块顺序**，无任何跨块交错）：
    #   x(D·T) | y(D·T) | S(D·(T+1)) | g(D·T)
    # S 块每天含 T+1 个时刻点（S_{d,0}..S_{d,T}）。
    n_dt = n_days * n_t
    n_soc = n_days * (n_t + 1)
    i_x, i_y, i_s, i_g = 0, n_dt, 2 * n_dt, 2 * n_dt + n_soc
    n_vars = i_g + (n_dt if allow_surplus else 0)

    # ---- 目标：常数项 + Σ c·(x - y + g)；q = N + x - y + g >= 0 由不等式块保证
    c = np.zeros(n_vars)
    flat_cost = cost.reshape(-1)
    c[i_x:i_x + n_dt] = flat_cost
    c[i_y:i_y + n_dt] = -flat_cost
    if allow_surplus:
        c[i_g:i_g + n_dt] = flat_cost
    net = (load - pv).reshape(-1)
    const = float((flat_cost * net).sum())

    # ---- 等式：储能递推 S_t - S_{t-1} - eta·x_t + y_t/eta = 0（统一在 SOC 块内）
    # 第 d 天第 t 个时段（t = 0..T-1）对应行 d·T + t：
    #   +1 → S 列 i_s + d·(T+1) + t + 1、-1 → 前一点（t = 0 时为 S_{d,0}）
    #   x 列 i_x + d·T + t 系数 -eta、y 列 i_y + d·T + t 系数 +1/eta
    # ``S_{d,0}`` 无等式行，由边界 ``(s0, s0)`` 钉死。
    n_eq = n_dt
    row_d = np.repeat(np.arange(n_days), n_t)
    row_t = np.tile(np.arange(n_t), n_days)
    eq_rows = row_d * n_t + row_t
    eq_rows_stack = np.concatenate([eq_rows, eq_rows, eq_rows, eq_rows])
    eq_cols_stack = np.concatenate([
        i_s + row_d * (n_t + 1) + row_t + 1,     # +1 落在 S_{d,t+1}
        i_s + row_d * (n_t + 1) + row_t,         # -1 落在 S_{d,t}（t = 0 时为 S_{d,0}）
        i_x + eq_rows,
        i_y + eq_rows,
    ])
    eq_data_stack = np.concatenate([
        np.ones(n_eq), -np.ones(n_eq),
        np.full(n_eq, -eta_value), np.full(n_eq, 1.0 / eta_value),
    ])
    a_eq = csr_matrix((eq_data_stack, (eq_rows_stack, eq_cols_stack)),
                      shape=(n_eq, n_vars))
    b_eq = np.zeros(n_eq)

    # ---- 不等式：4 个块（购电量非负 / SOC 上界 / SOC 下界 / 弃光上限）
    n_ub = n_eq + 2 * n_eq + (n_eq if allow_surplus else 0)
    ub_rows_parts: list[np.ndarray] = []
    ub_cols_parts: list[np.ndarray] = []
    ub_data_parts: list[np.ndarray] = []
    b_ub = np.zeros(n_ub)

    # 块 1（行 0..D·T-1）：y - x - g <= N_t  <=>  购电量非负
    ub_rows_parts += [eq_rows, eq_rows]
    ub_cols_parts += [i_y + eq_rows, i_x + eq_rows]
    ub_data_parts += [np.ones(n_eq), -np.ones(n_eq)]
    if allow_surplus:
        ub_rows_parts.append(eq_rows)
        ub_cols_parts.append(i_g + eq_rows)
        ub_data_parts.append(-np.ones(n_eq))
    b_ub[:n_eq] = net

    # 块 2/3：SOC 上界与下界，用前缀和展开。
    # 对第 d 天第 t 个时段（t = 0..T-1，即 S_{d,t+1}）：
    #   S_{d,t+1} = s0 + eta·Σ_{τ<=t} x_τ - (1/eta)·Σ_{τ<=t} y_τ
    # 故列下标 = 该日块起点 + 前缀步 k（k = 0..t），系数取下三角 lower[t, k]；
    # 行下标 = 块起点 n_dt（或 2·n_dt）+ 该日行偏移 d·T + t。
    # 下三角的每个非零位置都要在**每一天**重复一遍，故用 kron 式的两层展开。
    lower = np.tril(np.ones((n_t, n_t)))
    tri_r, tri_c = np.nonzero(lower)          # 天内位置（t, k）
    tri_v = lower[tri_r, tri_c]
    tri_d = np.repeat(np.arange(n_days), tri_r.size)   # 所属日（0..D-1）
    tri_t = np.tile(tri_r, n_days)                     # 天内行 t
    tri_k = np.tile(tri_c, n_days)                     # 天内列 k
    day_offset = tri_d * n_t
    r2_rows = n_dt + day_offset + tri_t
    r2_cols_x = i_x + day_offset + tri_k
    r2_cols_y = i_y + day_offset + tri_k
    r3_rows = 2 * n_dt + day_offset + tri_t
    tri_v_full = np.tile(tri_v, n_days)
    ub_rows_parts += [r2_rows, r2_rows, r3_rows, r3_rows]
    ub_cols_parts += [r2_cols_x, r2_cols_y, r2_cols_x, r2_cols_y]
    ub_data_parts += [eta_value * tri_v_full, -tri_v_full / eta_value,
                      -eta_value * tri_v_full, tri_v_full / eta_value]
    # 块 2 的右端按天重复；块 3 同样如此（前缀和展开对每个 t 都给一条真实约束）
    b_ub[n_dt:n_dt + n_eq] = s_hi - s0
    b_ub[2 * n_dt:2 * n_dt + n_eq] = s0 - s_lo

    if allow_surplus:  # 块 4：g_t <= V_t（行偏移 3·D·T，列在 g 块内）
        g_rows = 3 * n_dt + np.arange(n_dt)
        ub_rows_parts.append(g_rows)
        ub_cols_parts.append(i_g + np.arange(n_dt))
        ub_data_parts.append(np.ones(n_dt))
        b_ub[3 * n_dt:4 * n_dt] = pv.reshape(-1)

    a_ub = csr_matrix((np.concatenate(ub_data_parts),
                       (np.concatenate(ub_rows_parts), np.concatenate(ub_cols_parts))),
                      shape=(n_ub, n_vars))

    # ---- 结构性自检（防止上面任何一处行列偏移写错后静默失效）
    # 逐块非零元计数：
    #   块 1 = D·T·(2 + [允许弃光])、块 2/3 = 各 D·(T·(T+1)/2)、块 4 = D·T。
    # 写错行/列偏移（例如漏乘 n_t、把 n_t 当 n_dt）会让实际计数与预期不符。
    n_tri = n_t * (n_t + 1) // 2
    expect_ub = (n_dt * (2 + (1 if allow_surplus else 0))
                 + 4 * n_days * n_tri
                 + (n_dt if allow_surplus else 0))
    if a_ub.nnz != expect_ub:
        raise AssertionError(
            f"A_ub 非零元数异常：{a_ub.nnz}（预期 {expect_ub}）——说明有约束块未被正确铺满"
        )
    if a_eq.nnz != n_dt * 4:
        raise AssertionError(f"A_eq 非零元数异常：{a_eq.nnz}（预期 {n_dt * 4}）")
    if allow_surplus and b_ub[3 * n_dt:4 * n_dt].max() <= 0:
        raise AssertionError("弃光上限右端全为 0：光伏矩阵可能传成了功率而非电量")

    # ---- 变量边界（顺序与变量分块严格一致：x | y | S | g）
    # S 块按天连续排布：每天的 (T+1) 个时刻点里，S_{d,0} 与 S_{d,T} 钉死为
    # s0 / s1，中间 T-1 个自由；务必**逐日展开**，否则第 2 天起的钉死位置
    # 会对不上（曾因此让模型偷偷允许 SOC 跨日不归位）。
    bounds: list[tuple[float, float]] = []
    bounds += [(0.0, cap)] * n_dt                                 # x
    bounds += [(0.0, cap)] * n_dt                                 # y
    for _ in range(n_days):
        bounds += [(s0, s0)]                                      # S_{d,0}
        bounds += [(s_lo, s_hi)] * (n_t - 1)                      # S_{d,1..T-1}
        bounds += [(s1, s1)]                                      # S_{d,T}
    if allow_surplus:
        bounds += [(0.0, float(v)) for v in pv.reshape(-1)]       # g
    if len(bounds) != n_vars:
        raise AssertionError(
            f"变量边界条数 {len(bounds)} != 变量数 {n_vars}——分块顺序与边界不一致"
        )

    slices = {
        "x": (i_x, i_x + n_dt),
        "y": (i_y, i_y + n_dt),
        "s": (i_s, i_s + n_soc),
        "g": (i_g, i_g + n_dt) if allow_surplus else (i_g, i_g),
    }
    meta: dict[str, object] = {
        "eta": eta_value,
        "s_init_kwh": s0,
        "s_end_kwh": s1,
        "soc_min_kwh": s_lo,
        "soc_max_kwh": s_hi,
        "power_per_interval_kwh": cap,
        "allow_surplus": bool(allow_surplus),
        "energy_conversion": "kWh = kW x 10/60",
        "reduced_form": "q 由平衡式回代；等价性依赖 c > 0",
    }
    return DayBatchLP(
        n_days=n_days, n_intervals=n_t, n_vars=n_vars, c=c, const=const,
        A_eq=a_eq, b_eq=b_eq, A_ub=a_ub, b_ub=b_ub, bounds=bounds,
        slices=slices, meta=meta,
    )


def solve_lp(lp: DayBatchLP, *, max_iter: int = 200_000,
             check_feasibility: bool = False) -> tuple[np.ndarray, dict]:
    """求解 :func:`build_day_batch_lp` 构造的线性规划。

    Args:
        lp: 待求解的 :class:`DayBatchLP`。
        max_iter: HiGHS 迭代上限。
        check_feasibility: 是否先单独跑一次零目标求解以确认可行性
            （对已知可行的批量问题可关闭以节省时间）。

    Returns:
        ``(z, info)``：``z`` 为最优解向量；``info`` 含求解器状态、迭代次数、
        目标值（含常数项）与耗时。

    Raises:
        RuntimeError: 未求得最优解。
    """
    if check_feasibility:
        feas = linprog(np.zeros(lp.n_vars), A_ub=lp.A_ub, b_ub=lp.b_ub,
                       A_eq=lp.A_eq, b_eq=lp.b_eq, bounds=lp.bounds,
                       method="highs", options={"maxiter": max_iter})
        if not feas.success:
            raise RuntimeError(f"可行性预检失败：{feas.message}")
    res = linprog(lp.c, A_ub=lp.A_ub, b_ub=lp.b_ub, A_eq=lp.A_eq, b_eq=lp.b_eq,
                  bounds=lp.bounds, method="highs",
                  options={"maxiter": max_iter})
    info = {
        "status": int(res.status),
        "success": bool(res.success),
        "message": str(res.message),
        "n_vars": int(lp.n_vars),
        "n_eq": int(lp.A_eq.shape[0]),
        "n_ub": int(lp.A_ub.shape[0]),
        "n_days": int(lp.n_days),
        "nit": int(getattr(res, "nit", -1)),
    }
    if not res.success:
        raise RuntimeError(f"线性规划求解失败：{res.message}")
    info["objective_with_const_yuan"] = float(lp.const + res.fun)
    info["objective_without_const_yuan"] = float(res.fun)
    return np.asarray(res.x, dtype=float), info


def split_days(lp: DayBatchLP, z: np.ndarray, price: np.ndarray,
               load_energy: np.ndarray, pv_energy: np.ndarray,
               *, tol: float = 1e-9) -> dict[str, np.ndarray]:
    """把批量解拆成逐日序列，并按平衡式回代购电量。

    Args:
        lp: 已求解的 :class:`DayBatchLP`。
        z: 最优解向量。
        price: 形状 ``(D, 144)`` 的电价（用于返回逐日费用）。
        load_energy: 形状 ``(D, 144)`` 的负载电量。
        pv_energy: 形状 ``(D, 144)`` 的光伏电量。
        tol: 小于该绝对值的抖动量归零，避免 ``-0.0`` 与求解器噪声进入结果文件。

    Returns:
        含 ``x``/``y``/``g``/``s``（形状 ``(D, 144)`` 或 ``(D, 145)``）、
        ``q``（``(D, 144)``，回代购电量）、``cost_yuan``（``(D,)``）、
        ``const_yuan``（标量）的字典。
    """
    n_days, n_t = lp.n_days, lp.n_intervals

    def clean(arr: np.ndarray) -> np.ndarray:
        """把亚容差抖动量归零。"""
        return np.where(np.abs(arr) < tol, 0.0, arr)

    ix0, ix1 = lp.slices["x"]
    iy0, iy1 = lp.slices["y"]
    is0, is1 = lp.slices["s"]
    ig0, ig1 = lp.slices["g"]

    x = clean(z[ix0:ix1]).reshape(n_days, n_t)
    y = clean(z[iy0:iy1]).reshape(n_days, n_t)
    g = (clean(z[ig0:ig1]).reshape(n_days, n_t) if ig1 > ig0
         else np.zeros((n_days, n_t)))
    # LP 的 S 块覆盖 S_{d,0}..S_{d,T}（T+1 个）。S_{d,0} 与 S_{d,T} 由等式/边界共同
    # 钉死，而 S_{d,T} 另按递推式回代，使返回的 soc 在数值上逐时段闭合
    # （t = 1..T 全部满足 S_t = S_{t-1} + eta·x_t - y_t/eta）。
    soc = clean(z[is0:is1]).reshape(n_days, n_t + 1)
    soc[:, 0] = float(lp.meta["s_init_kwh"])
    soc[:, n_t] = (soc[:, n_t - 1] + lp.meta["eta"] * x[:, n_t - 1]
                   - y[:, n_t - 1] / lp.meta["eta"])
    net = np.asarray(load_energy, dtype=float) - np.asarray(pv_energy, dtype=float)
    q = clean(net + x - y + g)
    cost = (np.asarray(price, dtype=float) * q).sum(axis=1)
    return {"x": x, "y": y, "g": g, "s": soc, "q": q,
            "net": net, "cost_yuan": cost, "const_yuan": float(lp.const)}


def solve_days_independently(
    load_energy: np.ndarray,
    pv_energy: np.ndarray,
    price: np.ndarray,
    *,
    eta: float | None = None,
    s_init: float | None = None,
    s_end: float | None = None,
    allow_surplus: bool = True,
) -> dict[str, object]:
    """**逐日独立**求解同一模型（每天一个 LP），用于与批量解对账。

    结构化相同的逐日 LP 与块对角批量 LP 应有**逐日相同**的最优值（可能存在
    多重最优解的差异，故调用方应比较**目标值**而非决策变量本身）。

    Args:
        load_energy: 形状 ``(D, 144)`` 的负载电量（kWh）。
        pv_energy: 形状 ``(D, 144)`` 的光伏电量（kWh）。
        price: 形状 ``(D, 144)`` 的电价（元/kWh）。
        eta: 充放电效率，默认取全局参数。
        s_init: 每天 0:00 储电量，默认 6000。
        s_end: 每天 24:00 储电量，默认等于 ``s_init``。
        allow_surplus: 是否保留弃光松弛项。

    Returns:
        含 ``x``/``y``/``g``/``s``/``q``/``cost_yuan``/``per_day_objective``
        （每天单独 LP 的目标值，含常数项）与 ``solver_statuses`` 的字典。
    """
    n_days = int(load_energy.shape[0])
    n_t = INTERVALS
    x = np.zeros((n_days, n_t))
    y = np.zeros((n_days, n_t))
    g = np.zeros((n_days, n_t))
    soc = np.zeros((n_days, n_t + 1))
    q = np.zeros((n_days, n_t))
    objectives: list[float] = []
    statuses: list[str] = []
    for d in range(n_days):
        lp_d = build_day_batch_lp(
            load_energy[d:d + 1], pv_energy[d:d + 1], price[d:d + 1],
            eta=eta, s_init=s_init, s_end=s_end, allow_surplus=allow_surplus,
        )
        z_d, info_d = solve_lp(lp_d)
        day = split_days(lp_d, z_d, price[d:d + 1], load_energy[d:d + 1],
                         pv_energy[d:d + 1])
        x[d] = day["x"][0]
        y[d] = day["y"][0]
        g[d] = day["g"][0]
        soc[d] = day["s"][0]
        q[d] = day["q"][0]
        objectives.append(float(info_d["objective_with_const_yuan"]))
        statuses.append(str(info_d["message"]))
    return {
        "x": x, "y": y, "g": g, "s": soc, "q": q,
        "cost_yuan": (np.asarray(price) * q).sum(axis=1),
        "per_day_objective": np.asarray(objectives),
        "solver_statuses": statuses,
    }


def verify_day(
    x: np.ndarray,
    y: np.ndarray,
    g: np.ndarray,
    soc: np.ndarray,
    q: np.ndarray,
    load_energy: np.ndarray,
    pv_energy: np.ndarray,
    *,
    eta: float | None = None,
    s_init: float | None = None,
    s_end: float | None = None,
    tol_balance: float = 1e-6,
    tol_recurrence: float = 1e-6,
) -> dict[str, float]:
    """对**单日**解做独立残差自检（不依赖求解器自报结果）。

    Args:
        x: 长度 144 的充电量。
        y: 长度 144 的放电量。
        g: 长度 144 的弃光量。
        soc: 长度 145 的储电量（``soc[0]`` 为 0:00）。
        q: 长度 144 的购电量（应已由平衡式回代）。
        load_energy: 长度 144 的负载电量。
        pv_energy: 长度 144 的光伏电量。
        eta: 效率，默认取全局参数。
        s_init: 0:00 储电量期望值，默认 6000。
        s_end: 24:00 储电量期望值，默认等于 ``s_init``。
        tol_balance: 平衡残差容差（kWh）。
        tol_recurrence: 递推残差容差（kWh）。

    Returns:
        残差与越界量字典；``*_ok`` 键为对应的布尔结论。
    """
    eta_v = float(paths.STORAGE.efficiency if eta is None else eta)
    s0 = float(paths.STORAGE.soc_init_kwh if s_init is None else s_init)
    s1 = float(s0 if s_end is None else s_end)
    s_lo = float(paths.STORAGE.soc_min_kwh)
    s_hi = float(paths.STORAGE.soc_max_kwh)
    cap = float(paths.STORAGE.max_energy_per_interval_charge)

    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    g = np.asarray(g, dtype=float)
    soc = np.asarray(soc, dtype=float)
    q = np.asarray(q, dtype=float)
    load = np.asarray(load_energy, dtype=float)
    pv = np.asarray(pv_energy, dtype=float)

    bal = np.abs(q + y + pv - g - load - x)
    rec = np.abs(np.diff(soc) - (eta_v * x - y / eta_v))
    out = {
        "max_balance_residual_kwh": float(bal.max()),
        "max_recurrence_residual_kwh": float(rec.max()),
        "max_soc_upper_violation_kwh": float(max(0.0, soc[1:-1].max() - s_hi)),
        "max_soc_lower_violation_kwh": float(max(0.0, s_lo - soc[1:-1].min())),
        "max_charge_over_power_kwh": float(max(0.0, x.max() - cap)),
        "max_discharge_over_power_kwh": float(max(0.0, y.max() - cap)),
        "max_curtail_over_pv_kwh": float(max(0.0, (g - pv).max())),
        "purchase_nonneg_violation_kwh": float(max(0.0, -q.min())),
        "soc_start_deviation_kwh": float(abs(soc[0] - s0)),
        "soc_end_deviation_kwh": float(abs(soc[-1] - s1)),
        "charge_total_kwh": float(x.sum()),
        "discharge_total_kwh": float(y.sum()),
        "curtail_total_kwh": float(g.sum()),
        "purchase_total_kwh": float(q.sum()),
    }
    out["ratio_discharge_over_charge"] = (
        float(y.sum() / x.sum()) if x.sum() > 1e-12 else float("nan")
    )
    out["eta_squared"] = eta_v ** 2
    out["ratio_gap_to_eta_squared"] = (
        abs(out["ratio_discharge_over_charge"] - eta_v ** 2)
        if x.sum() > 1e-12 else float("nan")
    )
    out["balance_ok"] = bool(out["max_balance_residual_kwh"] <= tol_balance)
    out["recurrence_ok"] = bool(out["max_recurrence_residual_kwh"] <= tol_recurrence)
    out["soc_bounds_ok"] = bool(
        out["max_soc_upper_violation_kwh"] <= tol_recurrence
        and out["max_soc_lower_violation_kwh"] <= tol_recurrence
    )
    out["power_limits_ok"] = bool(
        out["max_charge_over_power_kwh"] <= tol_recurrence
        and out["max_discharge_over_power_kwh"] <= tol_recurrence
    )
    out["curtail_ok"] = bool(out["max_curtail_over_pv_kwh"] <= tol_recurrence)
    out["purchase_nonneg_ok"] = bool(out["purchase_nonneg_violation_kwh"] <= 1e-9)
    out["daily_closure_ok"] = bool(
        out["soc_start_deviation_kwh"] <= tol_recurrence
        and out["soc_end_deviation_kwh"] <= tol_recurrence
    )
    return out


def common_block_labels() -> list[str]:
    """返回 ``充放电量`` 表的 6 个 4 小时区块标签（与 ``io_attachments`` 同源）。"""
    from . import io_attachments as _io

    return _io.half_hour_block_labels()


def as_list(values: Sequence[float], ndigits: int = 6) -> list[float]:
    """把可迭代数值转成**确定性舍入**的 Python 浮点列表（便于 JSON 落盘）。

    Args:
        values: 待转换的数值序列。
        ndigits: 保留小数位。

    Returns:
        舍入后的浮点列表。
    """
    return [float(np.round(float(v), ndigits)) for v in values]


__all__ = [
    "DayBatchLP",
    "HOURS",
    "INTERVALS",
    "as_list",
    "build_day_batch_lp",
    "common_block_labels",
    "solve_days_independently",
    "solve_lp",
    "split_days",
    "verify_day",
]
