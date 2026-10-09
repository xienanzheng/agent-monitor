"""Load real agent logs, redact them, write data/real/actions.jsonl and summary stats."""
import json
from collections import Counter
from pathlib import Path

from monitor.adapters.claude_code import load_claude_code
from monitor.adapters.codex import load_codex
from monitor.redact import redact

HOME = Path.home()


def discover(home: Path = HOME) -> tuple[list[Path], list[Path]]:
    # ** also picks up subagent transcripts (<project>/<session>/subagents/*.jsonl)
    claude = sorted((home / ".claude" / "projects").glob("**/*.jsonl"))
    codex = sorted((home / ".codex" / "sessions").glob("**/*.jsonl"))
    return claude, codex


def _clean(a):
    a.text, a.output, a.task = redact(a.text), redact(a.output), redact(a.task)
    return a


def ingest(claude_files, codex_files, out_path) -> dict:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    by_agent, by_kind, by_tool, policy, first_word = Counter(), Counter(), Counter(), Counter(), Counter()
    with out_path.open("w") as f:
        for loader, files in ((load_claude_code, claude_files), (load_codex, codex_files)):
            for path in files:
                for a in loader(path):
                    a = _clean(a)
                    f.write(json.dumps(a.to_dict(), ensure_ascii=False) + "\n")
                    by_agent[a.agent] += 1
                    by_kind[a.kind] += 1
                    by_tool[a.tool] += 1
                    if a.policy:
                        policy[f"{a.policy.get('approval')}/{a.policy.get('sandbox')}"] += 1
                    if a.kind == "shell" and a.text.strip():
                        first_word[a.text.split()[0]] += 1
    return {"by_agent": dict(by_agent), "by_kind": dict(by_kind), "top_tools": by_tool.most_common(15),
            "policy": dict(policy), "top_shell_commands": first_word.most_common(25)}
