"""Monitor settings: defaults, optionally overridden by monitor.toml in the project root."""
import os
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    settle_low: float = 1.0
    settle_high: float = 9.0
    escalate_at: float = 5.0
    min_confidence: float = 0.6
    incident_at: float = 5.0
    notify_at: float = 8.0
    notify: bool = True
    incident_window_s: float = 60.0
    session_idle_s: float = 7200.0
    triage_model: str = "qwen3:4b"
    gateway_model: str = "qwen3:8b"
    triage_timeout_s: float = 90.0
    gateway_timeout_s: float = 120.0
    queue_max: int = 500
    socket_path: str = "~/.cache/agent-monitor/monitor.sock"


def _validate(cfg: Config) -> Config:
    def bad(key, rule):
        raise ValueError(f"monitor.toml: {key} {rule}, got {getattr(cfg, key)!r}")

    if not os.path.isabs(os.path.expanduser(cfg.socket_path)):
        bad("socket_path", "must be an absolute path (or start with ~)")
    if cfg.queue_max < 1:
        bad("queue_max", "must be at least 1")
    if not 0 <= cfg.settle_low < cfg.settle_high <= 10:
        raise ValueError(f"monitor.toml: settle_low/settle_high must satisfy 0 <= settle_low < settle_high <= 10, "
                         f"got settle_low={cfg.settle_low!r}, settle_high={cfg.settle_high!r}")
    for key in ("escalate_at", "incident_at", "notify_at"):
        if not 0 <= getattr(cfg, key) <= 10:
            bad(key, "must be between 0 and 10")
    if not 0 <= cfg.min_confidence <= 1:
        bad("min_confidence", "must be between 0 and 1")
    for key in ("triage_timeout_s", "gateway_timeout_s", "incident_window_s", "session_idle_s"):
        if not getattr(cfg, key) > 0:
            bad(key, "must be greater than 0")
    return cfg


def load_config(path=None) -> Config:
    p = Path(path) if path is not None else ROOT / "monitor.toml"
    if not p.exists():
        return _validate(Config())
    data = tomllib.loads(p.read_text())
    defaults = Config()
    known = {f.name for f in fields(Config)}
    out = {}
    for key, value in data.items():
        if key not in known:
            raise ValueError(f"monitor.toml: unknown key {key!r}")
        default = getattr(defaults, key)
        if isinstance(default, bool):
            ok = isinstance(value, bool)
        elif isinstance(default, (int, float)):
            ok = isinstance(value, (int, float)) and not isinstance(value, bool)
        else:
            ok = isinstance(value, str)
        if not ok:
            raise ValueError(f"monitor.toml: {key} must be {type(default).__name__}, got {value!r}")
        out[key] = value if isinstance(default, (bool, str)) else type(default)(value)
    return _validate(Config(**out))
