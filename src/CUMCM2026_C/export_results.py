"""Export full physical-day records; never wrap today's first value into tomorrow."""
from datetime import datetime
from pathlib import Path
import shutil
import numpy as np
import openpyxl
from . import paths, io_attachments as io


def clear_body(ws):
    for merged in list(ws.merged_cells.ranges):
        if merged.max_row > 1:
            ws.unmerge_cells(str(merged))
    if ws.max_row > 1:
        ws.delete_rows(2, ws.max_row-1)


def export_scenario(data, destination: Path|None=None):
    name='result'+data['model']['question']
    dest=destination or paths.result_path(name)
    dest.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(paths.RESULT_TEMPLATES[name],dest)
    book=openpyxl.load_workbook(dest)
    for ws in book:
        clear_body(ws)
    for ws in book:
        if ws.title in ('计划购电量','调整购电量'):
            for t in range(144):ws.cell(1,t+2,io.interval_label(t+1))
            ws.freeze_panes='B2'
        else:
            ws.freeze_panes='C2'
    for i,r in enumerate(data['daily']):
        day=datetime.fromisoformat(r['date']); price=np.asarray(r['price_by_interval'])
        for title,key in [('计划购电量','plan_by_interval_kwh'),('调整购电量','purchase_by_interval_kwh')]:
            if title not in book.sheetnames:continue
            v=np.asarray(r[key]);ws=book[title]
            ws.append([day,*v.tolist(),float(v.sum()),float(price@v)])
        ws=book['充放电量']
        c=np.asarray(r['charge_by_interval_kwh']);d=np.asarray(r['discharge_by_interval_kwh'])
        for b in range(6):
            clock='0:00' if b==0 else '24:00' if b==1 else None
            soc=r['soc_kwh'][0] if b==0 else r['soc_kwh'][-1] if b==1 else None
            ws.append([day if b==0 else None,f'{b*4}:00-{(b+1)*4}:00',float(c[24*b:24*(b+1)].sum()),float(d[24*b:24*(b+1)].sum()),clock,soc])
        em=np.asarray(r['emergency_by_interval_kwh'])
        for t,e in enumerate(em):
            if e>1e-8:book['紧急购电量'].append([day,io.interval_label(t+1),float(e)])
    for ws in book:
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                if isinstance(cell.value,datetime):cell.number_format='yyyy/mm/dd'
                elif isinstance(cell.value,(int,float)):cell.number_format='0.000000'
    book.save(dest)
    return dest
