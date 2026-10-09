"""Add ground-truth class denominators to already recorded scores, preserving score provenance.
No model calls and no threshold/score changes. Dataset hash must match the recorded run.
"""
import hashlib
import json
import sys
from pathlib import Path
from monitor.dataset import load_labelled, split_by_trajectory

ROOT = Path(__file__).resolve().parents[1]

def main(paths):
    for name in paths:
        path=Path(name); result=json.loads(path.read_text())
        dataset=ROOT/'data/labelled'/result['provenance']['dataset']
        if hashlib.sha256(dataset.read_bytes()).hexdigest()!=result['provenance']['hashes']['dataset']:
            raise ValueError('Dataset changed; cannot add class totals to this measurement')
        dev,test=split_by_trajectory(load_labelled(dataset))
        actions=test if result['split']=='test' else dev
        for row in result['scorers'].values():
            row['n_pos_total']=sum(a.label==1 for a in actions)
            row['n_neg_total']=sum(a.label==0 for a in actions)
        result['provenance']['metadata_annotation']={'purpose':'Add total classes from the same hashed labels; scores and thresholds unchanged',
            'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
        path.write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main(sys.argv[1:])
