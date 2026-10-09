"""Common action schema shared by every adapter, monitor and the evaluation."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

KINDS = ("shell", "code_exec", "file_write", "file_read", "network", "browser", "mcp", "agent", "other")


@dataclass
class Action:
    agent: str                 # claude_code | codex | cursor | synthetic
    session_id: str
    index: int                 # position of the action within its session
    tool: str                  # raw tool name as logged
    kind: str                  # one of KINDS
    text: str                  # normalised description: the command, or path + content
    ts: str | None = None
    cwd: str | None = None
    output: str = ""           # truncated tool output, if logged
    task: str = ""             # most recent user instruction before this action
    policy: dict = field(default_factory=dict)  # e.g. {"approval": "never", "sandbox": "danger-full-access"}
    label: int | None = None   # synthetic only: 1 malicious, 0 benign
    category: str | None = None
    trajectory_id: str | None = None
    group_id: str | None = None
    split: str | None = None
    path: str | None = None
    tool_use_id: str = ""
    outcome: str = "pending"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Action":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})
