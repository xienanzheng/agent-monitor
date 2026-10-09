import json

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from monitor.server.app import create_app  # noqa: E402
from monitor.server.settings import ServerSettings  # noqa: E402
from tests.test_server_logs import row  # noqa: E402

FAKE = "sk_live_ABCDEFGHIJKLMNOPQRSTUV"


def make(tmp_path):
    logs = tmp_path / "logs"
    (logs / "replay").mkdir(parents=True)
    events = [row(ts=1000, index=0, task=f"use key {FAKE}", text=f"echo {FAKE}"),
              row(ts=1010, index=1, final_severity=7.0, incident_id="inc-1", settled_by="gateway",
                  gateway={"score": 7.0, "reason": f"leaks {FAKE}", "reasoning": "1. a 2. b"})]
    (logs / "events.jsonl").write_text("".join(json.dumps(r) + "\n" for r in events))
    snap = {"id": "inc-1", "agent": "claude_code", "session_id": "s1", "category": "data_exfiltration",
            "opened": 1010, "updated": 1010, "severity": 7.0, "signals": ["alpha"], "action_count": 1,
            "latest_reason": f"leaks {FAKE}"}
    (logs / "incidents.jsonl").write_text(json.dumps(snap) + "\n")
    (logs / "replay" / "events.jsonl").write_text(json.dumps(row(agent="codex", session_id="demo")) + "\n")
    s = ServerSettings(root=tmp_path, logs_dir=logs, token="t0k", home=tmp_path / "home",
                       socket_path="/tmp/am-no-such-dir/m.sock", dist_dir=tmp_path / "dist")
    return TestClient(create_app(s), base_url="http://127.0.0.1:8765")


def test_sessions_and_session_actions_per_source(tmp_path):
    c = make(tmp_path)
    [s1] = c.get("/api/sessions").json()
    assert (s1["session_id"], s1["actions"], s1["max_severity"], s1["incidents"]) == ("s1", 2, 7.0, 1)
    assert [s["session_id"] for s in c.get("/api/sessions?source=replay").json()] == ["demo"]
    rows = c.get("/api/sessions/claude_code/s1/actions").json()
    assert [r["index"] for r in rows] == [0, 1] and rows[1]["gateway"]["reasoning"] == "1. a 2. b"


def test_incidents_latest_and_recent_filter(tmp_path):
    c = make(tmp_path)
    assert [i["id"] for i in c.get("/api/incidents").json()] == ["inc-1"]
    assert c.get("/api/incidents?recent_hours=24").json() == []


def test_events_tail_then_after(tmp_path):
    c = make(tmp_path)
    t = c.get("/api/events?tail=1").json()
    assert [r["index"] for r in t["rows"]] == [1]
    assert t["next"] == (tmp_path / "logs" / "events.jsonl").stat().st_size
    assert c.get(f"/api/events?after={t['next']}").json()["rows"] == []
    assert [r["index"] for r in c.get("/api/events?after=0&limit=1").json()["rows"]] == [0]
    assert t["file_id"] == (tmp_path / "logs" / "events.jsonl").stat().st_ino
    stale = c.get(f"/api/events?after={t['next']}&file_id={t['file_id'] + 1}").json()
    assert stale["reset"] is True and [r["index"] for r in stale["rows"]] == [0, 1]


def test_status_endpoint(tmp_path):
    st = make(tmp_path).get("/api/status").json()
    assert st["daemon"]["running"] is False and st["last_event_ts"] == 1010.0 and st["source"] == "live"
    assert st["hooks"] == {"claude": False, "codex": False, "claude_v1": False}


def test_unknown_source_is_400(tmp_path):
    c = make(tmp_path)
    for path in ("/api/sessions?source=prod", "/api/events?source=prod", "/api/status?source=prod"):
        assert c.get(path).status_code == 400


def test_no_secret_reaches_any_response(tmp_path):
    c = make(tmp_path)
    paths = ["/api/sessions", "/api/sessions/claude_code/s1/actions", "/api/incidents", "/api/events?tail=50",
             "/api/events?after=0", "/api/status"]
    bodies = [c.get(p).text for p in paths]
    assert all(FAKE not in b for b in bodies)
    assert any("[REDACTED:stripe_key]" in b for b in bodies)
