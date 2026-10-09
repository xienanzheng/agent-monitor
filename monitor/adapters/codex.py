"""Codex rollouts: ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl"""
import json

from monitor.adapters.common import MAX_OUTPUT, MAX_TEXT, content_to_text, iter_jsonl, nested_commands, safe_clip
from monitor.schema import Action

_SHELL = {"shell", "exec_command", "shell_command", "local_shell", "write_stdin"}


def _args(p: dict) -> dict | str:
    raw = p.get("arguments", p.get("input", ""))
    if isinstance(raw, str):
        try:
            v = json.loads(raw)
            return v if isinstance(v, dict) else raw
        except json.JSONDecodeError:
            return raw
    return raw if isinstance(raw, dict) else str(raw)


def classify(name: str, args) -> tuple[str, str]:
    name = name.removeprefix("functions.")
    a = args if isinstance(args, dict) else {}
    if name.startswith("mcp__"):
        return "mcp", f"{name} {safe_clip(args, MAX_TEXT)}"
    if name in _SHELL:
        cmd = a.get("command", a.get("cmd", a.get("chars", "")))
        if isinstance(cmd, list):  # ["bash", "-lc", "ls"] -> "ls"
            cmd = cmd[-1] if len(cmd) >= 3 and cmd[1] in ("-lc", "-c") else " ".join(map(str, cmd))
        return "shell", str(cmd)
    if name == "apply_patch":
        return "file_write", args if isinstance(args, str) else a.get("input", json.dumps(a))
    if name in {"exec", "js"}:
        code = args if isinstance(args, str) else a.get("code", json.dumps(a))
        nested = nested_commands(code)
        return "code_exec", ("\n".join(f"$ {c}" for c in nested) + "\n" if nested else "") + code
    if name in {"spawn_agent", "send_message", "followup_task"}:
        return "agent", safe_clip(json.dumps(a), MAX_TEXT) if a else str(args)
    if "browser" in name or name.startswith("cua"):
        return "browser", json.dumps(a) if a else str(args)
    return "other", f"{name} {json.dumps(a) if a else args}"


def load_codex(path) -> list[Action]:
    actions: list[Action] = []
    by_call: dict[str, Action] = {}
    session, cwd, task, policy = "", None, "", {}
    for rec in iter_jsonl(path):
        p = rec.get("payload")
        if not isinstance(p, dict):
            continue
        t = rec.get("type")
        if t == "session_meta":
            session, cwd = str(p.get("id", "")), p.get("cwd")
        elif t == "turn_context":
            cwd = p.get("cwd", cwd)
            sp = p.get("sandbox_policy")
            ap = p.get("approval_policy")
            policy = {"approval": ap if isinstance(ap, str) else json.dumps(ap),
                      "sandbox": sp.get("type") if isinstance(sp, dict) else str(sp)}
        elif t == "response_item":
            pt = p.get("type")
            if pt == "message" and p.get("role") == "user":
                text = content_to_text(p.get("content"))
                if text.strip() and not text.lstrip().startswith("<"):  # skip injected env/instructions blocks
                    task = safe_clip(text.strip(), MAX_TEXT)
            elif pt in ("function_call", "custom_tool_call"):
                kind, text = classify(p.get("name", ""), _args(p))
                a = Action(agent="codex", session_id=session, index=len(actions), tool=p.get("name", ""), kind=kind,
                           text=safe_clip(text, MAX_TEXT), ts=rec.get("timestamp"), cwd=cwd, task=task, policy=dict(policy), tool_use_id=str(p.get("call_id") or ""))
                actions.append(a)
                by_call[p.get("call_id", "")] = a
            elif pt in ("function_call_output", "custom_tool_call_output") and p.get("call_id") in by_call:
                out = p.get("output")
                by_call[p["call_id"]].outcome = "failed" if isinstance(out,dict) and (out.get("isError") or out.get("exit_code",0) != 0) else "succeeded"
                by_call[p["call_id"]].output = safe_clip(content_to_text(out) if not isinstance(out, str) else out, MAX_OUTPUT)
    return actions
