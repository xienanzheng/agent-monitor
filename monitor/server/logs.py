"""Read-only, incremental readers for the daemon's JSONL logs, and the views the dashboard builds from them.
Only complete lines are consumed: the daemon may be mid-write. Stdlib only."""
import json
import math
import threading
import time
from pathlib import Path


def num(x, default: float = 0.0) -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v if math.isfinite(v) else default


def _parse(line: bytes):
    try:
        row = json.loads(line)
    except ValueError:
        return None
    return row if isinstance(row, dict) else None


class JsonlTail:
    """Caches a JSONL file's rows, reading only bytes appended since the last refresh.
    A shrunk or replaced file is re-read from the start; a missing file is empty."""

    def __init__(self, path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._reset()

    def _reset(self) -> None:
        self.rows, self.offset, self.bad, self._ino = [], 0, 0, None

    def refresh(self) -> list:
        with self._lock:
            try:
                st = self.path.stat()
            except FileNotFoundError:
                self._reset()
                return self.rows
            if st.st_size < self.offset or (self._ino is not None and st.st_ino != self._ino):
                self._reset()
            self._ino = st.st_ino
            if st.st_size > self.offset:
                with open(self.path, "rb") as f:
                    f.seek(self.offset)
                    data = f.read(st.st_size - self.offset)
                end = data.rfind(b"\n") + 1
                for line in data[:end].splitlines():
                    if not line.strip():
                        continue
                    row = _parse(line)
                    if row is None:
                        self.bad += 1
                    else:
                        self.rows.append(row)
                self.offset += end
            return self.rows


class LogStore:
    """One JsonlTail per file, shared across requests."""

    def __init__(self):
        self._tails: dict[str, JsonlTail] = {}
        self._lock = threading.Lock()

    def tail(self, path) -> JsonlTail:
        key = str(Path(path))
        with self._lock:
            if key not in self._tails:
                self._tails[key] = JsonlTail(path)
            return self._tails[key]


def read_after(path, after: int, limit: int = 200, file_id: int | None = None) -> dict:
    """Rows after byte offset `after`. If the file is now shorter than `after`, or `file_id` names a different
    (rotated or replaced) file, restart from 0 with reset=True."""
    p = Path(path)
    try:
        st = p.stat()
        size, current = st.st_size, st.st_ino
    except FileNotFoundError:
        size, current = 0, None
    reset = after > size or (file_id is not None and file_id != current)
    start = 0 if reset or after < 0 else after
    rows, pos = [], start
    if size > start:
        with open(p, "rb") as f:
            f.seek(start)
            data = f.read(size - start)
        for line in data.splitlines(keepends=True):
            if not line.endswith(b"\n") or len(rows) >= limit:
                break
            pos += len(line)
            row = _parse(line) if line.strip() else None
            if row is not None:
                rows.append(row)
    return {"rows": rows, "next": pos, "reset": reset, "file_id": current}


def read_tail(path, n: int = 50) -> dict:
    """The last n complete rows and the byte offset just after the last complete line."""
    p = Path(path)
    if not p.exists():
        return {"rows": [], "next": 0, "reset": False, "file_id": None}
    n = max(1, n)
    st = p.stat()
    size, file_ino = st.st_size, st.st_ino
    data, pos = b"", size
    with open(p, "rb") as f:
        while pos > 0 and data.count(b"\n") <= n:
            step = min(65536, pos)
            pos -= step
            f.seek(pos)
            data = f.read(step) + data
    end = data.rfind(b"\n") + 1  # bytes after the last newline are a partial line
    lines = data[:end].splitlines()
    if pos > 0:
        lines = lines[1:]  # the first line may be cut by the block boundary
    rows = [r for r in (_parse(line) for line in lines if line.strip()) if r is not None][-n:]
    return {"rows": rows, "next": pos + end, "reset": False, "file_id": file_ino}


def summarize_sessions(rows) -> list[dict]:
    from monitor.server.analysis import latest_actions
    by: dict[tuple, dict] = {}
    for r in latest_actions(rows):
        key = (str(r.get("agent", "")), str(r.get("session_id", "")))
        ts = num(r.get("ts"))
        s = by.get(key)
        if s is None:
            s = by[key] = {"agent": key[0], "session_id": key[1], "task": "", "first_ts": ts, "last_ts": ts,
                           "actions": 0, "max_severity": 0.0, "_incidents": set(), "_task_ts": float("-inf")}
        s["first_ts"], s["last_ts"] = min(s["first_ts"], ts), max(s["last_ts"], ts)
        s["actions"] += 1
        s["max_severity"] = max(s["max_severity"], num(r.get("final_severity")))
        if r.get("incident_id"):
            s["_incidents"].add(r["incident_id"])
        if r.get("task") and ts >= s["_task_ts"]:
            s["task"], s["_task_ts"] = r["task"], ts
    out = []
    for s in by.values():
        s["incidents"] = len(s.pop("_incidents"))
        s.pop("_task_ts")
        out.append(s)
    return sorted(out, key=lambda s: s["last_ts"], reverse=True)


def session_actions(rows, agent: str, session_id: str) -> list[dict]:
    """A session's rows in time order; a rules_post row sorts directly after the action it rescored."""
    sel = [r for r in rows if r.get("agent") == agent and r.get("session_id") == session_id]
    return sorted(sel, key=lambda r: (num(r.get("ts")), num(r.get("index")), r.get("settled_by") == "rules_post"))


def latest_incidents(rows, recent_hours=None, now=None) -> list[dict]:
    """The last snapshot per incident id, highest severity first, then most recently updated."""
    latest: dict[str, dict] = {}
    for r in rows:
        if r.get("id"):
            latest[str(r["id"])] = r
    vals = list(latest.values())
    if recent_hours is not None:
        cutoff = (time.time() if now is None else now) - float(recent_hours) * 3600
        vals = [v for v in vals if num(v.get("updated")) >= cutoff]
    return sorted(vals, key=lambda v: (-num(v.get("severity")), -num(v.get("updated"))))
