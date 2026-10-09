import json

from monitor.hook import install_hook, run_hook, uninstall_hook


def rules_file(tmp_path):
    p = tmp_path / "rules.json"
    p.write_text(json.dumps([{"id": "m", "pattern": "ALPHA_MARKER", "weight": 6}]))
    return p


def test_hook_logs_scored_row(tmp_path):
    log = tmp_path / "logs" / "live.jsonl"
    payload = {"session_id": "s1", "cwd": "/p", "tool_name": "Bash", "tool_input": {"command": "echo ALPHA_MARKER"}}
    assert run_hook(json.dumps(payload), log, rules_file(tmp_path)) == 0
    row = json.loads(log.read_text().splitlines()[0])
    assert row["rule_score"] == 6.0 and row["rule_hits"] == ["m"] and row["tool"] == "Bash"


def test_hook_exits_zero_on_garbage(tmp_path):
    assert run_hook("not json {", tmp_path / "missing" / "live.jsonl", tmp_path / "nope.json") == 0


def test_install_merges_existing_hooks_and_uninstall_restores(tmp_path):
    s = tmp_path / "settings.json"
    original = json.dumps({"model": "x", "hooks": {"PostToolUse": [{"matcher": "*", "hooks": []}]}}, indent=2)
    s.write_text(original)
    backup = install_hook(s, "/py -m monitor.hook")
    data = json.loads(s.read_text())
    assert data["model"] == "x" and "PostToolUse" in data["hooks"]
    assert data["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "/py -m monitor.hook"
    assert backup.read_text() == original
    uninstall_hook(s, backup)
    assert s.read_text() == original


def test_second_install_is_refused(tmp_path):
    s = tmp_path / "settings.json"
    install_hook(s, "/py -m monitor.hook")
    try:
        install_hook(s, "/py -m monitor.hook")
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "already installed" in str(e)


def test_install_creates_settings_when_missing(tmp_path):
    s = tmp_path / "settings.json"
    backup = install_hook(s, "/py -m monitor.hook")
    assert json.loads(s.read_text())["hooks"]["PreToolUse"]
    uninstall_hook(s, backup)
    assert not s.exists()


def test_hook_records_errors_without_failing(tmp_path):
    assert run_hook("not json {", tmp_path / "logs" / "live.jsonl", tmp_path / "nope.json") == 0
    error_log = tmp_path / "logs" / "hook_errors.log"
    assert error_log.exists()
    row = json.loads(error_log.read_text().splitlines()[0])
    assert row["error"] == "JSONDecodeError"


def test_uninstall_keeps_changes_made_after_install(tmp_path):
    s = tmp_path / "settings.json"
    user_hook = {"matcher": "Bash", "hooks": [{"type": "command", "command": "/usr/bin/true"}]}
    s.write_text(json.dumps({"model": "x", "hooks": {"PreToolUse": [user_hook]}}, indent=2))
    backup = install_hook(s, "/py -I -m monitor.hook")
    data = json.loads(s.read_text())
    data["theme"] = "dark"  # user edits settings while the hook is installed
    s.write_text(json.dumps(data, indent=2))
    uninstall_hook(s, backup)
    after = json.loads(s.read_text())
    assert after["theme"] == "dark" and after["model"] == "x"
    assert after["hooks"]["PreToolUse"] == [user_hook]
    assert "monitor.hook" not in s.read_text()
    saved = list(tmp_path.glob("settings.json.backup-before-uninstall-*"))
    assert len(saved) == 1 and json.loads(saved[0].read_text())["theme"] == "dark"


def test_uninstall_of_created_file_keeps_later_changes_and_drops_empty_containers(tmp_path):
    s = tmp_path / "settings.json"
    backup = install_hook(s, "/py -I -m monitor.hook")
    data = json.loads(s.read_text())
    data["theme"] = "dark"
    s.write_text(json.dumps(data, indent=2))
    uninstall_hook(s, backup)
    assert json.loads(s.read_text()) == {"theme": "dark"}


def test_install_saves_copy_of_what_it_wrote(tmp_path):
    s = tmp_path / "settings.json"
    backup = install_hook(s, "/py -I -m monitor.hook")
    installed = backup.with_name(backup.name.replace(".backup-", ".monitor-installed-"))
    assert installed.read_bytes() == s.read_bytes()


def test_hook_error_log_is_redacted(tmp_path, monkeypatch):
    import monitor.rules

    def boom(path):
        raise ValueError("bad sk_live_ABCDEFGHIJKLMNOPQRSTUV")

    monkeypatch.setattr(monitor.rules, "load_rules", boom)
    log = tmp_path / "logs" / "live.jsonl"
    payload = {"session_id": "s1", "cwd": "/p", "tool_name": "Bash", "tool_input": {"command": "ls"}}
    assert run_hook(json.dumps(payload), log, rules_file(tmp_path)) == 0
    err = (tmp_path / "logs" / "hook_errors.log").read_text()
    assert "ValueError" in err and "sk_live_" not in err


def test_main_exits_zero_on_invalid_utf8_stdin(tmp_path, monkeypatch):
    import io
    import sys

    import pytest

    import monitor.hook as hook

    monkeypatch.setattr(hook, "ROOT", tmp_path)  # keep logs out of the real logs/ dir
    raw = b'{"session_id": "s1", "tool_name": "Bash", "tool_input": {"command": "echo \xff\xfe"}}'
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw), encoding="utf-8"))
    with pytest.raises(SystemExit) as e:
        hook.main()
    assert e.value.code == 0
    row = json.loads((tmp_path / "logs" / "live.jsonl").read_text().splitlines()[0])
    assert row["tool"] == "Bash"


def test_hook_marks_missing_rules_instead_of_scoring_zero(tmp_path):
    log = tmp_path / "logs" / "live.jsonl"
    payload = {"session_id": "s1", "cwd": "/p", "tool_name": "Bash", "tool_input": {"command": "ls"}}
    assert run_hook(json.dumps(payload), log, tmp_path / "no-rules.json") == 0
    row = json.loads(log.read_text().splitlines()[0])
    assert row["rule_score"] is None and row["rules_missing"] is True and row["rule_hits"] == []
