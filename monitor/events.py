"""Normalize Claude Code / Codex hook payloads into redacted HookEvents. Runs inside the hook process."""
import json
import time
from dataclasses import asdict, dataclass

from monitor.adapters.claude_code import classify as classify_claude
from monitor.adapters.common import MAX_OUTPUT, MAX_TEXT, content_to_text, safe_clip
from monitor.redact import redact

EVENTS = {"UserPromptSubmit": "prompt", "PreToolUse": "pre_tool", "PostToolUse": "post_tool",
          "PostToolUseFailure": "post_tool",
          "SessionStart": "session_start", "SessionEnd": "session_end"}
AGENTS = {"claude": "claude_code", "codex": "codex"}


@dataclass
class HookEvent:
    agent: str
    event: str
    session_id: str
    ts: float
    cwd: str | None = None
    permission_mode: str = ""
    turn_id: str | None = None
    prompt: str = ""
    tool_name: str = ""
    tool_use_id: str = ""
    kind: str = ""
    text: str = ""
    output: str = ""
    path: str | None = None
    source: str = ""
    reason: str = ""
    outcome: str = "pending"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "HookEvent":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


def classify_codex(tool: str, inp) -> tuple[str, str]:
    from monitor.adapters.codex import classify
    tool = tool.removeprefix("functions.")
    name = tool
    if name in {"shell", "exec_command", "shell_command", "local_shell", "write_stdin", "exec", "js",
                "spawn_agent", "send_message", "followup_task"}:
        return classify(name, inp)
    if tool == "apply_patch" and isinstance(inp, str):  # Codex can send the patch itself as the whole input
        return "file_write", inp
    inp = inp if isinstance(inp, dict) else {}
    if tool == "Bash":
        return "shell", str(inp.get("command", ""))
    if tool == "apply_patch":
        return "file_write", str(inp.get("command") or inp.get("input") or json.dumps(inp))
    if tool.startswith("mcp__"):
        return "mcp", f"{tool} {safe_clip(inp, MAX_TEXT)}"
    return classify_claude(tool, inp)


def _path(inp) -> str | None:
    if not isinstance(inp, dict):
        return None
    p = inp.get("file_path") or inp.get("notebook_path") or inp.get("path")
    return redact(p) if isinstance(p, str) and p else None


def normalize_event(agent_flag: str, payload: dict) -> HookEvent | None:
    if not isinstance(payload, dict):
        raise ValueError("hook payload must be an object")
    agent = AGENTS.get(agent_flag)
    event = EVENTS.get(payload.get("hook_event_name", ""))
    if agent is None or event is None:
        return None
    ev = HookEvent(agent=agent, event=event, session_id=str(payload.get("session_id", "")), ts=time.time(),
                   cwd=redact(str(payload["cwd"])) if payload.get("cwd") else None, permission_mode=str(payload.get("permission_mode") or ""),
                   turn_id=payload.get("turn_id"), source=str(payload.get("source") or ""),
                   reason=str(payload.get("reason") or ""))
    if event == "prompt":
        ev.prompt = safe_clip(str(payload.get("prompt", "")), MAX_TEXT)
    elif event in ("pre_tool", "post_tool"):
        tool = str(payload.get("tool_name", ""))
        inp = payload.get("tool_input", {})
        kind, text = (classify_codex if agent == "codex" else classify_claude)(tool, inp)
        ev.tool_name, ev.kind, ev.text, ev.path = tool, kind, safe_clip(text, MAX_TEXT), _path(inp)
        ev.tool_use_id = str(payload.get("tool_use_id") or "")
        if event == "post_tool":
            failed = payload.get("hook_event_name") == "PostToolUseFailure"
            out = payload.get("error", "") if failed else payload.get("tool_output", payload.get("tool_response", ""))
            if isinstance(out, dict):
                failed = failed or bool(out.get("isError")) or bool(out.get("is_error")) or (isinstance(out.get("exit_code"), (int,float)) and out["exit_code"] != 0)
            ev.outcome = "failed" if failed else "succeeded"
            if not isinstance(out, str):
                out = content_to_text(out) or json.dumps(out, default=str)
            ev.output = safe_clip(out, MAX_OUTPUT)
    return ev
