"""Record a frozen inference revision without replacing earlier evaluation evidence."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import asdict

from monitor.runs import evaluation_scorers,run_eval

ROOT=Path(__file__).resolve().parents[1]


def freeze():
    paths=[ROOT/'data/labelled/daily_monitor.jsonl',ROOT/'data/labelled/daily_monitor.manifest.json',
           *sorted((ROOT/'prompts').glob('*.txt')),*sorted((ROOT/'rules').glob('*.json')),
           *sorted((ROOT/'monitor').rglob('*.py')),Path(__file__).resolve()]
    if (ROOT/'monitor.toml').exists():paths.append(ROOT/'monitor.toml')
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/f'inference-{stamp}'
    out.mkdir(parents=True,exist_ok=False)
    snapshot=freeze()
    (out/'frozen-inputs.json').write_text(json.dumps(snapshot,indent=2)+'\n')
    scorers=evaluation_scorers(ROOT)
    def progress(name,phase,i,n):print(f'{name}: {phase} {i}/{n}',flush=True)
    def annotate(result):
        result['limitations'].append('This fixed synthetic dataset has been evaluated before; this revision is a repeated regression measurement, not a newly unseen generalization study.')
        return result
    dev=annotate(run_eval(ROOT,ROOT/'data/labelled/daily_monitor.jsonl',out=out/'dev.json',progress=progress,scorers=scorers))
    (out/'dev.json').write_text(json.dumps(dev,indent=2)+'\n')
    print('DEVELOPMENT',json.dumps({k:{'metrics':v['metrics'],'coverage':v['coverage'],'judge_failures':v.get('judge_failures')} for k,v in dev['scorers'].items()}),flush=True)
    if freeze()!=snapshot:raise RuntimeError('Scoring inputs changed; refuse test recording')
    final=annotate(run_eval(ROOT,ROOT/'data/labelled/daily_monitor.jsonl',final=True,out=out/'test.json',progress=progress,scorers=scorers))
    if freeze()!=snapshot:raise RuntimeError('Scoring inputs changed during test recording')
    (out/'test.json').write_text(json.dumps(final,indent=2)+'\n')
    cascade=scorers['live_cascade']
    details=[{'key':list(key),'decision':asdict(value)} for key,value in cascade.details.items()]
    (out/'cascade-decisions.json').write_text(json.dumps(details,indent=2)+'\n')
    # A pointer supports review/promotion only after the run has completed.
    (ROOT/'results'/'inference-latest.json').write_text(json.dumps({'directory':str(out.relative_to(ROOT))})+'\n')
    print('TEST',json.dumps({k:{'metrics':v['metrics'],'coverage':v['coverage'],'judge_failures':v.get('judge_failures')} for k,v in final['scorers'].items()}),flush=True)
    print('OUTPUT',str(out),flush=True)


if __name__=='__main__':main()
