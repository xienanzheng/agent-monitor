import json
from pathlib import Path

import pytest

from monitor.install import (CLAUDE_EVENTS, CODEX_EVENTS, install_hooks, install_live_hooks, live_hook_command,
                             settings_path_for, uninstall_hooks)

CMD = '"/v/bin/python" -I -m monitor.live_hook --agent claude'


def test_command_uses_isolated_venv_python_and_agent_flag():
    assert live_hook_command(Path("/a b"), "codex") == '"/a b/.venv/bin/python" -I -m monitor.live_hook --agent codex'


def test_settings_paths():
    assert settings_path_for("claude", Path("/h")) == Path("/h/.claude/settings.json")
    assert settings_path_for("codex", Path("/h")) == Path("/h/.codex/hooks.json")


def test_install_registers_every_event_and_keeps_existing_hooks(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text(json.dumps({"model": "x", "hooks": {"PreToolUse": [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "other"}]}]}}))
    install_hooks(s, CMD, CLAUDE_EVENTS)
    d = json.loads(s.read_text())
    assert d["model"] == "x" and set(CLAUDE_EVENTS) <= set(d["hooks"])
    pre = d["hooks"]["PreToolUse"]
    assert pre[0]["hooks"][0]["command"] == "other"
    assert pre[1]["matcher"] == "*" and pre[1]["hooks"][0]["command"] == CMD
    assert "matcher" not in d["hooks"]["UserPromptSubmit"][0]


def test_codex_session_end_timeout_is_short(tmp_path):
    s = tmp_path / "hooks.json"
    install_hooks(s, CMD, CODEX_EVENTS)
    assert json.loads(s.read_text())["hooks"]["SessionEnd"][0]["hooks"][0]["timeout"] == 1


def test_second_install_is_refused(tmp_path):
    s = tmp_path / "settings.json"
    install_hooks(s, CMD, CLAUDE_EVENTS)
    with pytest.raises(RuntimeError, match="already installed"):
        install_hooks(s, CMD, CLAUDE_EVENTS)


def test_uninstall_restores_exactly_or_removes_only_our_commands(tmp_path):
    s = tmp_path / "settings.json"
    original = json.dumps({"hooks": {"PreToolUse": [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": "other"}]}]}}, indent=2)
    s.write_text(original)
    b = install_hooks(s, CMD, CLAUDE_EVENTS)
    assert uninstall_hooks(s, b) is None and s.read_text() == original
    b = install_hooks(s, CMD, CLAUDE_EVENTS)
    d = json.loads(s.read_text())
    d["theme"] = "dark"
    s.write_text(json.dumps(d))
    saved = uninstall_hooks(s, b)
    after = json.loads(s.read_text())
    assert saved is not None and after["theme"] == "dark" and "monitor.live_hook" not in s.read_text()
    assert after["hooks"] == {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "other"}]}]}


def test_uninstall_of_created_file_removes_it(tmp_path):
    s = tmp_path / "hooks.json"
    b = install_hooks(s, CMD, CODEX_EVENTS)
    assert uninstall_hooks(s, b) is None and not s.exists()


def test_install_live_hooks_needs_venv_and_installs_both(tmp_path):
    root, home = tmp_path / "proj", tmp_path / "home"
    with pytest.raises(SystemExit, match="uv sync"):
        install_live_hooks(root, "both", home)
    (root / ".venv" / "bin").mkdir(parents=True)
    (root / ".venv" / "bin" / "python").write_text("")
    done = install_live_hooks(root, "both", home)
    assert [a for a, _, _ in done] == ["claude", "codex"]
    assert "--agent codex" in (home / ".codex" / "hooks.json").read_text()


def test_both_is_refused_up_front_when_one_agent_is_already_installed(tmp_path):
    root, home = tmp_path / "proj", tmp_path / "home"
    (root / ".venv" / "bin").mkdir(parents=True)
    (root / ".venv" / "bin" / "python").write_text("")
    install_live_hooks(root, "codex", home)
    with pytest.raises(RuntimeError, match="nothing was changed"):
        install_live_hooks(root, "both", home)
    assert not (home / ".claude" / "settings.json").exists()


def test_both_is_refused_up_front_when_a_target_is_malformed(tmp_path):
    root, home = tmp_path / "proj", tmp_path / "home"
    (root / ".venv" / "bin").mkdir(parents=True)
    (root / ".venv" / "bin" / "python").write_text("")
    (home / ".codex").mkdir(parents=True)
    (home / ".codex" / "hooks.json").write_text("{not json")
    with pytest.raises(RuntimeError, match="nothing was changed"):
        install_live_hooks(root, "both", home)
    assert not (home / ".claude" / "settings.json").exists()
    assert (home / ".codex" / "hooks.json").read_text() == "{not json"
