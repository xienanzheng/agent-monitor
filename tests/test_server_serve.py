import json
import shutil
import socket
from pathlib import Path

import pytest

from monitor.server.serve import port_free, preflight

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"


def test_preflight_explains_a_missing_build(tmp_path):
    pytest.importorskip("fastapi")
    with pytest.raises(SystemExit, match="npm --prefix dashboard"):
        preflight(tmp_path, 8765)


def test_port_in_time_wait_counts_as_free():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    cli = socket.create_connection(("127.0.0.1", port))
    conn, _ = srv.accept()
    conn.close()  # server side closes first -> its end of the connection enters TIME_WAIT
    cli.close()
    srv.close()
    assert port_free(port) is True


def test_preflight_explains_a_busy_port(tmp_path):
    pytest.importorskip("fastapi")
    (tmp_path / "dashboard" / "dist").mkdir(parents=True)
    (tmp_path / "dashboard" / "dist" / "index.html").write_text("x")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    port = s.getsockname()[1]
    try:
        assert port_free(port) is False
        with pytest.raises(SystemExit, match=f"--port {port + 1}"):
            preflight(tmp_path, port)
    finally:
        s.close()


def test_a_test_home_also_scopes_the_daemon_socket(tmp_path):
    from monitor.server.serve import build_settings
    s = build_settings(tmp_path, 8799, tmp_path / "logs", "t", home=tmp_path / "home")
    assert s.socket_path == str(tmp_path / "home" / ".cache" / "agent-monitor" / "monitor.sock")
    assert s.home == tmp_path / "home"


def test_cli_has_serve_with_its_options(capsys):
    from monitor.cli import main
    with pytest.raises(SystemExit) as e:
        main(["serve", "--help"])
    out = capsys.readouterr().out
    assert e.value.code == 0 and "--port" in out and "--logs-dir" in out and "--open" in out


def test_demo_events_load_through_the_api(tmp_path):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from monitor.server.app import create_app
    from monitor.server.settings import ServerSettings
    logs = tmp_path / "logs"
    shutil.copytree(FIX / "demo_events", logs)
    s = ServerSettings(root=tmp_path, logs_dir=logs, token="t", home=tmp_path / "home", dist_dir=tmp_path / "dist")
    c = TestClient(create_app(s), base_url="http://127.0.0.1:8765")
    assert {x["session_id"] for x in c.get("/api/sessions").json()} == {"demo-claude-1", "demo-codex-1"}
    [inc] = c.get("/api/incidents").json()
    assert inc["severity"] == 7.0 and inc["category"] == "data_exfiltration"
    rows = c.get("/api/sessions/claude_code/demo-claude-1/actions").json()
    assert [r["index"] for r in rows] == [0, 1, 2] and rows[2]["gateway"]["authorization"] == "out_of_scope"


def test_demo_session_replays_cleanly(tmp_path):
    from monitor.daemon import replay
    from tests.test_core import core
    c, _, _ = core(tmp_path)
    stats = replay(c, FIX / "demo_session.jsonl")
    assert (stats["bad_lines"], stats["errors"], stats["tool_actions"]) == (0, 0, 4)
    rows = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    from monitor.server.analysis import latest_actions
    assert len(latest_actions(rows)) == 4
    assert any("1 failed, 12 passed" in r.get("output", "") for r in rows)
