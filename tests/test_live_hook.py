import io
import json
import os
import socket
import sys
import tempfile
import threading

from monitor.live_hook import run_live_hook

FAKE = "sk_live_ABCDEFGHIJKLMNOPQRSTUV"
PRE = {"hook_event_name": "PreToolUse", "session_id": "s1", "cwd": "/p", "tool_name": "Bash",
       "tool_input": {"command": f"echo {FAKE}"}}


def short_sock():
    return os.path.join(tempfile.mkdtemp(prefix="am", dir="/tmp"), "m.sock")


def listen(path):
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(path)
    srv.listen(1)
    got = []

    def accept():
        conn, _ = srv.accept()
        with conn:
            buf = b""
            while chunk := conn.recv(65536):
                buf += chunk
        got.append(buf)
        srv.close()

    t = threading.Thread(target=accept, daemon=True)
    t.start()
    return got, t


def test_sends_redacted_event_to_daemon_socket(tmp_path):
    path = short_sock()
    got, t = listen(path)
    assert run_live_hook("claude", json.dumps(PRE), path, tmp_path / "spool.jsonl", tmp_path / "err.log") == 0
    t.join(2)
    ev = json.loads(got[0].decode())
    assert ev["event"] == "pre_tool" and FAKE not in got[0].decode() and "[REDACTED:stripe_key]" in ev["text"]
    assert not (tmp_path / "spool.jsonl").exists()


def test_spools_when_daemon_unreachable(tmp_path):
    spool = tmp_path / "logs" / "spool.jsonl"
    assert run_live_hook("codex", json.dumps(PRE), short_sock(), spool, tmp_path / "err.log") == 0
    row = json.loads(spool.read_text().splitlines()[0])
    assert row["agent"] == "codex" and FAKE not in spool.read_text()


def test_garbage_input_logs_redacted_error_and_exits_zero(tmp_path):
    err = tmp_path / "err.log"
    assert run_live_hook("claude", "not json {", short_sock(), tmp_path / "spool.jsonl", err) == 0
    assert json.loads(err.read_text().splitlines()[0])["error"] == "JSONDecodeError"


def test_ignored_event_sends_and_spools_nothing(tmp_path):
    spool = tmp_path / "spool.jsonl"
    assert run_live_hook("claude", json.dumps({"hook_event_name": "Notification"}), short_sock(), spool,
                         tmp_path / "e") == 0
    assert not spool.exists()


def test_main_prints_nothing_and_exits_zero(tmp_path, monkeypatch, capsys):
    import monitor.live_hook as lh
    monkeypatch.setattr(lh, "ROOT", tmp_path)
    monkeypatch.setattr(lh, "socket_path", short_sock)
    monkeypatch.setattr(sys, "argv", ["live_hook", "--agent", "claude"])
    payload = {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "prompt": "hi"}
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(payload).encode())))
    try:
        lh.main()
    except SystemExit as e:
        assert e.code == 0
    assert capsys.readouterr().out == ""
    assert (tmp_path / "logs" / "spool.jsonl").exists()
