import os
import socket
import tempfile

from monitor.server.logs import JsonlTail
from monitor.server.settings import ServerSettings
from monitor.server.status import build_status, daemon_running, hook_markers, line_count


def short_sock():
    return os.path.join(tempfile.mkdtemp(prefix="am", dir="/tmp"), "m.sock")


def test_daemon_probe_sees_a_listening_socket_only():
    p = short_sock()
    assert daemon_running(p) is False
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(p)
    srv.listen(1)
    try:
        assert daemon_running(p) is True
    finally:
        srv.close()


def test_hook_markers_only_check_for_the_marker(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text('{"hooks": {"PreToolUse": [{"command": "py -m monitor.hook"}]}}')
    assert hook_markers(tmp_path) == {"claude": False, "codex": False, "claude_v1": True}
    (tmp_path / ".codex" / "hooks.json").write_text('{"command": "py -I -m monitor.live_hook --agent codex"}')
    assert hook_markers(tmp_path)["codex"] is True
    assert hook_markers(tmp_path / "no-such-home") == {"claude": False, "codex": False, "claude_v1": False}


def test_line_count_ignores_blank_lines_and_missing_files(tmp_path):
    p = tmp_path / "x.log"
    p.write_text("a\n\nb\n")
    assert line_count(p) == 2 and line_count(tmp_path / "none.log") == 0


def test_build_status_combines_everything(tmp_path):
    logs = tmp_path / "logs"
    logs.mkdir()
    (logs / "events.jsonl").write_text('{"ts": 1000}\n{"ts": 1500}\nbad\n')
    (logs / "daemon_errors.log").write_text('{"error": "RuntimeError"}\n')
    (logs / "spool.jsonl").write_text("{}\n{}\n")
    s = ServerSettings(root=tmp_path, logs_dir=logs, token="t", home=tmp_path / "home", socket_path=short_sock())
    events, incidents = JsonlTail(logs / "events.jsonl"), JsonlTail(logs / "incidents.jsonl")
    events.refresh()
    incidents.refresh()
    st = build_status(s, "live", events, incidents)
    assert st["daemon"]["running"] is False and st["last_event_ts"] == 1500.0
    assert (st["spool_backlog"], st["daemon_errors"], st["unreadable_lines"], st["source"]) == (2, 1, 1, "live")
