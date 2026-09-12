"""Problem 4-3: problem-3 rolling forecast under attachment-4 prices."""
from __future__ import annotations
import json
from datetime import date
from . import io_attachments as io, paths
from .solve_problem3 import forecast_vector, solve_rolling
import numpy as np

def run(output=None, pv_scale: float = 0.825):
 a1,a2,a3,a4=io.load_all(); start=date.fromisoformat(paths.RESULT2_START); rec=[]; total={'plan_purchase_kwh':0.,'final_purchase_kwh':0.,'emergency_kwh':0.,'plan_cost_yuan':0.,'adjustment_cost_yuan':0.,'emergency_cost_yuan':0.}
 for i,d in enumerate(a2.dates):
  if d<start: continue
  price=np.asarray(a4.price[i],float); f=[(0,forecast_vector(a3,d,0,pv_scale)),(36,forecast_vector(a3,d,6,pv_scale)),(72,forecast_vector(a3,d,12,pv_scale)),(108,forecast_vector(a3,d,18,pv_scale))]; ini,fin=solve_rolling(price,a2.load[i],f); p0=ini['purchase']; pf=fin['purchase']; pv=np.maximum(a2.pv_actual[i]*paths.INTERVAL_MINUTES/60-fin['curtail'],0); emg=np.maximum(a2.load[i]*paths.INTERVAL_MINUTES/60-(pf+fin['discharge']-fin['charge']+pv),0); pa=pf-p0; ac=float(np.where(pa>=0,1.5*price*pa,0.5*price*(-pa)).sum()); ec=float(np.dot(5*price,emg)); r={'date':d.isoformat(),'plan_purchase_kwh':float(p0.sum()),'final_purchase_kwh':float(pf.sum()),'adjustment_cost_yuan':ac,'emergency_kwh':float(emg.sum()),'emergency_cost_yuan':ec,'plan_cost_yuan':float(np.dot(price,p0))}; rec.append(r)
  for k in total: total[k]+=r.get(k,0.)
 total['total_cost_yuan']=total['plan_cost_yuan']+total['adjustment_cost_yuan']+total['emergency_cost_yuan']; out={'model':{'question':'4-3','price_source':'attachment4','forecast_source':'attachment3','pv_forecast_scale':pv_scale},'summary':total,'daily':rec}; dst=output or paths.PROCESSED_DIR/'problem4_3_daily_solution.json'; dst.parent.mkdir(parents=True,exist_ok=True); dst.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8'); return out
if __name__=='__main__': print(json.dumps(run()['summary'],ensure_ascii=False,indent=2))
