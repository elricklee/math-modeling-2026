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


# 官方模板口径（write_plan_columns mode="template"，A18 单一事实来源）：
# 表头逐字符沿用附件5 原样（0:10-0:20 … 0:00-0:10+1，含 7:0-7:10 瑕疵）；
# 第 i 个数据位装区间 i+1 的值，末列为次日首区间（12/31 置 0，表注声明）；
# 全天购电量/购电费仍是当日 144 区间的真实合计（区间1 只进汇总，无独立列）。
_TEMPLATE_COLS: list[str] = [lab for _, lab in io.write_plan_columns("template")]


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
            for t in range(144):ws.cell(1,t+2,_TEMPLATE_COLS[t])
            ws.freeze_panes='B2'
        else:
            ws.freeze_panes='C2'
    daily=data['daily']
    for i,r in enumerate(daily):
        day=datetime.fromisoformat(r['date']); price=np.asarray(r['price_by_interval'])
        nxt=daily[i+1] if i+1<len(daily) else None
        for title,key in [('计划购电量','plan_by_interval_kwh'),('调整购电量','purchase_by_interval_kwh')]:
            if title not in book.sheetnames:continue
            v=np.asarray(r[key]);ws=book[title]
            tail=float(np.asarray(nxt[key])[0]) if nxt is not None else 0.0
            ws.append([day,*v[1:].tolist(),tail,float(v.sum()),float(price@v)])
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
