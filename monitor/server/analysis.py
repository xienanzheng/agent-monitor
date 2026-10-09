"""Aggregate observed evidence once per action; updates cannot inflate denominators."""
import statistics
import time
from collections import Counter
from monitor.server.logs import num


def action_key(row):
    return row.get('action_id') or (row.get('agent'), row.get('session_id'), row.get('index'), row.get('ts'))


def latest_actions(rows):
    latest = {}
    for r in rows:
        key = action_key(r)
        previous = latest.get(key, {})
        merged = {**previous, **r}
        merged['final_severity'] = max(num(previous.get('final_severity')), num(r.get('final_severity')))
        latest[key] = merged
    return list(latest.values())


def build_analysis(rows, source, threshold=5, now=None):
    now = time.time() if now is None else now
    sel = latest_actions(rows)
    if source == 'live':
        sel = [r for r in sel if num(r.get('ts')) >= now - 86400]
    flagged = [r for r in sel if num(r.get('final_severity')) >= threshold]
    incomplete = [r for r in sel if r.get('assessment_state') == 'incomplete' or r.get('judge_failed')]
    pending = [r for r in sel if r.get('assessment_state') == 'pending' and not r.get('judge_failed')]
    latency = [sum(num(r.get(stage, {}).get('latency_s')) for stage in ('triage', 'gateway') if isinstance(r.get(stage), dict))
               for r in sel if any(isinstance(r.get(stage), dict) for stage in ('triage', 'gateway'))]
    stages = [r[stage] for r in sel for stage in ('triage','gateway') if isinstance(r.get(stage),dict)]
    failures = Counter(v.get('error_code') or ('timeout' if 'timed out' in v.get('reason','') else 'legacy_unknown')
                       for v in stages if v.get('failed'))
    recovered = sum(any(isinstance(r.get(s),dict) and r[s].get('failed') for s in ('triage','gateway'))
                    and r.get('assessment_state') == 'assessed' and not r.get('judge_failed') for r in sel)
    retried = sum(any(isinstance(r.get(s),dict) and r[s].get('retry_errors') for s in ('triage','gateway')) for r in sel)
    return {'source': source, 'window': {'hours': 24 if source == 'live' else None, 'end_ts': now},
            'actions': len(sel), 'flagged': len(flagged), 'incomplete': len(incomplete),
            'pending': len(pending), 'assessed': len(sel) - len(incomplete) - len(pending), 'threshold': threshold,
            'unknown_tools': sum(r.get('coverage') == 'unknown_tool' for r in sel),
            'categories': dict(Counter(r.get('category', 'other') for r in flagged)),
            'judging': {'actions': len(latency), 'median_latency_s': statistics.median(latency) if latency else None,
                        'stage_attempts':len(stages), 'failures':dict(failures), 'recovered_actions':recovered,
                        'request_attempts':sum(v.get('request_attempts',1) for v in stages), 'retried_actions':retried}}
