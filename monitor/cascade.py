"""Decision and LLM cascade: rules settle the clear cases, qwen3:4b triages the rest, qwen3:8b decides escalations."""
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

from monitor.categories import normalize_category
from monitor.features import CONTEXT_TAGS
from monitor.llm_judge import _http
from monitor.redact import redact

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
AUTHORIZATION = ("explicit", "implied", "unclear", "out_of_scope", "forbidden")
RECOVERABILITY = ("high", "medium", "low")
_DECODER = json.JSONDecoder()


@dataclass
class Verdict:
    score: float | None
    category: str = "other"
    authorization: str = "unclear"
    boundary: str = ""
    recoverability: str = "medium"
    confidence: float = 0.0
    reason: str = ""
    reasoning: str = ""
    model: str = ""
    latency_s: float = 0.0
    failed: bool = False
    error_code: str | None = None
    timing: dict = field(default_factory=dict)
    request_attempts: int = 0
    retry_errors: list = field(default_factory=list)


def _enum(value, allowed, default):
    v = str(value).strip().lower() if value is not None else ""
    return v if v in allowed else default


def _confidence(c) -> float:
    if isinstance(c, bool) or not isinstance(c, (int, float)) or not math.isfinite(c):
        return 0.0
    return max(0.0, min(1.0, float(c)))


def parse_verdict(text) -> Verdict:
    text = text or ""
    start = text.find("{")
    while start != -1:
        try:
            d, _ = _DECODER.raw_decode(text, start)
            if isinstance(d, dict):
                s = d["score"]
                if isinstance(s, bool) or not math.isfinite(float(s)):
                    raise ValueError("unusable score")
                r = d.get("reasoning", "")
                reasoning = " ".join(str(x) for x in r) if isinstance(r, list) else str(r)
                return Verdict(score=max(0.0, min(10.0, float(s))),
                               category=normalize_category(str(d.get("category", "")).strip().lower()),
                               authorization=_enum(d.get("authorization"), AUTHORIZATION, "unclear"),
                               boundary=str(d.get("boundary", ""))[:200],
                               recoverability=_enum(d.get("recoverability"), RECOVERABILITY, "medium"),
                               confidence=_confidence(d.get("confidence", 0.0)),
                               reason=str(d.get("reason", ""))[:1000], reasoning=reasoning[:2000])
        except (ValueError, KeyError, TypeError):
            pass
        start = text.find("{", start + 1)
    return Verdict(score=None, reason=f"unparseable reply: {text[:120]}", failed=True)


class LLMStage:
    def __init__(self, model, prompt_name, timeout, url="http://localhost:11434", transport=None):
        self.model, self.timeout, self.url = model, timeout, url.rstrip("/")
        self.prompt = (PROMPTS / prompt_name).read_text()
        self.is_triage = prompt_name == 'triage.txt'
        self.transport = transport or _http

    def judge(self, action, context, rule_result, tags) -> Verdict:
        t0 = time.monotonic()
        diagnostics = {}
        try:
            from monitor.prompting import evidence, grounded_policy, VERDICT_SCHEMA, TRIAGE_SCHEMA
            from monitor.inference import request, evidence_budget
            max_tokens = 220 if self.is_triage else 360
            schema = TRIAGE_SCHEMA if self.is_triage else VERDICT_SCHEMA
            policy = grounded_policy(self.prompt,schema)
            text, timings = request(self.transport, self.url, self.model, policy,
                evidence(action, context, rule_result.hits, tags, rule_result.score, rule_result.reasons,
                         max_bytes=evidence_budget(policy,max_tokens)),
                schema, self.timeout, max_tokens, diagnostics)
            v = parse_verdict(text)
            v.timing = timings
        except Exception as e:  # a judge failure must never look benign
            from monitor.inference import failure_code
            v = Verdict(score=None, reason=f"judge error: {e}", failed=True, error_code=failure_code(e))
        v.model, v.latency_s = self.model, round(time.monotonic() - t0, 3)
        v.request_attempts = diagnostics.get('request_attempts',0)
        v.retry_errors = diagnostics.get('retry_errors',[])
        v.reason, v.reasoning = redact(v.reason), redact(v.reasoning)
        return v


@dataclass
class Decision:
    final_severity: float
    settled_by: str
    triage: Verdict | None = None
    gateway: Verdict | None = None
    judge_failed: bool = False


class Cascade:
    def __init__(self, cfg, triage: LLMStage, gateway: LLMStage):
        self.cfg, self.triage, self.gateway = cfg, triage, gateway

    def route(self, rule_result, tags) -> str:
        if rule_result.score >= self.cfg.settle_high:
            return "rules_high"
        if rule_result.score <= self.cfg.settle_low and not (set(tags) - CONTEXT_TAGS):
            return "rules_low"
        return "triage"

    def judge(self, action, context, rule_result, tags, route) -> Decision:
        rs = rule_result.score
        if route == "rules_low":
            return Decision(rs, "rules_low")
        if route == "rules_high":
            g = self.gateway.judge(action, context, rule_result, tags)
            return Decision(rs, "rules_high", gateway=g, judge_failed=g.failed)
        t = self.triage.judge(action, context, rule_result, tags)
        if t.failed:
            g = self.gateway.judge(action, context, rule_result, tags)
            if g.failed:
                return Decision(rs, "triage", triage=t, gateway=g, judge_failed=True)
            return Decision(g.score, "gateway", triage=t, gateway=g)
        if t.score < self.cfg.escalate_at and t.confidence >= self.cfg.min_confidence:
            return Decision(t.score, "triage", triage=t)
        g = self.gateway.judge(action, context, rule_result, tags)
        if g.failed:  # an unsure triage that escalated must not settle below the rules
            return Decision(max(t.score, rs), "triage", triage=t, gateway=g, judge_failed=True)
        return Decision(g.score, "gateway", triage=t, gateway=g)

    def run(self, action, context, rule_result, tags) -> Decision:
        return self.judge(action, context, rule_result, tags, self.route(rule_result, tags))
