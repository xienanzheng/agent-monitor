"""Group related signals into incidents and notify on high severity (never with command text)."""
import json
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from monitor.redact import redact


@dataclass
class Incident:
    id: str
    agent: str
    session_id: str
    category: str
    opened: float
    updated: float
    severity: float
    signals: list = field(default_factory=list)
    action_count: int = 1
    latest_reason: str = ""
    notified_severity: float = 0.0


def macos_notifier(title: str, body: str) -> None:
    """Fire-and-forget: title and body go in as argv, so no AppleScript quoting, and the caller never waits."""
    subprocess.Popen(["osascript", "-e", "on run argv",
                      "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
                      "-e", "end run", title, body],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class IncidentTracker:
    def __init__(self, cfg, out_path=None, notifier=None, clock=time.time):
        self.cfg, self.notifier, self.clock = cfg, notifier, clock
        self.out_path = Path(out_path) if out_path is not None else None
        self.open: dict[tuple, Incident] = {}
        self._n = 0
        self._action_ids: dict[str, set] = {}

    def observe(self, agent, session_id, category, severity, signals, reason, *,
                at: float | None = None, action_id: str | None = None) -> Incident | None:
        """`at` is the event time; spooled events are judged long after they happened, so the window uses it."""
        if severity is None or severity < self.cfg.incident_at:
            return None
        now = self.clock() if at is None else at
        key = (agent, session_id, category)
        inc = self.open.get(key)
        if inc is not None and now - inc.updated <= self.cfg.incident_window_s:  # an older event merges too
            inc.updated = max(inc.updated, now)
            inc.opened = min(inc.opened, now)
            inc.severity = max(inc.severity, severity)
            if action_id is None or action_id not in self._action_ids.setdefault(inc.id, set()):
                inc.action_count += 1
            for s in signals:
                if s not in inc.signals:
                    inc.signals.append(s)
            if reason:
                inc.latest_reason = redact(reason)[:500]
        else:
            self._n += 1
            inc = Incident(id=f"inc-{int(now)}-{self._n}", agent=agent, session_id=session_id, category=category,
                           opened=now, updated=now, severity=severity, signals=list(dict.fromkeys(signals)),
                           latest_reason=redact(reason)[:500] if reason else "")
            self.open[key] = inc
        if action_id is not None:
            self._action_ids.setdefault(inc.id, set()).add(action_id)
        self._maybe_notify(inc)
        self._write(inc)
        return inc

    def _maybe_notify(self, inc: Incident) -> None:
        if not (self.cfg.notify and self.notifier) or inc.severity < self.cfg.notify_at:
            return
        if inc.severity <= inc.notified_severity:
            return
        inc.notified_severity = inc.severity
        try:
            self.notifier(f"Agent Monitor — HIGH ({inc.severity:.0f})",
                          f"{inc.category} · {inc.agent} · session {inc.session_id[:8]}")
        except Exception:
            pass  # notification problems never affect monitoring

    def _write(self, inc: Incident) -> None:
        if self.out_path is None:
            return
        row = asdict(inc)
        row.pop("notified_severity")
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.out_path, "a") as f:
            f.write(json.dumps(row) + "\n")
