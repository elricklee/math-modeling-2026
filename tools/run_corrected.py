"""One command produces Q1 and all four causal scenarios with audit evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.CUMCM2026_C import io_attachments as io, paths
from src.CUMCM2026_C.dispatch import run
from src.CUMCM2026_C.export_results import export_scenario


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--questions',nargs='+',default=['2','3','4-2','4-3'])
    args=parser.parse_args()
    attachments=io.load_all()
    from src.CUMCM2026_C.write_base_results import build
    build(include_scenarios=False)
    results={}
    for question in args.questions:
        data=run(question,attachments=attachments)
        path=export_scenario(data)
        results[question]={'summary':data['summary'],'file':str(path.relative_to(paths.RESULTS_DIR)),
                           'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        print(question,json.dumps(data['summary'],ensure_ascii=False),flush=True)
    (paths.PROCESSED_DIR/'corrected_run_summary.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
