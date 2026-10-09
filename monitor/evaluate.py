import heapq
import json
import random
import statistics
import time
import math
from dataclasses import replace
from collections import defaultdict, deque

from monitor.features import extract_tags
from monitor.metrics import confusion, roc_auc, threshold_for_fpr, tpr_at_fpr
from monitor.redact import redact
from monitor.rules import evaluate_rules, score_rules
from monitor.schema import Action

CONTEXT_WINDOW = 20


def rules_scorer(rules):
    return lambda action, context: score_rules(action, rules)[0]


class RulesV2Scorer:
    """Rules v2 offline. Sequence rules see the previous actions the evaluation passes as context
    (at most CONTEXT_WINDOW); the live daemon keeps 20."""

    def __init__(self, rules, features):
        self.rules, self.features = rules, features
        self._tags: dict[tuple, set] = {}

    def _base_tags(self, a) -> set:
        return extract_tags(a, self.features, permission_mode=(a.policy or {}).get("permission_mode", ""), path=a.path)

    def _tags_for(self, a) -> set:
        key = (a.agent, a.session_id, a.index, a.text)
        if key not in self._tags:
            base = self._base_tags(a)
            self._tags[key] = base | evaluate_rules(a, base, [], self.rules).added_tags
        return self._tags[key]

    def __call__(self, action, context):
        history = [self._tags_for(c) for c in context]
        return evaluate_rules(action, self._base_tags(action), history, self.rules).score


def rules_v2_scorer(rules, features) -> RulesV2Scorer:
    return RulesV2Scorer(rules, features)


class JudgeScorer:
    """The LLM judge as a scorer. Each action is sent to the judge once (cached, so a combined
    monitor reuses the judge's score); `calls` and `failures` (score None) make outages visible."""

    def __init__(self, judge, k: int = CONTEXT_WINDOW):
        self.judge, self.k = judge, k
        self.calls = self.failures = 0
        self.inference_requests = self.inference_retries = 0
        self.cached_ms = 0.0  # judge time skipped by cache hits; _score_all adds it back to timings
        self._cache: dict[tuple, tuple[float | None, float]] = {}

    def __call__(self, action, context):
        key = (action.agent, action.session_id, action.index, action.text)
        if key in self._cache:
            score, ms = self._cache[key]
            self.cached_ms += ms
            return score
        t0 = time.perf_counter()
        result = self.judge.score(action, context[-self.k:])
        score = result.score
        self.inference_requests += result.request_attempts
        self.inference_retries += len(result.retry_errors)
        self._cache[key] = (score, (time.perf_counter() - t0) * 1000)
        self.calls += 1
        self.failures += score is None
        return score


def judge_scorer(judge, k: int = 5) -> JudgeScorer:
    return JudgeScorer(judge, k)


class CascadeScorer:
    """The live cascade policy with pre-tool assessment and post-tool rule evidence.

    Judge failures produce missing assessments, never a benign score. Rule-only evidence
    remains available in details for diagnosis. No tools described in the dataset are run.
    """
    def __init__(self, cfg, rules, features, cascade=None):
        from monitor.cascade import Cascade, LLMStage
        self.cfg = cfg
        self.engine = RulesV2Scorer(rules, features)
        self.cascade = cascade or Cascade(cfg, LLMStage(cfg.triage_model, 'triage.txt', cfg.triage_timeout_s),
                                         LLMStage(cfg.gateway_model, 'gateway.txt', cfg.gateway_timeout_s))
        self.calls = self.failures = 0
        self.inference_requests = self.inference_retries = 0
        self.cached_ms = 0.0
        self._cache, self.details = {}, {}

    def __call__(self, action, context):
        key = (action.agent, action.session_id, action.index, action.text)
        if key in self._cache:
            score, ms = self._cache[key]
            self.cached_ms += ms
            return score
        start = time.perf_counter()
        pre = replace(action, output='')
        tags = self.engine._base_tags(pre)
        history = [self.engine._tags_for(c) for c in context[-20:]]
        rr = evaluate_rules(pre, tags, history, self.engine.rules)
        decision = self.cascade.run(pre, context[-5:], rr, tags | rr.added_tags)
        verdicts = [v for v in (decision.triage, decision.gateway) if v is not None]
        self.calls += len(verdicts)
        self.failures += sum(v.failed for v in verdicts)
        self.inference_requests += sum(v.request_attempts for v in verdicts)
        self.inference_retries += sum(len(v.retry_errors) for v in verdicts)
        if action.output:
            post = evaluate_rules(action, self.engine._base_tags(action), history, self.engine.rules)
            if post.score > rr.score:
                decision.final_severity = max(decision.final_severity, post.score)
        score = None if decision.judge_failed else decision.final_severity
        self.details[key] = decision
        self._cache[key] = score, (time.perf_counter()-start)*1000
        return score


def max_scorer(*scorers):
    def combined(action, context):
        vals = [s for s in (f(action, context) for f in scorers) if s is not None]
        return max(vals) if vals else None
    combined.parts = scorers
    return combined


def _judges(scorer):
    return [s for s in (scorer, *getattr(scorer, "parts", ())) if isinstance(s, (JudgeScorer, CascadeScorer))]


def _judge_health(scorer) -> dict:
    js = _judges(scorer)
    return {"judge_calls": sum(j.calls for j in js), "judge_failures": sum(j.failures for j in js),
            "inference_requests":sum(j.inference_requests for j in js),
            "inference_retries":sum(j.inference_retries for j in js)} if js else {}


def _score_all(actions, scorer, progress=None):
    judges = _judges(scorer)
    history = defaultdict(list)
    out, times = [], []
    for i, a in enumerate(actions):
        skipped0 = sum(j.cached_ms for j in judges)
        t0 = time.perf_counter()
        key = (a.agent, a.session_id)
        out.append(scorer(a, history[key][-CONTEXT_WINDOW:]))
        # a cache hit is charged the judge's original latency, so timings reflect the live cost
        times.append((time.perf_counter() - t0) * 1000 + sum(j.cached_ms for j in judges) - skipped0)
        history[key].append(a)
        if progress:
            progress(i+1, len(actions))
    return out, times


def evaluate(dev, test, scorers, fprs=(0.01, 0.05), progress=None) -> dict:
    res = {}
    for name, scorer in scorers.items():
        callback = lambda phase: (lambda i,n: progress(name,phase,i,n)) if progress else None
        (d_s, _), (t_s, t_ms) = _score_all(dev, scorer, callback('dev')), _score_all(test, scorer, callback('evaluated'))
        d_y, t_y = [a.label for a in dev], [a.label for a in test]
        thr = threshold_for_fpr(d_s, d_y, 0.05)
        scored_y = [y for s, y in zip(t_s, t_y) if s is not None]
        points = {}
        for f in fprs:
            threshold = threshold_for_fpr(d_s, d_y, f)
            c = confusion(t_s, t_y, threshold) if threshold is not None else None
            points[str(f)] = {'threshold': threshold if threshold is not None and math.isfinite(threshold) else None,
                             'reject_all': threshold is not None and not math.isfinite(threshold),
                             'threshold_source': 'dev', 'actual_fpr': c['fpr'] if c else None,
                             'recall': c['recall'] if c else None,
                             'dev_negatives': sum(y == 0 for s, y in zip(d_s, d_y) if s is not None)}
        counts = confusion(t_s, t_y, thr) if thr is not None else None
        def metrics(c):
            return {'recall': c['recall'], 'precision': c['precision'], 'false_alarm_rate': c['fpr'],
                    'miss_rate': 1-c['recall'] if c['recall'] is not None else None} if c else None
        categories = {}
        for category in sorted({a.category or 'other' for a in test}):
            pairs = [(s,a.label) for s,a in zip(t_s,test) if (a.category or 'other') == category]
            c = confusion([p[0] for p in pairs], [p[1] for p in pairs], thr) if thr is not None else None
            categories[category] = {'n_actions':len(pairs),'n_scored':sum(s is not None for s,y in pairs),
                                    'confusion':c,'metrics':metrics(c)}
        res[name] = {"auc": roc_auc(t_s, t_y),
                     "tpr_at_fpr": {str(f): points[str(f)]['recall'] for f in fprs},
                     "threshold_at_5pct": thr if thr is not None and math.isfinite(thr) else None,
                     "test_confusion": counts,
                     "operating_points": points, "metrics": metrics(counts), "categories": categories,
                     "coverage": len(scored_y)/len(test) if test else None,
                     "n_incomplete": len(test)-len(scored_y),
                     "n_test": len(test), "n_scored": len(scored_y),
                     "n_pos": scored_y.count(1), "n_neg": scored_y.count(0),
                     "n_pos_total": t_y.count(1), "n_neg_total": t_y.count(0),
                     "median_latency_ms": round(statistics.median(t_ms), 3) if t_ms else None,
                     **_judge_health(scorer)}
    return res


def scan_real(path, scorer, threshold: float, top_n: int = 30) -> dict:
    history = defaultdict(lambda: deque(maxlen=CONTEXT_WINDOW))
    n, alerts, top, skipped = 0, 0, [], 0
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            try:
                a = Action.from_dict(json.loads(line))
            except (json.JSONDecodeError, TypeError, KeyError):
                skipped += 1
                continue
            key = (a.agent, a.session_id)
            s = scorer(a, list(history[key]))
            history[key].append(a)
            n += 1
            if s is not None and s >= threshold:
                alerts += 1
                item = (s, n, {"score": s, "agent": a.agent, "tool": a.tool, "text": redact(a.text)[:400]})
                heapq.heappush(top, item) if len(top) < top_n else heapq.heappushpop(top, item)
    return {"n_actions": n, "n_alerts": alerts, "alerts_per_1000": round(1000 * alerts / n, 2) if n else None,
            "top_alerts": [t[2] for t in sorted(top, key=lambda t: (-t[0], t[1]))], "n_skipped": skipped}


def sample_actions(path, n: int, seed: int = 0) -> list[Action]:
    """Reservoir-sample n actions from a JSONL file, streaming; malformed lines are skipped."""
    rng = random.Random(seed)
    sample: list[Action] = []
    seen = 0
    with open(path) as f:
        for line in f:
            if not line.strip():
                continue
            try:
                a = Action.from_dict(json.loads(line))
            except (json.JSONDecodeError, TypeError, KeyError):
                continue
            if len(sample) < n:
                sample.append(a)
            else:
                j = rng.randint(0, seen)
                if j < n:
                    sample[j] = a
            seen += 1
    return sample


def score_sample(actions, scorer, threshold: float, top_n: int = 30) -> dict:
    """Score a list of actions (no session context). None scores are counted but never alert."""
    scored, alerts, top = 0, 0, []
    for i, a in enumerate(actions):
        s = scorer(a, [])
        if s is None:
            continue
        scored += 1
        if s >= threshold:
            alerts += 1
            top.append((s, i, {"score": s, "agent": a.agent, "tool": a.tool, "text": redact(a.text)[:400]}))
    top.sort(key=lambda t: (-t[0], t[1]))
    return {"n_actions": len(actions), "n_scored": scored, "n_alerts": alerts,
            "alerts_per_1000": round(1000 * alerts / scored, 2) if scored else None,
            "top_alerts": [t[2] for t in top[:top_n]], **_judge_health(scorer)}
