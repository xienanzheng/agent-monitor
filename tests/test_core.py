import json

from monitor.cascade import Cascade, LLMStage
from monitor.config import Config
from monitor.core import MonitorCore
from monitor.events import normalize_event
from monitor.incidents import IncidentTracker
from monitor.rules import ActionRule, SequenceRule

FAKE = "sk_live_ABCDEFGHIJKLMNOPQRSTUV"


class Fake:
    def __init__(self, score=7, **kw):
        self.calls = []
        self.reply = {"score": score, "confidence": 0.9, "category": "data_exfiltration",
                      "boundary": "local workspace", "recoverability": "medium", "authorization": "out_of_scope", "reason": "not asked for", **kw}

    def __call__(self, url, payload, timeout):
        self.calls.append(payload)
        return {"done": True, "done_reason": "stop", "message": {"content": json.dumps(self.reply)}}


RULES = [ActionRule(id="alpha", category="data_exfiltration", score=4.0, pattern="ALPHA_MARKER", add_tags=("alpha_seen",)),
         SequenceRule(id="alpha_then_beta", category="data_exfiltration", score=9.0, previous_tag="alpha_seen",
                      current_tag="beta_seen", within_actions=3),
         ActionRule(id="beta", category="other", score=1.0, pattern="BETA_MARKER", add_tags=("beta_seen",))]


def core(tmp_path, triage=None, gateway=None, sent=None):
    cfg = Config(notify=True)
    t, g = triage or Fake(score=2), gateway or Fake(score=7)
    cas = Cascade(cfg, LLMStage("qwen3:4b", "triage.txt", 20, transport=t), LLMStage("qwen3:8b", "gateway.txt", 60, transport=g))
    sink = sent if sent is not None else []
    inc = IncidentTracker(cfg, out_path=tmp_path / "incidents.jsonl", notifier=lambda a, b: sink.append((a, b)),
                          clock=lambda: 1000.0)
    return MonitorCore(cfg, list(RULES), [], cas, inc, events_path=tmp_path / "events.jsonl", clock=lambda: 1000.0), t, g


def ev(event, **kw):
    names = {"prompt": "UserPromptSubmit", "pre": "PreToolUse", "post": "PostToolUse", "start": "SessionStart",
             "end": "SessionEnd"}
    return normalize_event("claude", {"hook_event_name": names[event], "session_id": "s1", "cwd": "/p", **kw})


def bash(cmd, **kw):
    return ev("pre", tool_name="Bash", tool_input={"command": cmd}, **kw)


def rows(tmp_path):
    return [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]


def test_low_action_settles_immediately_and_records_task(tmp_path):
    c, t, g = core(tmp_path)
    assert c.ingest(ev("prompt", prompt="update the README")) is None
    assert c.ingest(bash("ls")) is None
    [r] = rows(tmp_path)
    assert (r["settled_by"], r["final_severity"], r["task"], r["index"]) == ("rules_low", 0.0, "update the README", 0)
    assert t.calls == [] and g.calls == []


def test_mid_action_is_queued_then_judged_with_task_context(tmp_path):
    c, t, g = core(tmp_path, triage=Fake(score=6), gateway=Fake(score=7))
    c.ingest(ev("prompt", prompt="update the README"))
    p = c.ingest(bash("echo ALPHA_MARKER"))
    assert p is not None and p.route == "triage" and not (tmp_path / "events.jsonl").exists()
    row = c.judge_and_finalize(p)
    assert row["settled_by"] == "gateway" and row["final_severity"] == 7.0 and row["category"] == "data_exfiltration"
    assert row["gateway"]["authorization"] == "out_of_scope" and row["incident_id"]
    assert "update the README" in t.calls[0]["messages"][-1]["content"]


def test_sequence_rule_fires_across_actions(tmp_path):
    sent = []
    c, _, _ = core(tmp_path, sent=sent)
    c.judge_and_finalize(c.ingest(bash("echo ALPHA_MARKER")))
    p = c.ingest(bash("echo BETA_MARKER"))
    assert p.route == "rules_high" and "alpha_then_beta" in p.rule_result.hits
    row = c.judge_and_finalize(p)
    assert row["final_severity"] == 9.0 and row["settled_by"] == "rules_high"
    assert sent and "ALPHA" not in sent[-1][0] + sent[-1][1]


def test_everything_written_is_redacted(tmp_path):
    c, _, _ = core(tmp_path)
    c.ingest(ev("prompt", prompt=f"use {FAKE}"))
    p = c.ingest(bash(f"echo {FAKE}"))
    assert "secret_marker" in p.tags
    c.judge_and_finalize(p)
    out = (tmp_path / "events.jsonl").read_text()
    if (tmp_path / "incidents.jsonl").exists():
        out += (tmp_path / "incidents.jsonl").read_text()
    assert FAKE not in out and "[REDACTED:stripe_key]" in out


def test_post_tool_secret_output_raises_tags_and_rescores(tmp_path):
    c, _, _ = core(tmp_path)
    c.rules = RULES + [ActionRule(id="leak", category="data_exfiltration", score=6.0, tags_any=("secret_in_output",))]
    c.ingest(bash("cat notes.txt", tool_use_id="t1"))
    c.ingest(ev("post", tool_name="Bash", tool_input={"command": "cat notes.txt"}, tool_use_id="t1",
                tool_output=f"key {FAKE}"))
    r = rows(tmp_path)
    assert r[-1]["settled_by"] == "rules_post" and r[-1]["final_severity"] == 6.0 and "secret_in_output" in r[-1]["tags"]


def test_session_end_forgets_session_and_idle_sessions_expire(tmp_path):
    c, _, _ = core(tmp_path)
    c.ingest(ev("prompt", prompt="task one"))
    c.ingest(ev("end", reason="other"))
    c.ingest(bash("ls"))
    assert rows(tmp_path)[-1]["task"] == ""
    c.ingest(ev("prompt", prompt="task two"))
    c.clock = lambda: 1000.0 + 7201
    c.ingest(bash("ls"))
    assert rows(tmp_path)[-1]["task"] == ""


def test_row_ts_is_event_time_and_scored_ts_is_finalize_time(tmp_path):
    c, _, _ = core(tmp_path)
    e = bash("echo ALPHA_MARKER")
    e.ts = 500.0
    p = c.ingest(e)
    c.clock = lambda: 900.0
    row = c.judge_and_finalize(p)
    assert (row["ts"], row["scored_ts"]) == (500.0, 900.0)


def test_stats_count_judging_failures_and_drops(tmp_path):
    def down(url, payload, timeout):
        raise TimeoutError("ollama down")

    c, _, _ = core(tmp_path, triage=down, gateway=down)
    row = c.judge_and_finalize(c.ingest(bash("echo ALPHA_MARKER")))
    assert (row["settled_by"], row["final_severity"], row["judge_failed"]) == ("triage", 4.0, True)
    dropped = c.finalize_dropped(c.ingest(bash("echo ALPHA_MARKER")))
    assert (dropped["settled_by"], dropped["final_severity"], dropped["judge_failed"]) == ("dropped", 4.0, True)
    assert (c.stats["judged"], c.stats["judge_failures"], c.stats["dropped"], c.stats["tool_actions"]) == (1, 2, 1, 2)


def test_spooled_events_hours_apart_open_separate_incidents(tmp_path):
    c, _, _ = core(tmp_path, triage=Fake(score=6), gateway=Fake(score=7))
    first, second = bash("echo ALPHA_MARKER"), bash("echo ALPHA_MARKER")
    first.ts, second.ts = 1000.0, 8200.0
    pending = [c.ingest(first), c.ingest(second)]
    a, b = [c.judge_and_finalize(p) for p in pending]
    assert a["incident_id"] and b["incident_id"] and a["incident_id"] != b["incident_id"]


def test_record_error_logs_redacted_line(tmp_path):
    c, _, _ = core(tmp_path)
    c.record_error(RuntimeError(f"failed on {FAKE}"), bash("ls"))
    [line] = (tmp_path / "daemon_errors.log").read_text().splitlines()
    row = json.loads(line)
    assert FAKE not in line and "[REDACTED:stripe_key]" in row["message"] and c.stats["errors"] == 1
    assert (row["error"], row["agent"], row["session_id"], row["event"]) == ("RuntimeError", "claude_code", "s1",
                                                                             "pre_tool")
