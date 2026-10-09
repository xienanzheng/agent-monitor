"""Local LLM judge via Ollama /api/chat. Transport is injectable for offline tests."""
import json
import math
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from monitor.redact import redact
from monitor.schema import Action

PROMPT = (Path(__file__).resolve().parent.parent / "prompts" / "judge.txt").read_text()
_DECODER = json.JSONDecoder()
# The judge only talks to localhost: never route it through HTTP(S)_PROXY from the environment.
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


@dataclass
class JudgeResult:
    score: float | None
    reason: str
    latency_s: float
    error_code: str | None = None
    timing: dict = field(default_factory=dict)
    request_attempts: int = 0
    retry_errors: list = field(default_factory=list)


def parse_judge_reply(text: str) -> tuple[float | None, str]:
    text = text or ""
    start = text.find("{")
    while start != -1:
        try:
            d, _ = _DECODER.raw_decode(text, start)
            if isinstance(d, dict):
                v = d["score"]
                if isinstance(v, bool) or not math.isfinite(float(v)):
                    raise ValueError(f"unusable score {v!r}")
                return max(0.0, min(10.0, float(v))), str(d.get("reason", ""))
        except (ValueError, KeyError, TypeError):
            pass
        start = text.find("{", start + 1)
    return None, f"unparseable reply: {text[:120]}"


def _http(url: str, payload: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with _OPENER.open(req, timeout=timeout) as r:
        return json.loads(r.read())


class Judge:
    def __init__(self, model="qwen3:8b", url="http://localhost:11434", timeout=60.0, transport=None):
        self.model, self.url, self.timeout, self.transport = model, url.rstrip("/"), timeout, transport or _http

    def score(self, action: Action, context: list[Action]) -> JudgeResult:
        from monitor.prompting import evidence, grounded_policy, BASE_SCHEMA
        from monitor.inference import request, failure_code, evidence_budget
        t0 = time.monotonic()
        error, timings = None, {}
        diagnostics = {}
        try:
            policy = grounded_policy(PROMPT,BASE_SCHEMA)
            text, timings = request(self.transport, self.url, self.model, policy,
                evidence(action, context,max_bytes=evidence_budget(policy,220)), BASE_SCHEMA, self.timeout, 220, diagnostics)
            score, reason = parse_judge_reply(text)
        except Exception as e:  # judge failure must never look like "benign"
            score, reason, error = None, f"judge error: {e}", failure_code(e)
        return JudgeResult(score, redact(reason), time.monotonic() - t0, error, timings,
                           diagnostics.get('request_attempts',0),diagnostics.get('retry_errors',[]))
