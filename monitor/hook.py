"""Claude Code PreToolUse hook: log-only, fail-open. Never prints, never blocks."""
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_ABSENT = "__settings_absent__"
_MARK = "monitor.hook"


def run_hook(stdin_text: str, log_path, rules_path) -> int:
    try:
        from monitor.adapters.claude_code import classify
        from monitor.redact import redact
        from monitor.rules import load_rules, score_rules
        from monitor.schema import Action

        p = json.loads(stdin_text)
        kind, text = classify(p.get("tool_name", ""), p.get("tool_input", {}))
        a = Action(agent="claude_code", session_id=str(p.get("session_id", "")), index=-1,
                   tool=p.get("tool_name", ""), kind=kind, text=text, cwd=p.get("cwd"))
        rules_missing = not Path(rules_path).exists()
        score, hits = (None, []) if rules_missing else score_rules(a, load_rules(rules_path))
        row = {"ts": time.time(), "session_id": a.session_id, "cwd": a.cwd, "tool": a.tool, "kind": kind,
               "text": redact(text)[:2000], "rule_score": score, "rule_hits": hits, "rules_missing": rules_missing}
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception as e:
        # Record failure to error log while staying fail-open
        try:
            try:
                from monitor.redact import redact
                message = redact(str(e))[:500]
            except Exception:
                message = type(e).__name__
            error_log = Path(log_path).parent / "hook_errors.log"
            Path(log_path).parent.mkdir(parents=True, exist_ok=True)
            error_row = {"ts": time.time(), "error": type(e).__name__, "message": message}
            with open(error_log, "a") as f:
                f.write(json.dumps(error_row) + "\n")
        except Exception:
            pass  # fail open: error log write must not break the agent
    return 0


def main():
    try:
        stdin_text = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    except Exception:
        stdin_text = ""  # run_hook records the parse failure and still exits 0
    sys.exit(run_hook(stdin_text, ROOT / "logs" / "live.jsonl", ROOT / "rules" / "rules.json"))


def _installed_copy(backup: Path) -> Path:
    """Exact copy of what install_hook wrote, named after the backup's timestamp."""
    return backup.with_name(backup.name.replace(".backup-", ".monitor-installed-", 1))


def install_hook(settings_path, command: str) -> Path:
    s = Path(settings_path)
    if s.exists() and _MARK in s.read_text():
        raise RuntimeError(f"already installed in {s}")
    backup = s.with_name(f"{s.name}.backup-{time.strftime('%Y%m%d-%H%M%S')}")
    if s.exists():
        shutil.copy2(s, backup)
        data = json.loads(s.read_text() or "{}")
    else:
        backup.write_text(_ABSENT)
        data = {}
    pre = data.setdefault("hooks", {}).setdefault("PreToolUse", [])
    pre.append({"matcher": "*", "hooks": [{"type": "command", "command": command, "timeout": 5}]})
    s.parent.mkdir(parents=True, exist_ok=True)
    s.write_text(json.dumps(data, indent=2))
    shutil.copy2(s, _installed_copy(backup))
    return backup


def _remove_monitor_hooks(data: dict) -> dict:
    """Drop only our PreToolUse hook commands; drop containers that became empty because of that."""
    hooks = data.get("hooks")
    pre = hooks.get("PreToolUse") if isinstance(hooks, dict) else None
    if not isinstance(pre, list):
        return data
    kept, changed = [], False
    for entry in pre:
        inner = entry.get("hooks") if isinstance(entry, dict) else None
        if not isinstance(inner, list):
            kept.append(entry)
            continue
        rest = [h for h in inner if not (isinstance(h, dict) and _MARK in str(h.get("command", "")))]
        if len(rest) == len(inner):
            kept.append(entry)
            continue
        changed = True
        if rest:
            kept.append({**entry, "hooks": rest})
    if not changed:
        return data
    if kept:
        hooks["PreToolUse"] = kept
    else:
        del hooks["PreToolUse"]
        if not hooks:
            del data["hooks"]
    return data


def uninstall_hook(settings_path, backup_path) -> Path | None:
    """Restore the backup if settings are exactly as installed; otherwise remove only our hook.

    Returns None after a byte-for-byte restore, or the path of the pre-uninstall copy
    when later edits were kept and only the monitor hook entry was removed."""
    s, b = Path(settings_path), Path(backup_path)
    installed = _installed_copy(b)
    if s.exists() and installed.exists() and s.read_bytes() == installed.read_bytes():
        if b.read_text() == _ABSENT:
            s.unlink(missing_ok=True)
        else:
            shutil.copy2(b, s)
        return None
    if not s.exists():
        return None  # nothing installed any more; leave the user's choice alone
    saved = s.with_name(f"{s.name}.backup-before-uninstall-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(s, saved)
    data = json.loads(s.read_text() or "{}")
    s.write_text(json.dumps(_remove_monitor_hooks(data), indent=2))
    return saved


if __name__ == "__main__":
    main()
