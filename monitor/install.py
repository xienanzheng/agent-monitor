"""Install/uninstall the v2 live hook for Claude Code (~/.claude/settings.json) and Codex (~/.codex/hooks.json)."""
import json
import shutil
import time
from pathlib import Path

from monitor.hook import _ABSENT, _installed_copy

MARK = "monitor.live_hook"
TOOL_EVENTS = {"PreToolUse", "PostToolUse"}
CLAUDE_EVENTS = {"UserPromptSubmit": 5, "PreToolUse": 5, "PostToolUse": 5, "PostToolUseFailure": 5, "SessionStart": 5, "SessionEnd": 5}
CODEX_EVENTS = {"UserPromptSubmit": 5, "PreToolUse": 5, "PostToolUse": 5, "SessionStart": 5, "SessionEnd": 1}


def live_hook_command(root, agent: str) -> str:
    return f'"{Path(root) / ".venv" / "bin" / "python"}" -I -m monitor.live_hook --agent {agent}'


def settings_path_for(agent: str, home=None) -> Path:
    home = Path(home) if home is not None else Path.home()
    return home / ".claude" / "settings.json" if agent == "claude" else home / ".codex" / "hooks.json"


def install_hooks(settings_path, command: str, events: dict) -> Path:
    s = Path(settings_path)
    if s.exists() and MARK in s.read_text():
        raise RuntimeError(f"already installed in {s}")
    s.parent.mkdir(parents=True, exist_ok=True)
    backup = s.with_name(f"{s.name}.backup-{time.strftime('%Y%m%d-%H%M%S')}")
    if s.exists():
        shutil.copy2(s, backup)
        data = json.loads(s.read_text() or "{}")
    else:
        backup.write_text(_ABSENT)
        data = {}
    hooks = data.setdefault("hooks", {})
    for event, timeout in events.items():
        entry = {"hooks": [{"type": "command", "command": command, "timeout": timeout}]}
        if event in TOOL_EVENTS:
            entry = {"matcher": "*", **entry}
        hooks.setdefault(event, []).append(entry)
    s.write_text(json.dumps(data, indent=2))
    shutil.copy2(s, _installed_copy(backup))
    return backup


def _remove_ours(data: dict) -> dict:
    hooks = data.get("hooks")
    if not isinstance(hooks, dict):
        return data
    any_changed = False
    for event in list(hooks):
        entries = hooks[event]
        if not isinstance(entries, list):
            continue
        kept, changed = [], False
        for entry in entries:
            inner = entry.get("hooks") if isinstance(entry, dict) else None
            if not isinstance(inner, list):
                kept.append(entry)
                continue
            rest = [h for h in inner if not (isinstance(h, dict) and MARK in str(h.get("command", "")))]
            if len(rest) == len(inner):
                kept.append(entry)
                continue
            changed = True
            if rest:
                kept.append({**entry, "hooks": rest})
        if changed:
            any_changed = True
            if kept:
                hooks[event] = kept
            else:
                del hooks[event]
    if any_changed and not hooks:
        del data["hooks"]
    return data


def uninstall_hooks(settings_path, backup_path) -> Path | None:
    """Restore byte-for-byte if unchanged since install; else keep the user's edits and drop only our hooks.

    Returns None when restored (or when there was nothing of ours to remove), else the pre-uninstall copy."""
    s, b = Path(settings_path), Path(backup_path)
    installed = _installed_copy(b)
    if s.exists() and installed.exists() and s.read_bytes() == installed.read_bytes():
        if b.read_text() == _ABSENT:
            s.unlink(missing_ok=True)
        else:
            shutil.copy2(b, s)
        return None
    if not s.exists() or MARK not in s.read_text():
        return None  # nothing of ours left: leave the file exactly as it is
    saved = s.with_name(f"{s.name}.backup-before-uninstall-{time.strftime('%Y%m%d-%H%M%S')}")
    shutil.copy2(s, saved)
    s.write_text(json.dumps(_remove_ours(json.loads(s.read_text() or "{}")), indent=2))
    return saved


def install_live_hooks(root, agent: str, home=None) -> list[tuple[str, Path, Path]]:
    py = Path(root) / ".venv" / "bin" / "python"
    if not py.exists():
        raise SystemExit(f"error: {py} not found; run `uv sync` first. Nothing was changed.")
    agents = ["claude", "codex"] if agent == "both" else [agent]
    targets = [(a, settings_path_for(a, home)) for a in agents]
    already = [str(s) for _, s in targets if s.exists() and MARK in s.read_text()]
    if already:
        raise RuntimeError(f"already installed in {', '.join(already)}; nothing was changed")
    for _, s in targets:  # parse every target before writing any, so a bad second file can't leave a half install
        if s.exists():
            try:
                if not isinstance(json.loads(s.read_text() or "{}"), dict):
                    raise ValueError("top level is not a JSON object")
            except ValueError as e:
                raise RuntimeError(f"{s} is not valid JSON ({e}); nothing was changed") from e
    done = []
    for a, s in targets:
        events = CLAUDE_EVENTS if a == "claude" else CODEX_EVENTS
        done.append((a, s, install_hooks(s, live_hook_command(root, a), events)))
    return done
