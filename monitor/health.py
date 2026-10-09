"""Shared read-only diagnostics. Never execute commands from settings."""
import json
import os
import shlex
import threading
import time
import urllib.request
from pathlib import Path
from monitor.config import load_config
from monitor.install import CLAUDE_EVENTS, CODEX_EVENTS, settings_path_for

_MODEL_CACHE = None
_MODEL_LOCK = threading.Lock()


def ollama_health():
    global _MODEL_CACHE
    with _MODEL_LOCK:
        if _MODEL_CACHE and time.monotonic() - _MODEL_CACHE[0] < 10:
            return dict(_MODEL_CACHE[1])
        try:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open('http://127.0.0.1:11434/api/tags', timeout=1) as r:
                data = json.load(r)
            result = {'reachable': True, 'models': sorted(m['name'] for m in data.get('models', [])), 'error': None, 'digests': {m['name']:m.get('digest') for m in data.get('models',[])}}
        except Exception as e:
            result = {'reachable': False, 'models': [], 'error': type(e).__name__}
        _MODEL_CACHE = (time.monotonic(), result)
        return dict(result)


def agent_health(home, agent, rows):
    path = settings_path_for(agent, home)
    required = set(CLAUDE_EVENTS if agent == 'claude' else CODEX_EVENTS)
    registered, commands, errors = set(), [], []
    disabled = False
    try:
        data = json.loads(path.read_text()) if path.exists() else {}
        if not isinstance(data, dict) or not isinstance(data.get('hooks', {}), dict):
            raise ValueError('settings must contain an object of hook events')
        disabled = data.get('disableAllHooks', False) is True
        for event, entries in data.get('hooks', {}).items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict) or entry.get('matcher', '*') not in ('*', '', None):
                    continue
                for h in entry.get('hooks', []):
                    if not isinstance(h, dict) or h.get('type') != 'command':
                        continue
                    args = shlex.split(h.get('command', ''))
                    if len(args) == 6 and args[1:] == ['-I', '-m', 'monitor.live_hook', '--agent', agent]:
                        registered.add(event)
                        commands.append(args[0])
    except (ValueError, OSError, IndexError, TypeError) as e:
        errors.append(type(e).__name__)
    agent_name = 'claude_code' if agent == 'claude' else 'codex'
    observed = [r for r in rows if r.get('agent') == agent_name]
    last = max((r.get('ts', 0) for r in observed if isinstance(r.get('ts'), (int, float))), default=None)
    executable_ok = bool(commands) and all(Path(p).is_file() and os.access(p, os.X_OK) for p in commands)
    configured = required <= registered and not disabled and not errors
    return {'configured': configured, 'observed': bool(observed), 'last_event_ts': last,
            'executable_ok': executable_ok, 'settings_path': str(path), 'disabled': disabled,
            'missing_events': sorted(required - registered), 'errors': errors,
            'trust': 'native_review_required' if agent == 'codex' else 'native_session_settings'}


def inspect_health(settings, live_rows):
    try:
        cfg = load_config(Path(settings.root) / 'monitor.toml')
        config_error = None
    except (ValueError, OSError) as e:
        from monitor.config import Config
        cfg, config_error = Config(), str(e)
    models = ollama_health()
    required = [cfg.triage_model, cfg.gateway_model]
    models['required'] = required
    models['missing'] = [m for m in required if m not in models['models']]
    return {'agents': {a: agent_health(settings.home, a, live_rows) for a in ('claude', 'codex')},
            'ollama': models, 'python': {'path': str(Path(settings.root)/'.venv/bin/python'),
            'exists': (Path(settings.root)/'.venv/bin/python').exists()}, 'config_error': config_error,
            'coverage': {'unknown_tools': sum(r.get('coverage') == 'unknown_tool' for r in live_rows)}}
