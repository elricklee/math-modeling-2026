"""Problem 4-2: volatile prices with the forecast-only Q2 plan."""
from __future__ import annotations
import json
from datetime import date
import numpy as np
from . import io_attachments as io, paths
from .solve_problem2 import solve_day_solution
from .solve_problem3 import forecast_vector

def run(output=None, pv_scale: float = 0.825):
 a1,a2,a3,a4=io.load_all(); start=date.fromisoformat(paths.RESULT2_START); daily=[]; sm={'plan_purchase_kwh':0.,'emergency_kwh':0.,'plan_cost_yuan':0.,'emergency_cost_yuan':0.}
 for i,d in enumerate(a2.dates):
  if d<start: continue
  price=np.asarray(a4.price[i],float); pvplan=forecast_vector(a3,d,0,pv_scale); s,v=solve_day_solution(d,price,a2.load[i],pvplan); actual=np.maximum(a2.pv_actual[i]/6-v['curtail'],0); em=np.maximum(a2.load[i]/6-(v['purchase']+v['discharge']-v['charge']+actual),0); r={'date':d.isoformat(),'plan_purchase_kwh':float(s.purchase_kwh),'plan_cost_yuan':float(np.dot(price,v['purchase'])),'emergency_kwh':float(em.sum()),'emergency_cost_yuan':float(np.dot(5*price,em)),'purchase_by_interval_kwh':v['purchase'].tolist(),'emergency_by_interval_kwh':em.tolist(),'charge_by_interval_kwh':v['charge'].tolist(),'discharge_by_interval_kwh':v['discharge'].tolist(),'soc_kwh':v['soc'].tolist()}; daily.append(r)
  for k in sm: sm[k]+=r.get(k,0.)
 sm['total_cost_yuan']=sm['plan_cost_yuan']+sm['emergency_cost_yuan']; sm['total_purchase_kwh']=sm['plan_purchase_kwh']+sm['emergency_kwh']; out={'model':{'question':'4-2','information':'00:00 forecast only','price_source':'attachment4','forecast_source':'attachment3','actual_source':'attachment2','pv_forecast_scale':pv_scale,'emergency_multiplier':5.0},'summary':sm,'daily':daily}; dst=output or paths.PROCESSED_DIR/'problem4_2_forecast_solution.json'; dst.parent.mkdir(parents=True,exist_ok=True); dst.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8'); return out
if __name__=='__main__': print(json.dumps(run()['summary'],ensure_ascii=False,indent=2))
