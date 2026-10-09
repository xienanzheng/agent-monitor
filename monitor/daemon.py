"""Unix-socket daemon around MonitorCore: receives hook events, judges asynchronously, drains the spool."""
import asyncio
import fcntl
import json
import os
import socket
import stat
import time
from pathlib import Path

from monitor.events import HookEvent

MAX_SOCKET_PATH = 100  # macOS sun_path is 104 bytes including the terminator


def _socket_path_and_dir(sock_path) -> str:
    """Expand and check the socket path, and create its directory (0700) if needed. Never touches the path itself."""
    p = os.path.expanduser(str(sock_path))
    if not os.path.isabs(p):
        raise ValueError(f"socket path must be absolute: {sock_path}")
    if len(p.encode()) > MAX_SOCKET_PATH:
        raise ValueError(f"socket path too long for macOS ({len(p.encode())} > {MAX_SOCKET_PATH} bytes): {p}")
    d = os.path.dirname(p)
    if not os.path.isdir(d):  # only tighten a directory we create; never chmod an existing one like /tmp
        os.makedirs(d, mode=0o700)
        os.chmod(d, 0o700)  # makedirs' mode is filtered by the umask
    return p


def acquire_lock(lock_path) -> int:
    """Take an exclusive, non-blocking flock; the returned fd holds it until closed. The file is never deleted."""
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise RuntimeError(f"a monitor daemon is already running (lock held: {lock_path})") from None
    except BaseException:
        os.close(fd)
        raise
    return fd


def prepare_socket_path(sock_path) -> str:
    p = _socket_path_and_dir(sock_path)
    if os.path.lexists(p):
        if not stat.S_ISSOCK(os.lstat(p).st_mode):
            raise RuntimeError(f"{p} exists and is not a socket; refusing to remove it")
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        probe.settimeout(0.2)
        try:
            probe.connect(p)
        except OSError:
            os.unlink(p)  # stale file left by a crashed daemon: nobody is listening
        else:
            raise RuntimeError(f"a monitor daemon is already listening on {p}")
        finally:
            probe.close()
    return p


def parse_line(core, line) -> HookEvent | None:
    try:
        d = json.loads(line)
        if not isinstance(d, dict):
            raise ValueError("not a JSON object")
        return HookEvent.from_dict(d)
    except (ValueError, TypeError):
        core.stats["bad_lines"] += 1
        return None


def _process(core, ev, on_pending) -> None:
    """Rules run here; a judge-bound Pending goes to on_pending (judge now, or queue for the worker)."""
    try:
        p = core.ingest(ev)
        if p is not None:
            on_pending(p)
    except Exception as e:  # one bad event must not stop a replay or the spool drain
        core.record_error(e, ev)


def replay(core, path) -> dict:
    with open(path, errors="replace") as f:
        for line in f:
            if line.strip() and (ev := parse_line(core, line)) is not None:
                _process(core, ev, core.judge_and_finalize)
    return dict(core.stats)


REPLAY_OUTPUTS = ("events.jsonl", "incidents.jsonl", "daemon_errors.log")


def clear_replay_outputs(out_dir) -> None:
    """Remove a previous replay's output so a re-run doesn't double it (new files get a new inode, so an
    open dashboard resets cleanly)."""
    for name in REPLAY_OUTPUTS:
        (Path(out_dir) / name).unlink(missing_ok=True)


def shift_events_to_now(src, dest, now=None) -> Path:
    """Copy recorded hook events to `dest`, shifting every event's `ts` so the newest is `now` (for demos)."""
    now = time.time() if now is None else now
    rows = [json.loads(line) for line in Path(src).read_text().splitlines() if line.strip()]
    stamps = [r["ts"] for r in rows if isinstance(r, dict) and isinstance(r.get("ts"), (int, float))]
    shift = now - max(stamps) if stamps else 0.0
    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w") as f:
        for r in rows:
            if isinstance(r, dict) and isinstance(r.get("ts"), (int, float)):
                r["ts"] = r["ts"] + shift
            f.write(json.dumps(r) + "\n")
    return Path(dest)


def _drain_file(core, path, on_pending) -> int:
    n = 0
    with open(path, errors="replace") as f:
        for line in f:
            if line.strip() and (ev := parse_line(core, line)) is not None:
                _process(core, ev, on_pending)
                n += 1
    return n


def drain_spool(core, spool_path, on_pending=None) -> int:
    """Rename the spool before reading it, so hooks that spool meanwhile write a fresh file instead of losing lines
    to a truncate. A leftover .draining file (a drain interrupted by a crash) is processed first.

    on_pending=None judges each judge-bound event before moving on; the daemon passes its queue instead."""
    on_pending = core.judge_and_finalize if on_pending is None else on_pending
    spool = Path(spool_path)
    draining = spool.with_name(spool.name + ".draining")
    n = 0
    for _ in range(2):  # leftover first (if any), then the current spool; a third pass is the next start's job
        if not draining.exists():
            if not spool.exists():
                break
            os.replace(spool, draining)
        n += _drain_file(core, draining, on_pending)
        draining.unlink()
    return n


class Daemon:
    def __init__(self, core, sock_path, spool_path, queue_max=500):
        self.core, self.sock_path, self.spool_path, self.queue_max = core, sock_path, spool_path, queue_max
        self.queue = None
        self.server = None
        self.worker = None
        self.path = None
        self.drained = 0
        self.lock_fd = None
        self._bound = False  # only a daemon that bound the socket may unlink it

    async def start(self):
        p = _socket_path_and_dir(self.sock_path)
        # The lock comes before any probing or unlinking, so two daemons starting at once can't both pass the probe.
        self.lock_fd = acquire_lock(os.path.join(os.path.dirname(p), "monitor.lock"))
        self.path = prepare_socket_path(p)
        self.queue = asyncio.Queue()
        self.worker = asyncio.create_task(self._work())
        # Drain on the loop thread (sessions and ingest live here). Rules are fast; judging goes to the worker,
        # so startup never waits on the judges.
        n = drain_spool(self.core, self.spool_path, on_pending=self._enqueue)
        self.server = await asyncio.start_unix_server(self._handle, path=self.path, limit=1 << 20)
        self._bound = True
        os.chmod(self.path, 0o600)
        n += drain_spool(self.core, self.spool_path, on_pending=self._enqueue)  # spooled while we were binding
        self.drained = n

    async def _handle(self, reader, writer):
        try:
            while line := await reader.readline():
                if line.strip() == b'{"op":"health"}':
                    writer.write((json.dumps({'ok': True, 'queue_depth': self.queue.qsize(), 'stats': dict(self.core.stats)}) + '\n').encode())
                    await writer.drain()
                    continue
                if not line.strip() or (ev := parse_line(self.core, line)) is None:
                    continue
                try:  # one bad event (in ingest, or in finalize_dropped on overflow) must not end the connection
                    p = self.core.ingest(ev)
                    if p is not None:
                        self._enqueue(p)
                except Exception as e:
                    self.core.record_error(e, ev)
        except (ValueError, ConnectionError):  # over-long line or a client that went away
            self.core.stats["bad_lines"] += 1
        finally:
            writer.close()

    def _enqueue(self, p) -> None:
        oldest = None
        if self.queue.qsize() >= self.queue_max:
            oldest = self.queue.get_nowait()
            self.queue.task_done()  # every get is matched by task_done, or queue.join() never completes
        self.queue.put_nowait(p)
        if oldest is not None:  # after the put, so a failure here can't lose the new event as well
            self.core.finalize_dropped(oldest)

    async def _work(self):
        loop = asyncio.get_running_loop()
        while True:
            p = await self.queue.get()
            try:
                await loop.run_in_executor(None, self.core.judge_and_finalize, p)
            except Exception as e:  # a crash here would otherwise end the worker and silently stop all judging
                self.core.record_error(e, p.action)
            finally:
                self.queue.task_done()

    async def stop(self, grace_s: float = 5.0):
        if self.server is not None:
            self.server.close()
            await self.server.wait_closed()
        if self.queue is not None:
            try:
                await asyncio.wait_for(self.queue.join(), timeout=grace_s)
            except asyncio.TimeoutError:
                pass
        if self.worker is not None:
            self.worker.cancel()
        if self.queue is not None:
            while not self.queue.empty():
                p = self.queue.get_nowait()
                self.queue.task_done()
                self.core.finalize_dropped(p)
        if self._bound and os.path.lexists(self.path):
            os.unlink(self.path)
            self._bound = False
        if self.lock_fd is not None:  # release last, after our socket is gone
            os.close(self.lock_fd)
            self.lock_fd = None


async def run_daemon(core, sock_path, spool_path, queue_max=500):
    d = Daemon(core, sock_path, spool_path, queue_max)
    try:  # start inside the try, so stop() runs even when start fails or is interrupted
        await d.start()
        print(f"monitor daemon listening on {d.path} ({d.drained} spooled events processed; "
              f"judging continues in the background) (Ctrl-C to stop)", flush=True)
        await asyncio.Event().wait()
    finally:
        await d.stop()


def build_core(cfg, root, notifier=None, logs_dir=None):
    """logs_dir (default root/logs) holds events.jsonl, incidents.jsonl and daemon_errors.log."""
    from monitor.cascade import Cascade, LLMStage
    from monitor.core import MonitorCore
    from monitor.features import load_features
    from monitor.incidents import IncidentTracker, macos_notifier
    from monitor.rules import load_rules_v2

    root = Path(root)
    logs = Path(logs_dir) if logs_dir is not None else root / "logs"
    rules = load_rules_v2(root / "rules" / "rules.json")
    features_path = root / "rules" / "features.json"
    features = load_features(features_path) if features_path.exists() else []
    cascade = Cascade(cfg, LLMStage(cfg.triage_model, "triage.txt", cfg.triage_timeout_s),
                      LLMStage(cfg.gateway_model, "gateway.txt", cfg.gateway_timeout_s))
    incidents = IncidentTracker(cfg, out_path=logs / "incidents.jsonl",
                                notifier=notifier if notifier is not None else macos_notifier)
    return MonitorCore(cfg, rules, features, cascade, incidents, events_path=logs / "events.jsonl",
                       errors_path=logs / "daemon_errors.log")
