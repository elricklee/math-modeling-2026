"""Problem 3 rolling forecast/adjustment model.

At 00:00 an initial purchase plan is optimized from the 00:00 PV forecast.
At 06:00, 12:00 and 18:00 the remaining decisions are re-optimized with
the newly issued forecast while all already executed decisions are fixed.
The final schedule is replayed against attachment-2 actual PV; deficits are
settled as emergency purchases.  All powers are converted to 10-minute kWh.
"""
from __future__ import annotations
import json
from datetime import date
from pathlib import Path
import numpy as np
from scipy.optimize import linprog
from . import io_attachments as io, paths

DT = paths.INTERVAL_MINUTES / 60.0; T = paths.INTERVALS_PER_DAY
ETA = paths.STORAGE.efficiency; XMAX = paths.STORAGE.max_energy_per_interval_charge; YMAX = paths.STORAGE.max_energy_per_interval_discharge
IS=0; IX=T+1; IY=IX+T; IG=IY+T; IP=IG+T; IZ=IP+T; N=IZ+T

def forecast_vector(a3, day, release_hour, scale: float = 1.0):
    rows=[i for i,(d,h) in enumerate(zip(a3.release_days,a3.release_hours)) if d==day and int(h)==release_hour]
    if not rows: raise KeyError((day,release_hour))
    hourly=np.asarray(a3.forecast[rows[0]],float); out=np.empty(T)
    for j in range(T):
        # array index j is interval number j+1; its right endpoint lies in
        # local hour ceil((j+1)/6).  This avoids a one-interval shift at
        # release boundaries (e.g. index 36 is the 6:00--6:10 interval).
        h=int(np.ceil((j+1)/6.0)); k=((h-release_hour-1)%24)+1
        out[j]=hourly[k-1] * scale
    return out

def solve_rolling(price, load_kw, forecasts):
    """Return initial and final schedules; forecasts is [(release_t, pv_kw)]."""
    net=(load_kw*DT); prev=None; initial=None; final=None
    for release_t,pv_kw in forecasts:
        pv=np.asarray(pv_kw)*DT
        if prev is not None:
            pv = prev['pv'].copy()
            pv[release_t:] = np.asarray(pv_kw, dtype=float)[release_t:] * DT
        b=np.zeros((2*T,N)); rhs=np.zeros(2*T)
        for t in range(T):
            b[t,IX+t]=-1; b[t,IY+t]=1; b[t,IG+t]=-1; b[t,IP+t]=1; b[t,IZ+t]=1; rhs[t]=net[t]-pv[t]
            b[T+t,IS+t+1]=1; b[T+t,IS+t]=-1; b[T+t,IX+t]=-ETA; b[T+t,IY+t]=1/ETA
        bounds=[(paths.STORAGE.soc_init_kwh,paths.STORAGE.soc_init_kwh)]+[(paths.STORAGE.soc_min_kwh,paths.STORAGE.soc_max_kwh)]*(T-1)+[(paths.STORAGE.soc_init_kwh,paths.STORAGE.soc_init_kwh)]+[(0,XMAX)]*T+[(0,YMAX)]*T+[(0,float(v)) for v in pv]+[(0,None)]*T+[(0,None)]*T
        if prev is not None:
            # fix all intervals before the new forecast release; SOC state is fixed too
            for t in range(release_t):
                for idx,val in ((IX+t,prev['charge'][t]),(IY+t,prev['discharge'][t]),(IG+t,prev['curtail'][t]),(IP+t,prev['purchase'][t]),(IZ+t,0.0)):
                    bounds[idx]=(float(val),float(val))
                bounds[IS+t]=(float(prev['soc'][t]),float(prev['soc'][t]))
            bounds[IS+release_t]=(float(prev['soc'][release_t]),float(prev['soc'][release_t]))
        c=np.zeros(N); c[IP:IP+T]=price; c[IZ:IZ+T]=5*price
        res=linprog(c,A_eq=b,b_eq=rhs,bounds=bounds,method='highs')
        if not res.success: raise RuntimeError(res.message)
        z=res.x; prev={'purchase':z[IP:IP+T].copy(),'charge':z[IX:IX+T].copy(),'discharge':z[IY:IY+T].copy(),'curtail':z[IG:IG+T].copy(),'soc':z[IS:IS+T+1].copy(),'pv':pv.copy()}
        if initial is None: initial={k:v.copy() for k,v in prev.items()}
        final=prev
    return initial, final

def run(output: Path|None=None, pv_scale: float = 0.825):
    a1,a2,a3,a4=io.load_all(); price=np.asarray(a1.price.values,float); start=date.fromisoformat(paths.RESULT2_START)
    records=[]; reps={date(2025,3,20),date(2025,6,21),date(2025,9,23),date(2025,12,21)}; summary={'plan_purchase_kwh':0.,'final_purchase_kwh':0.,'emergency_kwh':0.,'plan_cost_yuan':0.,'adjustment_cost_yuan':0.,'emergency_cost_yuan':0.}
    for i,day in enumerate(a2.dates):
        if day<start: continue
        f=[(0,forecast_vector(a3,day,0,pv_scale)),(36,forecast_vector(a3,day,6,pv_scale)),(72,forecast_vector(a3,day,12,pv_scale)),(108,forecast_vector(a3,day,18,pv_scale))]
        initial,final=solve_rolling(price,a2.load[i],f)
        p0=initial['purchase']; pf=final['purchase']; pa=pf-p0
        actual_pv=a2.pv_actual[i]*DT; delivered=np.maximum(actual_pv-final['curtail'],0); supply=pf+final['discharge']-final['charge']+delivered
        emg=np.maximum(a2.load[i]*DT-supply,0)
        adj=np.where(pa>=0,1.5*price*pa,0.5*price*(-pa)).sum(); emgc=float(np.dot(5*price,emg))
        rec={'date':day.isoformat(),'plan_purchase_kwh':float(p0.sum()),'final_purchase_kwh':float(pf.sum()),'adjustment_signed_kwh':float(pa.sum()),'adjustment_cost_yuan':float(adj),'emergency_kwh':float(emg.sum()),'emergency_cost_yuan':emgc,'plan_cost_yuan':float(np.dot(price,p0)),'purchase_by_interval_kwh':pf.tolist(),'plan_by_interval_kwh':p0.tolist(),'emergency_by_interval_kwh':emg.tolist()}
        records.append(rec)
        for k in summary: summary[k]+=rec.get(k,0.)
        if day in reps: rec['representative']=True
    summary['total_cost_yuan']=summary['plan_cost_yuan']+summary['adjustment_cost_yuan']+summary['emergency_cost_yuan']
    out={'model':{'question':3,'releases':[0,6,12,18],'emergency_multiplier':5.,'downward_penalty':.5,'upward_multiplier':1.5,'actual_source':'attachment2','forecast_source':'attachment3','pv_forecast_scale':pv_scale},'summary':summary,'representative_days':{r['date']:r for r in records if r['date'] in {d.isoformat() for d in reps}},'daily':records}
    dst=output or (paths.PROCESSED_DIR/'problem3_rolling_solution.json'); dst.parent.mkdir(parents=True,exist_ok=True); dst.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8'); return out

if __name__=='__main__':
    s=run()['summary']; print(json.dumps(s,ensure_ascii=False,indent=2))
