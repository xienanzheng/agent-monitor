"""Daemon pipeline without sockets: sessions, features, rules v2, cascade, incidents and outputs."""
import json
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from monitor.cascade import Decision
from monitor.features import extract_tags
from monitor.redact import redact
from monitor.rules import evaluate_rules
from monitor.schema import Action

CONTEXT_ACTIONS = 5
RECENT_ACTIONS = 20


def _event_ts(action, now: float) -> float:
    try:
        return float(action.ts)
    except (TypeError, ValueError):
        return now


@dataclass
class Session:
    task: str = ""
    cwd: str | None = None
    permission_mode: str = ""
    count: int = 0
    last_seen: float = 0.0
    recent: deque = field(default_factory=lambda: deque(maxlen=RECENT_ACTIONS))
    calls: dict = field(default_factory=dict)


@dataclass
class Pending:
    key: tuple
    action: Action
    context: list
    rule_result: object
    tags: set
    route: str
    state: dict = field(default_factory=dict)


class MonitorCore:
    def __init__(self, cfg, rules, features, cascade, incidents, events_path, clock=time.time, errors_path=None):
        self.cfg, self.rules, self.features = cfg, rules, features
        self.cascade, self.incidents = cascade, incidents
        self.events_path, self.clock = Path(events_path), clock
        self.errors_path = Path(errors_path) if errors_path is not None else \
            self.events_path.parent / "daemon_errors.log"
        self.sessions: dict[tuple, Session] = {}
        self._lock = threading.Lock()
        self.stats = {"events": 0, "tool_actions": 0, "judged": 0, "judge_failures": 0, "dropped": 0, "bad_lines": 0,
                      "errors": 0, "incomplete_assessments": 0}

    def _session(self, ev):
        now = self.clock()
        for k in [k for k, s in self.sessions.items() if now - s.last_seen > self.cfg.session_idle_s]:
            del self.sessions[k]
        key = (ev.agent, ev.session_id)
        s = self.sessions.get(key)
        if s is None:
            s = self.sessions[key] = Session()
        s.last_seen = now
        if ev.cwd:
            s.cwd = ev.cwd
        if ev.permission_mode:
            s.permission_mode = ev.permission_mode
        return key, s

    def ingest(self, ev) -> Pending | None:
        self.stats["events"] += 1
        if ev.event == "session_end":
            self.sessions.pop((ev.agent, ev.session_id), None)
            return None
        key, s = self._session(ev)
        if ev.event == "prompt":
            s.task = redact(ev.prompt)
            return None
        if ev.event == "post_tool":
            self._post_tool(key, s, ev)
            return None
        if ev.event != "pre_tool":
            return None
        self.stats["tool_actions"] += 1
        a = Action(agent=ev.agent, session_id=ev.session_id, index=s.count, tool=ev.tool_name, kind=ev.kind or "other",
                   text=redact(ev.text), ts=str(ev.ts), cwd=s.cwd, task=s.task,
                   policy={"permission_mode": s.permission_mode}, path=ev.path, tool_use_id=ev.tool_use_id)
        s.count += 1
        tags = extract_tags(a, self.features, permission_mode=s.permission_mode, path=ev.path)
        rr = evaluate_rules(a, tags, [e["tags"] for e in s.recent], self.rules)
        all_tags = tags | rr.added_tags
        context = [e["action"] for e in list(s.recent)[-CONTEXT_ACTIONS:]]
        entry = {"action": a, "tags": all_tags, "tool_use_id": ev.tool_use_id, "rule_score": rr.score,
                 "path": ev.path, "history": [e["tags"] for e in s.recent]}
        s.recent.append(entry)
        if ev.tool_use_id:
            s.calls[ev.tool_use_id] = entry
        p = Pending(key, a, context, rr, all_tags, self.cascade.route(rr, all_tags), entry)
        entry["pending"] = p
        entry["assessment_pending"] = p.route != "rules_low"
        if p.route == "rules_low":
            self.finalize(p, Decision(rr.score, "rules_low"))
            return None
        return p

    def _post_tool(self, key, s, ev) -> None:
        entries = list(s.recent)
        if ev.tool_use_id:
            e = s.calls.get(ev.tool_use_id)
        else:
            e = next((x for x in reversed(entries) if x["action"].tool == ev.tool_name), None)
        if e is None:
            return
        a = e["action"]
        a.output = redact(ev.output)
        a.outcome = ev.outcome
        new = extract_tags(a, self.features, permission_mode=s.permission_mode, path=e["path"]) - e["tags"]
        e["tags"].update(new)
        rr = evaluate_rules(a, e["tags"], e["history"], self.rules)
        e["tags"].update(rr.added_tags)
        p = e["pending"]
        p.tags = e["tags"]
        p.rule_result = rr
        if rr.score > e["rule_score"]:
            e["rule_score"] = rr.score
            prior = e.get("decision", Decision(rr.score, "pending"))
            self.finalize(p, replace(prior, final_severity=max(prior.final_severity, rr.score), settled_by="rules_post"), output_update=True)
        else:
            prior = e.get("decision", Decision(rr.score, "pending"))
            self.finalize(p, replace(prior, settled_by="output_update"), output_update=True)

    def record_error(self, exc, ev=None) -> None:
        """Count a processing error and log it (redacted) to daemon_errors.log. Never raises."""
        self.stats["errors"] += 1
        try:
            row = {"ts": self.clock(), "error": type(exc).__name__, "message": redact(str(exc))[:500],
                   "agent": getattr(ev, "agent", None), "session_id": getattr(ev, "session_id", None),
                   "event": getattr(ev, "event", None)}
            with self._lock:
                self.errors_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.errors_path, "a") as f:
                    f.write(json.dumps(row) + "\n")
        except Exception:
            pass  # error logging must never become a second error

    def judge_and_finalize(self, p: Pending) -> dict:
        d = self.cascade.judge(p.action, p.context, p.rule_result, p.tags, p.route)
        self.stats["judged"] += 1
        self.stats["judge_failures"] += sum(v.failed for v in (d.triage,d.gateway) if v is not None)
        self.stats["incomplete_assessments"] += int(d.judge_failed)
        return self.finalize(p, d)

    def finalize_dropped(self, p: Pending) -> dict:
        self.stats["dropped"] += 1
        self.stats["incomplete_assessments"] += 1
        return self.finalize(p, Decision(p.rule_result.score, "dropped", judge_failed=True))

    def finalize(self, p: Pending, d: Decision, *, output_update: bool = False) -> dict:
        a = p.action
        now = self.clock()
        with self._lock:
            prior = p.state.get("decision")
            if output_update and prior:
                # Inference may finish after the output handler reads its decision.
                # Preserve that completed verdict when writing the output revision.
                d = replace(prior, final_severity=max(prior.final_severity, d.final_severity), settled_by=d.settled_by)
            if prior and prior.final_severity > d.final_severity:
                d = replace(d, final_severity=prior.final_severity)
            if not output_update:
                p.state["assessment_pending"] = False
            p.state["decision"] = d
            ok = [v for v in (d.gateway, d.triage) if v is not None and not v.failed]
            matched = [r for r in self.rules if r.id in p.rule_result.hits]
            rule_category = max(matched, key=lambda r: r.score).category if matched else "other"
            category = next((v.category for v in ok if v.category != "other"), None) or rule_category
            reason = next((v.reason for v in ok if v.reason), "") or "; ".join(p.rule_result.reasons)
            action_id = f"{a.agent}|{a.session_id}|{a.index}|{a.ts}"
            inc = self.incidents.observe(a.agent, a.session_id, category, d.final_severity,
                                         list(p.rule_result.hits), reason, at=_event_ts(a, now), action_id=action_id)
            row = {"ts": _event_ts(a, now), "scored_ts": now, "agent": a.agent, "session_id": a.session_id, "index": a.index,
                   "tool": a.tool, "kind": a.kind, "text": redact(a.text)[:2000], "task": redact(a.task)[:300],
                   "tags": sorted(p.tags), "rule_score": p.rule_result.score, "rule_hits": list(p.rule_result.hits),
                   "rule_categories": list(p.rule_result.categories),
                   "rule_reasons": [redact(x)[:500] for x in p.rule_result.reasons],
                   "triage": asdict(d.triage) if d.triage else None,
                   "gateway": asdict(d.gateway) if d.gateway else None,
                   "final_severity": d.final_severity, "settled_by": d.settled_by, "judge_failed": d.judge_failed,
                   "category": category, "reason": redact(reason)[:500], "incident_id": inc.id if inc else None}
            row.update({"schema_version": 2, "action_id": action_id, "tool_use_id": a.tool_use_id,
                        "output": redact(a.output)[:1500], "outcome": a.outcome,
                        "coverage": "unknown_tool" if a.kind == "other" else "recognized",
                        "assessment_state": "pending" if p.state.get("assessment_pending") else
                            "incomplete" if d.judge_failed else "assessed"})
            self.events_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.events_path, "a") as f:
                f.write(json.dumps(row) + "\n")
        return row
