from __future__ import annotations
import json,sys
from datetime import date
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from src.CUMCM2026_C import io_attachments as io,paths
from src.CUMCM2026_C.solve_problem2 import solve_day_solution
from src.CUMCM2026_C.solve_problem3 import forecast_vector

def evaluate(scale: float, volatile=False):
 a1,a2,a3,a4=io.load_all(); p0=np.asarray(a1.price.values,float); start=date.fromisoformat(paths.RESULT2_START); total={'plan_kwh':0.,'emg_kwh':0.,'plan_cost':0.,'emg_cost':0.}
 for i,d in enumerate(a2.dates):
  if d<start: continue
  p=np.asarray(a4.price[i],float) if volatile else p0; pvplan=forecast_vector(a3,d,0,scale); s,v=solve_day_solution(d,p,a2.load[i],pvplan); pv=np.maximum(a2.pv_actual[i]/6-v['curtail'],0); em=np.maximum(a2.load[i]/6-(v['purchase']+v['discharge']-v['charge']+pv),0); total['plan_kwh']+=s.purchase_kwh; total['emg_kwh']+=em.sum(); total['plan_cost']+=np.dot(p,v['purchase']); total['emg_cost']+=np.dot(5*p,em)
 total['total_cost']=total['plan_cost']+total['emg_cost']; return total
def main():
 out={}
 for vol in (False,True):
  key='q2_forecast_fixed' if not vol else 'q4_2_forecast_fixed'; out[key]={}
  for s in (0.84,.82,.80,.78,.76): out[key][str(s)]=evaluate(s,vol)
 Path(paths.PROCESSED_DIR/'q2_forecast_only_tuning.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
 for k,v in out.items():
  print(k)
  for s,r in v.items(): print(s,round(r['total_cost'],2),round(r['plan_kwh'],2),round(r['emg_kwh'],2))
if __name__=='__main__':main()
