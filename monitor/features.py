"""Feature extraction: an action -> a set of tags.

Built-in tags are structural only. The detection vocabulary is user data in rules/features.json."""
import json
import os
import re
from dataclasses import dataclass

from monitor.rules import _compiled
from monitor.schema import KINDS, Action

CONTEXT_TAGS = frozenset({"full_access_mode", "outside_workspace"})
FULL_ACCESS_MODES = frozenset({"bypassPermissions", "danger-full-access"})
FIELDS = ("text", "output", "path")
_MARKER = re.compile(r"\[REDACTED:(?!email\])[a-z_]+\]")


@dataclass(frozen=True)
class Feature:
    tag: str
    pattern: str
    kinds: tuple[str, ...] = ()
    fields: tuple[str, ...] = ("text",)


def _validate(f, i: int) -> Feature:
    if not isinstance(f, dict):
        raise ValueError(f"feature at index {i}: must be a JSON object")
    tag = f.get("tag")
    name = f"feature {tag}" if isinstance(tag, str) and tag else f"feature at index {i}"
    if not isinstance(tag, str) or not tag:
        raise ValueError(f"{name}: missing tag")
    if not isinstance(f.get("pattern"), str):
        raise ValueError(f"{name}: pattern must be a string")
    kinds = f.get("kinds", [])
    flds = f.get("fields", ["text"])
    if not isinstance(kinds, list) or any(k not in KINDS for k in kinds):
        raise ValueError(f"{name}: kinds must be a list drawn from {list(KINDS)}")
    if not isinstance(flds, list) or not flds or any(x not in FIELDS for x in flds):
        raise ValueError(f"{name}: fields must be a non-empty list drawn from {list(FIELDS)}")
    try:
        _compiled(f["pattern"])
    except re.error as e:
        raise ValueError(f"{name}: invalid regex: {e}") from e
    return Feature(tag=tag, pattern=f["pattern"], kinds=tuple(kinds), fields=tuple(flds))


def load_features(path) -> list[Feature]:
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("features file must be a JSON list")
    return [_validate(f, i) for i, f in enumerate(data)]


def _outside(path, cwd) -> bool:
    if not path or not cwd or not os.path.isabs(path) or not os.path.isabs(cwd):
        return False
    p, c = os.path.normpath(path), os.path.normpath(cwd)
    return os.path.commonpath([p, c]) != c


def extract_tags(action: Action, features, *, permission_mode: str = "", path: str | None = None) -> set[str]:
    tags: set[str] = set()
    if '[REDACTED:email]' in (action.text or '') or '[REDACTED:email]' in (action.output or ''):
        tags.add('personal_data')
    if _MARKER.search(action.text or ""):
        tags.add("secret_marker")
    if _MARKER.search(action.output or ""):
        tags.add("secret_in_output")
    if _outside(path, action.cwd):
        tags.add("outside_workspace")
    if permission_mode in FULL_ACCESS_MODES or (action.policy or {}).get("sandbox") in FULL_ACCESS_MODES:
        tags.add("full_access_mode")
    if action.kind in ("network", "browser"):
        tags.add("network_tool")
    if action.kind == "agent":
        tags.add("new_subagent")
    if action.kind == "other":
        tags.add("unknown_tool")
    values = {"text": action.text or "", "output": action.output or "", "path": path or ""}
    for f in features:
        if f.kinds and action.kind not in f.kinds:
            continue
        if any(_compiled(f.pattern).search(values[x]) for x in f.fields):
            tags.add(f.tag)
    return tags
