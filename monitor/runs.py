"""Scan and eval runs shared by the CLI and the dashboard's background jobs."""
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path


def rules_engine(root):
    from monitor.evaluate import rules_v2_scorer
    from monitor.features import load_features
    from monitor.rules import load_rules_v2
    root = Path(root)
    features_path = root / "rules" / "features.json"
    features = load_features(features_path) if features_path.exists() else []
    return rules_v2_scorer(load_rules_v2(root / "rules" / "rules.json"), features)


def run_scan(root, threshold: float, judge_sample: int = 0, judge_model: str = "qwen3:8b") -> dict:
    from monitor.evaluate import judge_scorer, max_scorer, sample_actions, scan_real, score_sample
    root = Path(root)
    path = root / "data" / "real" / "actions.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found: run `uv run monitor ingest` first")
    res = scan_real(path, rules_engine(root), threshold)
    if judge_sample > 0:
        from monitor.llm_judge import Judge
        scorer = max_scorer(rules_engine(root), judge_scorer(Judge(model=judge_model)))
        res["judge_sample"] = score_sample(sample_actions(path, judge_sample), scorer, threshold)
    res['provenance'] = {'created_at': datetime.now(timezone.utc).isoformat(), 'threshold': threshold,
        'source': 'ingested historical traffic', 'labels': 'unlabelled',
        'hashes': {name: hashlib.sha256(p.read_bytes()).hexdigest() for name,p in {
            'dataset':path, 'rules':root/'rules/rules.json', 'features':root/'rules/features.json'}.items() if p.exists()}}
    out = root / "results" / "real_scan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, indent=1))
    return res


def evaluation_scorers(root, no_judge=False, judge_model='qwen3:8b'):
    from monitor.evaluate import judge_scorer, max_scorer
    root = Path(root)
    scorers = {"rules": rules_engine(root)}
    if not no_judge:
        from monitor.llm_judge import Judge
        scorers[f"judge:{judge_model}"] = judge_scorer(Judge(model=judge_model))
        scorers["max(rules,judge)"] = max_scorer(scorers["rules"], scorers[f"judge:{judge_model}"])
        from monitor.config import load_config
        from monitor.evaluate import CascadeScorer
        from monitor.features import load_features
        from monitor.rules import load_rules_v2
        cfg = load_config(root / 'monitor.toml')
        features = load_features(root / 'rules/features.json') if (root / 'rules/features.json').exists() else []
        scorers['live_cascade'] = CascadeScorer(cfg, load_rules_v2(root/'rules/rules.json'), features)
    return scorers


def run_eval(root, labelled, no_judge: bool = False, judge_model: str = "qwen3:8b", final: bool = False,
             out=None, progress=None, scorers=None) -> dict:
    from monitor.dataset import load_labelled, split_by_trajectory
    from monitor.evaluate import evaluate
    root = Path(root)
    dev, test = split_by_trajectory(load_labelled(labelled))
    scorers = scorers if scorers is not None else evaluation_scorers(root, no_judge, judge_model)
    split = "test" if final else "dev"
    def digest(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).exists() else None
    from dataclasses import asdict
    from monitor.config import load_config
    cfg = load_config(root/'monitor.toml')
    hashes = {'dataset':digest(labelled), 'rules':digest(root/'rules/rules.json'),
              'features':digest(root/'rules/features.json'),
              **{f'prompt:{name}':digest(root/'prompts'/name) for name in ('judge.txt','triage.txt','gateway.txt')},
              'config':hashlib.sha256(json.dumps(asdict(cfg),sort_keys=True).encode()).hexdigest()}
    from monitor.health import ollama_health
    model_health = ollama_health() if not no_judge else {}
    from monitor.prompting import BASE_SCHEMA, VERDICT_SCHEMA, TRIAGE_SCHEMA
    hashes['response_schema'] = hashlib.sha256(json.dumps([BASE_SCHEMA,TRIAGE_SCHEMA,VERDICT_SCHEMA],sort_keys=True).encode()).hexdigest()
    for name in ('evaluate.py','cascade.py','core.py','prompting.py','llm_judge.py','inference.py','features.py','rules.py','redact.py','schema.py'):
        hashes[f'source:{name}'] = digest(root/'monitor'/name)
    result = {"schema_version":2, "split": split, "scorers": evaluate(dev, test if final else dev, scorers, progress=progress),
              'provenance': {'created_at':datetime.now(timezone.utc).isoformat(),'dataset':str(Path(labelled).name),
               'dataset_kind':'original_synthetic' if Path(labelled).name=='daily_monitor.jsonl' else 'user_supplied',
               'hashes':hashes,'threshold_source':'dev', 'context_actions':20,'judge_context_actions':5,
               'model_digests':model_health.get('digests',{}), 'models':[] if no_judge else sorted({judge_model,cfg.triage_model,cfg.gateway_model}),
               'config':asdict(cfg),'dev_trajectories':len({a.trajectory_id for a in dev}),
               'test_trajectories':len({a.trajectory_id for a in test})},
              'limitations':['Synthetic cases are regression evidence, not measured real-world safety.',
               'Operating thresholds are chosen on development data; achieved false-alarm rates may differ on test.',
               'Small class counts cannot establish reliable performance at 1% or 5% false-alarm rates.',
               'Classification metrics use assessed actions; incomplete assessments are reported separately.']}
    out = Path(out) if out is not None else root / "results" / "eval.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=1))
    return result
