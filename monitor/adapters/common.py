import json
import re
from typing import Iterator

from monitor.redact import redact

MAX_TEXT = 4000
MAX_OUTPUT = 1500


def iter_jsonl(path) -> Iterator[dict]:
    with open(path, errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict):
                yield rec


def clip(text, n: int) -> str:
    text = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False, default=str)
    return text if len(text) <= n else text[:n] + f"…[+{len(text) - n} chars]"


def safe_clip(text, n: int) -> str:
    """Redact, then clip: clipping first can cut a secret so its pattern no longer matches."""
    text = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False, default=str)
    return clip(redact(text), n)


def content_to_text(content) -> str:
    """Flatten a message/tool-result content field (str or list of blocks) to text."""
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return json.dumps(content, ensure_ascii=False, default=str)
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                parts.append(b.get("text") or b.get("content") if isinstance(b.get("text") or b.get("content"), str) else "")
            elif isinstance(b, str):
                parts.append(b)
        return "\n".join(p for p in parts if p)
    return ""


_NESTED_CMD = re.compile(r"""\bcmd\s*:\s*(["'`])((?:\\.|(?!\1).)*)\1""", re.S)


def nested_commands(code: str) -> list[str]:
    """Shell commands embedded in JS tool code, e.g. tools.exec_command({cmd:"..."})."""
    return [m.group(2).encode().decode("unicode_escape", errors="ignore") for m in _NESTED_CMD.finditer(code or "")]
