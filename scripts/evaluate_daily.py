"""Run development, freeze-check inputs, then one held-out evaluation. Reuse identical dev verdicts."""
import hashlib
import json
from pathlib import Path
from monitor.runs import evaluation_scorers, run_eval

ROOT=Path(__file__).resolve().parents[1]
FILES=[ROOT/'rules/rules.json', ROOT/'rules/features.json', *(ROOT/'prompts'/p for p in ['judge.txt','triage.txt','gateway.txt']),ROOT/'data/labelled/daily_monitor.jsonl', *(ROOT/'monitor'/p for p in ['evaluate.py','cascade.py','prompting.py','llm_judge.py','config.py','core.py'])]


def freeze():
    files = FILES + ([ROOT/'monitor.toml'] if (ROOT/'monitor.toml').exists() else [])
    return {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def main():
    before=freeze()
    scorers=evaluation_scorers(ROOT)
    def progress(name,phase,i,n):
        print(f'{name}: {phase} {i}/{n}',flush=True)
    dev=run_eval(ROOT,ROOT/'data/labelled/daily_monitor.jsonl',out=ROOT/'results/daily-dev.json',progress=progress,scorers=scorers)
    print('DEVELOPMENT',json.dumps({k:{'auc':v['auc'],'coverage':v['coverage'],'metrics':v['metrics']} for k,v in dev['scorers'].items()}),flush=True)
    if freeze()!=before:
        raise RuntimeError('Evaluation inputs changed; refuse held-out run')
    # No tuning after development. Cached verdicts carry their original latency.
    final=run_eval(ROOT,ROOT/'data/labelled/daily_monitor.jsonl',final=True,out=ROOT/'results/daily-test.json',progress=progress,scorers=scorers)
    (ROOT/'results/eval.json').write_text(json.dumps(final,indent=2)+'\n')
    print('HELD_OUT',json.dumps({k:{'auc':v['auc'],'coverage':v['coverage'],'metrics':v['metrics']} for k,v in final['scorers'].items()}),flush=True)


if __name__=='__main__':
    main()
