"""Claude Code transcripts: ~/.claude/projects/<project>/<session>.jsonl"""
from monitor.adapters.common import MAX_OUTPUT, MAX_TEXT, content_to_text, iter_jsonl, safe_clip
from monitor.schema import Action

_WRITE = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
_READ = {"Read", "Glob", "Grep", "LS", "NotebookRead"}
_NET = {"WebFetch", "WebSearch"}


def classify(tool: str, inp: dict) -> tuple[str, str]:
    inp = inp if isinstance(inp, dict) else {}
    if tool == "Bash":
        return "shell", inp.get("command", "")
    if tool in _WRITE:
        body = inp.get("content") or inp.get("new_string") or inp.get("new_source") or inp.get("edits") or ""
        return "file_write", f"{tool} {inp.get('file_path') or inp.get('notebook_path', '')}\n{safe_clip(body, MAX_TEXT)}"
    if tool in _READ:
        return "file_read", f"{tool} {inp.get('file_path') or inp.get('pattern') or inp.get('path', '')}"
    if tool in _NET:
        return "network", f"{tool} {inp.get('url') or inp.get('query', '')}"
    if tool.startswith(("mcp__claude-in-chrome__", "mcp__plugin_playwright")):
        return "browser", f"{tool} {safe_clip(inp, MAX_TEXT)}"
    if tool.startswith("mcp__"):
        return "mcp", f"{tool} {safe_clip(inp, MAX_TEXT)}"
    if tool in {"Agent", "Task"}:
        return "agent", f"{tool} {safe_clip(inp.get('prompt', inp), MAX_TEXT)}"
    return "other", f"{tool} {safe_clip(inp, MAX_TEXT)}"


def load_claude_code(path) -> list[Action]:
    actions: list[Action] = []
    by_id: dict[str, Action] = {}
    task = ""
    for rec in iter_jsonl(path):
        msg = rec.get("message")
        if not isinstance(msg, dict):
            continue
        content = msg.get("content")
        if rec.get("type") == "user":
            if isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id") in by_id:
                        by_id[b["tool_use_id"]].outcome = "failed" if b.get("is_error") else "succeeded"
                        by_id[b["tool_use_id"]].output = safe_clip(content_to_text(b.get("content")), MAX_OUTPUT)
                texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
            else:
                texts = [content] if isinstance(content, str) else []
            # injected blocks (<system-reminder>, <command-name>, ...) and isMeta records are not the user's task
            text = "\n".join(t for t in texts if isinstance(t, str) and not t.lstrip().startswith("<"))
            if text.strip() and not rec.get("isMeta"):
                task = safe_clip(text.strip(), MAX_TEXT)
        elif rec.get("type") == "assistant" and isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "tool_use":
                    kind, text = classify(b.get("name", ""), b.get("input", {}))
                    a = Action(agent="claude_code", session_id=str(rec.get("sessionId", "")), index=len(actions),
                               tool=b.get("name", ""), kind=kind, text=safe_clip(text, MAX_TEXT), ts=rec.get("timestamp"),
                               cwd=rec.get("cwd"), task=task, tool_use_id=str(b.get("id") or ""),
                               path=(b.get("input") or {}).get("file_path") if isinstance(b.get("input"),dict) else None)
                    actions.append(a)
                    by_id[b.get("id", "")] = a
    return actions
