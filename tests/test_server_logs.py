import json
import os

from monitor.server.logs import (JsonlTail, LogStore, latest_incidents, read_after, read_tail, session_actions,
                                 summarize_sessions)


def row(**kw):
    base = {"ts": 1000.0, "scored_ts": 1000.0, "agent": "claude_code", "session_id": "s1", "index": 0, "tool": "Bash",
            "kind": "shell", "text": "ls", "task": "", "tags": [], "rule_score": 0.0, "rule_hits": [],
            "rule_categories": [], "triage": None, "gateway": None, "final_severity": 0.0, "settled_by": "rules_low",
            "judge_failed": False, "category": "other", "reason": "", "incident_id": None}
    return {**base, **kw}


def write(path, rows, extra=b""):
    path.write_bytes(b"".join(json.dumps(r).encode() + b"\n" for r in rows) + extra)


def test_tail_reads_only_new_complete_lines_and_counts_bad_ones(tmp_path):
    p = tmp_path / "events.jsonl"
    write(p, [row(index=0)], extra=b"not json\n" + b'{"partial": ')
    t = JsonlTail(p)
    assert [r["index"] for r in t.refresh()] == [0] and t.bad == 1
    with open(p, "ab") as f:
        f.write(b"1}\n" + json.dumps(row(index=1)).encode() + b"\n")
    assert [r.get("index") for r in t.refresh()] == [0, None, 1] and t.bad == 1


def test_tail_rereads_a_shrunk_or_replaced_file(tmp_path):
    p = tmp_path / "events.jsonl"
    write(p, [row(index=0), row(index=1)])
    t = JsonlTail(p)
    assert len(t.refresh()) == 2
    write(p, [row(index=7)])
    assert [r["index"] for r in t.refresh()] == [7]
    p.unlink()
    assert t.refresh() == []


def test_read_after_pages_by_byte_offset_and_resets_when_the_file_shrinks(tmp_path):
    p = tmp_path / "events.jsonl"
    write(p, [row(index=i) for i in range(3)])
    first = read_after(p, 0, limit=2)
    assert [r["index"] for r in first["rows"]] == [0, 1] and not first["reset"]
    second = read_after(p, first["next"], limit=10)
    assert [r["index"] for r in second["rows"]] == [2] and second["next"] == p.stat().st_size
    assert read_after(p, second["next"])["rows"] == []
    write(p, [row(index=9)])
    again = read_after(p, second["next"])
    assert again["reset"] and [r["index"] for r in again["rows"]] == [9]


def test_read_tail_returns_last_rows_and_the_end_offset(tmp_path):
    p = tmp_path / "events.jsonl"
    write(p, [row(index=i) for i in range(5)], extra=b'{"cut')
    t = read_tail(p, 2)
    assert [r["index"] for r in t["rows"]] == [3, 4]
    assert t["next"] == p.stat().st_size - len(b'{"cut')
    assert read_tail(tmp_path / "missing.jsonl", 5) == {"rows": [], "next": 0, "reset": False, "file_id": None}


def test_read_after_resets_when_the_file_was_replaced_by_a_larger_one(tmp_path):
    p = tmp_path / "events.jsonl"
    write(p, [row(index=i) for i in range(3)])
    first = read_after(p, 0)
    replacement = tmp_path / "new.jsonl"
    write(replacement, [row(index=10 + i) for i in range(10)])
    os.replace(replacement, p)
    again = read_after(p, first["next"], file_id=first["file_id"])
    assert again["reset"] and [r["index"] for r in again["rows"]][:3] == [10, 11, 12]
    assert again["file_id"] == p.stat().st_ino != first["file_id"]


def test_summarize_sessions():
    rows = [row(ts=1000, index=0, task="fix the tests", final_severity=1.0),
            row(ts=1010, index=1, final_severity=7.0, incident_id="inc-1", settled_by="gateway"),
            row(ts=1010, index=1, final_severity=8.0, settled_by="rules_post", incident_id="inc-1"),
            row(agent="codex", session_id="c1", ts=2000, task="add docs")]
    out = summarize_sessions(rows)
    assert [s["session_id"] for s in out] == ["c1", "s1"]
    s1 = out[1]
    assert (s1["actions"], s1["max_severity"], s1["incidents"], s1["task"], s1["first_ts"], s1["last_ts"]) == \
        (2, 8.0, 1, "fix the tests", 1000.0, 1010.0)


def test_session_actions_puts_rescored_rows_under_their_action():
    rows = [row(ts=1010, index=1, settled_by="rules_post"), row(ts=1000, index=0),
            row(ts=1010, index=1, settled_by="gateway"), row(session_id="other")]
    out = session_actions(rows, "claude_code", "s1")
    assert [(r["index"], r["settled_by"]) for r in out] == [(0, "rules_low"), (1, "gateway"), (1, "rules_post")]


def test_latest_incidents_keeps_the_last_snapshot_and_filters_recent():
    snaps = [{"id": "a", "severity": 6, "updated": 1000}, {"id": "b", "severity": 9, "updated": 500},
             {"id": "a", "severity": 7, "updated": 1100}]
    assert [(i["id"], i["severity"]) for i in latest_incidents(snaps)] == [("b", 9), ("a", 7)]
    assert [i["id"] for i in latest_incidents(snaps, recent_hours=1, now=1100 + 3600)] == ["a"]


def test_log_store_reuses_one_tail_per_file(tmp_path):
    store = LogStore()
    assert store.tail(tmp_path / "x.jsonl") is store.tail(tmp_path / "x.jsonl")
