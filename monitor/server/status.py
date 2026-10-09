"""Is monitoring on? Daemon socket probe, hook markers, spool backlog and error counts. Stdlib only, read-only."""
import json
import os
import socket
from pathlib import Path

from monitor.server.logs import num

MARK_V2 = "monitor.live_hook"
MARK_V1 = "monitor.hook"  # not a substring of MARK_V2


def daemon_running(socket_path, timeout: float = 0.2) -> bool:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(os.path.expanduser(str(socket_path)))
        return True
    except OSError:
        return False
    finally:
        s.close()


def daemon_health(socket_path, timeout=0.2):
    path = os.path.expanduser(str(socket_path))
    result = {'running': False, 'responsive': False, 'socket': path}
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(path)
        result['running'] = True
        sock.sendall(b'{"op":"health"}\n')
        reply = json.loads(sock.recv(8192))
        result['responsive'] = reply.get('ok') is True
        result['queue_depth'] = reply.get('queue_depth')
        result['stats'] = reply.get('stats')
    except (OSError, ValueError, AttributeError):
        pass
    finally:
        sock.close()
    return result


def _read(path) -> str:
    try:
        return Path(path).read_text(errors="replace")
    except OSError:
        return ""


def hook_markers(home) -> dict:
    """Only checks for the monitor's marker; never returns any settings content."""
    home = Path(home)
    claude = _read(home / ".claude" / "settings.json")
    codex = _read(home / ".codex" / "hooks.json")
    return {"claude": MARK_V2 in claude, "codex": MARK_V2 in codex, "claude_v1": MARK_V1 in claude}


def line_count(path) -> int:
    try:
        with open(path, "rb") as f:
            return sum(1 for line in f if line.strip())
    except OSError:
        return 0


def build_status(settings, source: str, events, incidents) -> dict:
    """events / incidents: already-refreshed JsonlTail objects for this source."""
    logs = Path(settings.logs_dir)
    last = max((num(r.get("ts")) for r in events.rows), default=None)
    from monitor.health import inspect_health
    from monitor.server.logs import JsonlTail
    from monitor.server.analysis import latest_actions
    live = events if source == "live" else JsonlTail(settings.source_dir("live") / "events.jsonl")
    if source != "live":
        live.refresh()
    return {
        "daemon": daemon_health(settings.socket_path),
        "hooks": hook_markers(settings.home),
        "last_event_ts": last,
        "spool_backlog": line_count(logs / "spool.jsonl") + line_count(logs / "spool.jsonl.draining"),
        "hook_errors": line_count(logs / "hook_errors.log"),
        "daemon_errors": line_count(settings.source_dir(source) / "daemon_errors.log"),
        "unreadable_lines": events.bad + incidents.bad,
        "source": source,
        "health": inspect_health(settings, latest_actions(live.rows)),
    }
