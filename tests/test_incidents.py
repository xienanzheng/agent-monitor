from monitor.config import Config
from monitor.incidents import IncidentTracker


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def tracker(tmp_path, **cfg):
    sent, clock = [], Clock()
    t = IncidentTracker(Config(**cfg), out_path=tmp_path / "incidents.jsonl",
                        notifier=lambda title, body: sent.append((title, body)), clock=clock)
    return t, sent, clock


def test_below_threshold_opens_nothing(tmp_path):
    t, sent, _ = tracker(tmp_path)
    assert t.observe("codex", "sess-123456789", "other", 4.9, ["r1"], "why") is None
    assert not (tmp_path / "incidents.jsonl").exists() and sent == []


def test_signals_merge_within_window_and_split_after(tmp_path):
    t, sent, clock = tracker(tmp_path)
    a = t.observe("codex", "s1", "data_exfiltration", 6.0, ["r1"], "first")
    clock.t += 30
    b = t.observe("codex", "s1", "data_exfiltration", 7.0, ["r2", "r1"], "second")
    assert b.id == a.id and b.severity == 7.0 and b.signals == ["r1", "r2"] and b.action_count == 2
    assert b.latest_reason == "second"
    clock.t += 61
    c = t.observe("codex", "s1", "data_exfiltration", 6.0, ["r1"], "")
    assert c.id != a.id
    assert t.observe("codex", "s1", "privilege_escalation", 6.0, [], "x").id != c.id
    assert len((tmp_path / "incidents.jsonl").read_text().splitlines()) == 4


def test_notifies_on_new_high_and_on_rise_only_without_command_text(tmp_path):
    t, sent, _ = tracker(tmp_path)
    t.observe("claude_code", "abcdef123456", "data_exfiltration", 8.0, ["r1"], "curl to example.org")
    t.observe("claude_code", "abcdef123456", "data_exfiltration", 8.0, ["r1"], "again")
    t.observe("claude_code", "abcdef123456", "data_exfiltration", 9.0, ["r3"], "worse")
    assert len(sent) == 2
    title, body = sent[0]
    assert "HIGH" in title and "data_exfiltration" in body and "abcdef12" in body and "curl" not in title + body


def test_notifications_can_be_disabled_and_notifier_errors_are_swallowed(tmp_path):
    t, sent, _ = tracker(tmp_path, notify=False)
    t.observe("codex", "s1", "other", 9.0, [], "")
    assert sent == []

    def boom(title, body):
        raise RuntimeError("no osascript")

    t2 = IncidentTracker(Config(), notifier=boom, clock=lambda: 1.0)
    assert t2.observe("codex", "s1", "other", 9.0, [], "").severity == 9.0


def test_window_uses_event_time_when_given(tmp_path):
    t, _, clock = tracker(tmp_path)
    a = t.observe("codex", "s1", "data_exfiltration", 6.0, ["r1"], "first", at=1000)
    b = t.observe("codex", "s1", "data_exfiltration", 6.0, ["r1"], "second", at=1000 + 7200)
    assert clock.t == 1000.0 and b.id != a.id and b.opened == 8200
    c = t.observe("codex", "s1", "data_exfiltration", 7.0, ["r2"], "third", at=8230)
    assert c.id == b.id and (c.opened, c.updated, c.action_count) == (8200, 8230, 2)
