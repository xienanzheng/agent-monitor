"""Offline views: traffic overview, the ingested-action browser, scan alerts, eval results and rules (read-only)."""
import json
import threading
from dataclasses import asdict
from pathlib import Path

from monitor.features import load_features
from monitor.rules import ActionRule, load_rules_v2

LABELLED_FIXTURE = "tests/fixtures/labelled_sample.jsonl"


def read_json(path) -> dict:
    p = Path(path)
    if not p.is_file():
        return {"missing": True}
    try:
        data = json.loads(p.read_text())
    except (ValueError, OSError) as e:
        return {"error": f"{p.name} could not be read: {e}"}
    return data if isinstance(data, dict) else {"error": f"{p.name} is not a JSON object"}


class ActionsCache:
    """data/real/actions.jsonl held in memory, reloaded when its size or mtime changes."""

    def __init__(self, path):
        self.path = Path(path)
        self._key = None
        self.rows: list = []
        self._lock = threading.Lock()

    def load(self) -> list:
        with self._lock:
            try:
                st = self.path.stat()
            except FileNotFoundError:
                self._key, self.rows = None, []
                return self.rows
            key = (st.st_size, st.st_mtime_ns)
            if key != self._key:
                rows = []
                with open(self.path, errors="replace") as f:
                    for line in f:
                        try:
                            row = json.loads(line)
                        except ValueError:
                            continue
                        if isinstance(row, dict):
                            rows.append(row)
                self.rows, self._key = rows, key
            return self.rows


def browse(rows, agent: str = "", kind: str = "", q: str = "", page: int = 1, page_size: int = 50) -> dict:
    sel = rows
    if agent:
        sel = [r for r in sel if r.get("agent") == agent]
    if kind:
        sel = [r for r in sel if r.get("kind") == kind]
    if q:
        needle = q.lower()
        sel = [r for r in sel if needle in str(r.get("text", "")).lower()]
    start = (page - 1) * page_size
    return {"total": len(sel), "page": page, "page_size": page_size, "rows": sel[start:start + page_size]}


def eval_results(root) -> dict:
    d = read_json(Path(root) / "results" / "eval.json")
    if "missing" in d or set(d) == {"error"}:
        return d
    if isinstance(d.get("scorers"), dict):
        return {**d, "split": d.get("split", "unknown"), 'legacy':d.get('schema_version') != 2}
    return {"split": "unknown", "scorers": d, 'legacy':True}


def rules_view(root) -> dict:
    root = Path(root)
    try:
        rules = [{"type": "action" if isinstance(r, ActionRule) else "sequence", **asdict(r)}
                 for r in load_rules_v2(root / "rules" / "rules.json")]
    except (ValueError, OSError) as e:
        rules = {"error": str(e)}
    features_path = root / "rules" / "features.json"
    try:
        features = [asdict(f) for f in load_features(features_path)] if features_path.exists() else []
    except (ValueError, OSError) as e:
        features = {"error": str(e)}
    return {"rules": rules, "features": features}


def labelled_files(root) -> list[str]:
    """The only files the eval job accepts: data/labelled/*.jsonl and the bundled sample."""
    root = Path(root)
    found = sorted(p.relative_to(root).as_posix() for p in (root / "data" / "labelled").glob("*.jsonl")
                   if p.is_file())
    if (root / LABELLED_FIXTURE).is_file():
        found.append(LABELLED_FIXTURE)
    return found
