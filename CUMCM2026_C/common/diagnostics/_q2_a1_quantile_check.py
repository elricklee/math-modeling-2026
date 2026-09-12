"""A1 复核：求解章 §四 L121 的储能十分位口径自洽性检查。

只读 Q2_timeseries.csv 的「时段末储电量」列，比较两种分位口径：
  A = 第 p(N+1) 位线性插值（Hyndman-Fan type 6；statistics.quantiles / numpy method='weibull'）
  B = 第 p(N-1)+1 位线性插值（Hyndman-Fan type 7；numpy 默认 'linear'）
并给出九个数在两口径下的最大差，用于核对正文「最多相差约 1 kWh」的说法。

不写任何项目文件；只打印。
"""

import csv
import statistics

import numpy as np

CSV = r"CUMCM2026_C/Q2/outputs/Q2_timeseries.csv"
SOC_COL = 16  # 「时段末储电量(kWh)」
PS = [i / 10 for i in range(1, 10)]

soc = []
with open(CSV, encoding="utf-8-sig", newline="") as fh:
    reader = csv.reader(fh)
    next(reader)
    for row in reader:
        soc.append(float(row[SOC_COL]))

a = np.array(sorted(soc), dtype=float)
n = a.size
print("N =", n)


def type6(p):
    h = (n + 1) * p
    i = int(np.floor(h))
    frac = h - i
    return float(a[i - 1] + frac * (a[i] - a[i - 1]))


def type7(p):
    h = (n - 1) * p + 1.0
    i = int(np.floor(h))
    frac = h - i
    return float(a[i - 1] + frac * (a[i] - a[i - 1]))


va = [type6(p) for p in PS]
vb = [type7(p) for p in PS]
print("A type6 p(N+1) :", [round(v, 1) for v in va])
print("B type7 deflt  :", [round(v, 1) for v in vb])
print("|A-B| by decile:", [round(abs(x - y), 4) for x, y in zip(va, vb)])
print("max |A-B|      =", round(max(abs(x - y) for x, y in zip(va, vb)), 4), "kWh")
print("libs: np.quantile default ->", [round(float(x), 1) for x in np.quantile(a, PS)])
print("libs: statistics.quantiles ->", [round(float(x), 1) for x in statistics.quantiles(list(a), n=10)])
print("libs: np.quantile weibull  ->", [round(float(x), 1) for x in np.quantile(a, PS, method="weibull")])

# 正文写「最多相差约 1 kWh」。分别看这句在两个范围上是否站得住：
#   (1) 只看正文列出的九个十分位；(2) 看全部百分位网格。
grid = [i / 1000 for i in range(1, 1000)]
diff_grid = [abs(type6(p) - type7(p)) for p in grid]
worst = max(range(len(grid)), key=lambda k: diff_grid[k])
print("grid p in (0,1) step .001: max |A-B| =", round(diff_grid[worst], 4),
      "kWh at p =", grid[worst])
cents = [i / 100 for i in range(1, 100)]
diff_cents = [abs(type6(p) - type7(p)) for p in cents]
wc = max(range(len(cents)), key=lambda k: diff_cents[k])
print("percentile grid 1..99    : max |A-B| =", round(diff_cents[wc], 4),
      "kWh at p =", cents[wc])
