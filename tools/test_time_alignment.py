"""比较附件时点到 10 分钟时段的两种对齐口径。"""
from __future__ import annotations
import json, sys
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from src.CUMCM2026_C import io_attachments as io
from src.CUMCM2026_C.solve_problem2 import solve_day

def main():
    a1,a2,_a3,a4=io.load_all(); dates=[date(2025,3,20),date(2025,6,21),date(2025,9,23),date(2025,12,21)]
    idx={d:i for i,d in enumerate(a2.dates)}; out={}
    for name,shift in [('A_endpoint',0),('B_template_left',1)]:
        q1=solve_day(date(2025,1,1),np.roll(a1.price.values,shift),np.roll(a1.load.values,shift),np.roll(a1.pv_forecast.values,shift))
        reps={}
        for d in dates:
            i=idx[d]; reps[d.isoformat()]=solve_day(d,np.roll(a1.price.values,shift),np.roll(a2.load[i],shift),np.roll(a2.pv_actual[i],shift)).__dict__
        out[name]={'problem1':q1.__dict__,'problem2_representative':reps}
    p=Path('data/processed/CUMCM2026_C/time_alignment_tests.json'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(out,ensure_ascii=False,indent=2)); print('写入',p)
if __name__=='__main__': main()
