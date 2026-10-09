"""Live hook (v2) for Claude Code and Codex.

Normalizes and redacts the hook payload in this short-lived process, then sends one JSON line to the
monitor daemon over a Unix socket. If the daemon is unreachable, the event is spooled to logs/spool.jsonl.
Never prints (Claude Code adds UserPromptSubmit stdout to the model's context). Always exits 0."""
import json
import os
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOCKET = "~/.cache/agent-monitor/monitor.sock"


def socket_path() -> str:
    try:
        from monitor.config import load_config
        return load_config().socket_path
    except Exception:
        return DEFAULT_SOCKET


def send(line: bytes, sock_path: str, timeout: float = 0.2) -> bool:
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(os.path.expanduser(sock_path))
        s.sendall(line)
        return True
    except OSError:
        return False
    finally:
        s.close()


def run_live_hook(agent_flag, stdin_text, sock_path, spool_path, error_log) -> int:
    try:
        from monitor.events import normalize_event
        ev = normalize_event(agent_flag, json.loads(stdin_text))
        if ev is not None:
            line = (json.dumps(ev.to_dict()) + "\n").encode()
            if not send(line, sock_path):
                Path(spool_path).parent.mkdir(parents=True, exist_ok=True)
                with open(spool_path, "ab") as f:
                    f.write(line)
    except Exception as e:
        try:
            try:
                from monitor.redact import redact
                message = redact(str(e))[:500]
            except Exception:
                message = type(e).__name__
            Path(error_log).parent.mkdir(parents=True, exist_ok=True)
            with open(error_log, "a") as f:
                f.write(json.dumps({"ts": time.time(), "error": type(e).__name__, "message": message}) + "\n")
        except Exception:
            pass  # fail open: the monitor's failure must never become the agent's failure
    return 0


def main():
    args = sys.argv[1:]
    agent = args[args.index("--agent") + 1] if "--agent" in args[:-1] else "claude"
    try:
        stdin_text = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    except Exception:
        stdin_text = ""
    sys.exit(run_live_hook(agent, stdin_text, socket_path(), ROOT / "logs" / "spool.jsonl",
                           ROOT / "logs" / "hook_errors.log"))


if __name__ == "__main__":
    main()
