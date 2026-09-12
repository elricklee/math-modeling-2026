"""Independent full-output verification, without calling the planner or settler."""
from pathlib import Path
from datetime import date, timedelta
import hashlib
import json
import sys
import numpy as np
import openpyxl
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.CUMCM2026_C import paths, io_attachments as io


def verify():
    a1,a2,_a3,a4=io.load_all(); index={d.isoformat():i for i,d in enumerate(a2.dates)}
    output={};expected=[d.isoformat() for d in a2.dates if d>=date(2025,2,1)]
    for question in ('2','3','4-2','4-3'):
        source=paths.PROCESSED_DIR/f'problem{question.replace("-","_")}_corrected.json'
        data=json.loads(source.read_text(encoding='utf-8'));records=data['daily']
        assert [r['date'] for r in records]==expected
        residuals={'balance':0.,'soc':0.,'cross_day':0.,'settlement':0.,'xlsx':0.}
        prev=data['summary']['output_initial_soc_kwh']; totals=np.zeros(4)
        book=openpyxl.load_workbook(paths.result_path('result'+question),read_only=True,data_only=True)
        sheets={s.title:list(s.values) for s in book}
        assert len(sheets['充放电量'])==2005
        assert len(sheets['计划购电量'])==335
        assert sheets['计划购电量'][0][1]=='0:00-0:10'
        assert sheets['计划购电量'][0][144]=='23:50-0:00+1'
        emergency_totals={}
        for row in sheets['紧急购电量'][1:]:
            key=row[0].date().isoformat();emergency_totals[key]=emergency_totals.get(key,0.)+float(row[2])
        for ri,r in enumerate(records):
            i=index[r['date']]
            def a(k):return np.asarray(r[k],float)
            p0=a('plan_by_interval_kwh');p=a('purchase_by_interval_kwh');e=a('emergency_by_interval_kwh')
            c=a('charge_by_interval_kwh');d=a('discharge_by_interval_kwh');s=a('soc_kwh')
            g=a('curtail_by_interval_kwh');w=a('unused_by_interval_kwh')
            price=np.asarray(a4.price[i] if question.startswith('4') else a1.price.values)
            assert np.isfinite(np.r_[p0,p,e,c,d,s,g,w]).all()
            assert min(p0.min(),p.min(),e.min(),c.min(),d.min(),g.min(),w.min())>=-1e-6
            assert (c+d).max()<=5000/6+1e-6
            assert not np.any((c>1e-6)&(d>1e-6))
            assert s.min()>=1200-1e-6 and s.max()<=10800+1e-6
            assert np.max(g-a2.pv_actual[i]/6)<=1e-6 and np.max(w-p)<=1e-6
            bal=p-w+e+d+a2.pv_actual[i]/6-g-a2.load[i]/6-c
            rec=np.diff(s)-.9*c+d/.9
            residuals['balance']=max(residuals['balance'],float(abs(bal).max()))
            residuals['soc']=max(residuals['soc'],float(abs(rec).max()))
            residuals['cross_day']=max(residuals['cross_day'],abs(s[0]-prev));prev=s[-1]
            costs=np.array([price@p0,price@(1.5*np.maximum(p-p0,0)+.5*np.maximum(p0-p,0)),5*price@e])
            report=np.array([r[k] for k in ('plan_cost_yuan','adjustment_cost_yuan','emergency_cost_yuan')])
            residuals['settlement']=max(residuals['settlement'],float(abs(costs-report).max()),abs(costs.sum()-r['total_cost_yuan']))
            totals+=np.r_[costs,costs.sum()]
            for name,v in [('计划购电量',p0),('调整购电量',p)]:
                if name not in sheets:continue
                row=sheets[name][ri+1];assert row[0].date().isoformat()==r['date']
                delta=max(float(abs(np.array(row[1:145])-v).max()),abs(row[145]-v.sum()),abs(row[146]-price@v))
                residuals['xlsx']=max(residuals['xlsx'],delta)
            for b in range(6):
                row=sheets['充放电量'][ri*6+b+1]
                residuals['xlsx']=max(residuals['xlsx'],abs(row[2]-c[24*b:24*(b+1)].sum()),abs(row[3]-d[24*b:24*(b+1)].sum()))
                if b==0:
                    assert row[0].date().isoformat()==r['date']
                    residuals['xlsx']=max(residuals['xlsx'],abs(row[5]-s[0]))
                if b==1:residuals['xlsx']=max(residuals['xlsx'],abs(row[5]-s[-1]))
            assert abs(emergency_totals.get(r['date'],0.)-e.sum())<1e-5
        assert max(residuals.values())<1e-5,residuals
        for j,k in enumerate(('plan_cost_yuan','adjustment_cost_yuan','emergency_cost_yuan','total_cost_yuan')):
            assert abs(totals[j]-data['summary'][k])<1e-5
        output[question]={'passed':True,'days':len(records),'intervals':len(records)*144,
                          'residuals':residuals,'summary':data['summary']}
    inputs={str(p.relative_to(paths.RAW_DIR)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths.RAW_DIR.rglob('*.xlsx')}
    report={'scenarios':output,'input_sha256':inputs}
    (paths.PROCESSED_DIR/'independent_verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(output,ensure_ascii=False,indent=2))
    return report


if __name__=='__main__':verify()
