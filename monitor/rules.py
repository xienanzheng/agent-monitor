"""Rule engine. Patterns are data, kept in rules/rules.json and maintained by the user."""
import json
import math
import re
from dataclasses import dataclass, field
from functools import lru_cache

from monitor.categories import CATEGORIES
from monitor.schema import KINDS, Action


@dataclass(frozen=True)
class Rule:
    id: str
    pattern: str
    weight: float
    kinds: tuple[str, ...] = ()


@lru_cache(maxsize=512)
def _compiled(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.I | re.S)


def _validate(r, i: int) -> Rule:
    if not isinstance(r, dict):
        raise ValueError(f"rule at index {i}: must be a JSON object")
    name = f"rule {r['id']}" if r.get("id") else f"rule at index {i}"
    missing = [k for k in ("id", "pattern", "weight") if k not in r]
    if missing:
        raise ValueError(f"{name}: missing {missing}")
    if not isinstance(r["pattern"], str):
        raise ValueError(f"{name}: pattern must be a string")
    w = r["weight"]
    if isinstance(w, bool) or not isinstance(w, (int, float)) or not math.isfinite(w):
        raise ValueError(f"{name}: weight must be a number, got {w!r}")
    kinds = r.get("kinds", [])
    if not isinstance(kinds, list):
        raise ValueError(f"{name}: kinds must be a list of {list(KINDS)}, got {kinds!r}")
    unknown = [k for k in kinds if k not in KINDS]
    if unknown:
        raise ValueError(f"{name}: unknown kinds {unknown}; valid kinds are {list(KINDS)}")
    try:
        _compiled(r["pattern"])
    except re.error as e:
        raise ValueError(f"{name}: invalid regex: {e}") from e
    return Rule(id=str(r["id"]), pattern=r["pattern"], weight=float(w), kinds=tuple(kinds))


def load_rules(path) -> list[Rule]:
    with open(path) as f:
        data = json.load(f)
    return [_validate(r, i) for i, r in enumerate(data)]


def score_rules(action: Action, rules: list[Rule]) -> tuple[float, list[str]]:
    total, hits = 0.0, []
    for r in rules:
        if r.kinds and action.kind not in r.kinds:
            continue
        if _compiled(r.pattern).search(action.text or ""):
            total += r.weight
            hits.append(r.id)
    return max(0.0, min(total, 10.0)), hits


# ---------------------------------------------------------------- rules v2 (action + sequence)

@dataclass(frozen=True)
class ActionRule:
    id: str
    category: str
    score: float
    pattern: str | None = None
    kinds: tuple[str, ...] = ()
    tags_any: tuple[str, ...] = ()
    tags_all: tuple[str, ...] = ()
    add_tags: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class SequenceRule:
    id: str
    category: str
    score: float
    previous_tag: str
    current_tag: str
    within_actions: int
    reason: str = ""


@dataclass
class RuleResult:
    score: float = 0.0
    hits: list = field(default_factory=list)
    categories: list = field(default_factory=list)
    added_tags: set = field(default_factory=set)
    reasons: list = field(default_factory=list)


def _strs(value, name: str, what: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(x, str) or not x for x in value):
        raise ValueError(f"{name}: {what} must be a list of non-empty strings")
    return tuple(value)


def _validate_v2(r, i: int):
    if not isinstance(r, dict):
        raise ValueError(f"rule at index {i}: must be a JSON object")
    if "type" not in r:  # v1 rule {id, pattern, weight, kinds}: an action rule with score = weight
        v1 = _validate(r, i)
        return ActionRule(id=v1.id, category="other", score=max(0.0, min(v1.weight, 10.0)),
                          pattern=v1.pattern, kinds=v1.kinds)
    name = f"rule {r['id']}" if r.get("id") else f"rule at index {i}"
    if not isinstance(r.get("id"), str) or not r["id"]:
        raise ValueError(f"{name}: missing id")
    category = r.get("category")
    if category not in CATEGORIES:
        raise ValueError(f"{name}: category must be one of {list(CATEGORIES)}, got {category!r}")
    score = r.get("score")
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
        raise ValueError(f"{name}: score must be a number, got {score!r}")
    if not 0 <= score <= 10:
        raise ValueError(f"{name}: score must be between 0 and 10")
    reason = r.get("reason", "")
    if not isinstance(reason, str):
        raise ValueError(f"{name}: reason must be a string")
    if r["type"] == "action":
        match = r.get("match")
        if not isinstance(match, dict) or not match:
            raise ValueError(f"{name}: match must be a non-empty object")
        unknown = set(match) - {"pattern", "kinds", "tags_any", "tags_all"}
        if unknown:
            raise ValueError(f"{name}: unknown match keys {sorted(unknown)}")
        pattern = match.get("pattern")
        if pattern is not None:
            if not isinstance(pattern, str):
                raise ValueError(f"{name}: match.pattern must be a string")
            try:
                _compiled(pattern)
            except re.error as e:
                raise ValueError(f"{name}: invalid regex: {e}") from e
        kinds = _strs(match.get("kinds", []), name, "match.kinds")
        bad = [k for k in kinds if k not in KINDS]
        if bad:
            raise ValueError(f"{name}: unknown kinds {bad}; valid kinds are {list(KINDS)}")
        return ActionRule(id=r["id"], category=category, score=float(score), pattern=pattern, kinds=kinds,
                          tags_any=_strs(match.get("tags_any", []), name, "match.tags_any"),
                          tags_all=_strs(match.get("tags_all", []), name, "match.tags_all"),
                          add_tags=_strs(r.get("add_tags", []), name, "add_tags"), reason=reason)
    if r["type"] == "sequence":
        for key in ("previous_tag", "current_tag"):
            if not isinstance(r.get(key), str) or not r[key]:
                raise ValueError(f"{name}: {key} must be a non-empty string")
        within = r.get("within_actions")
        if isinstance(within, bool) or not isinstance(within, int) or within < 1:
            raise ValueError(f"{name}: within_actions must be an integer >= 1")
        return SequenceRule(id=r["id"], category=category, score=float(score), previous_tag=r["previous_tag"],
                            current_tag=r["current_tag"], within_actions=within, reason=reason)
    raise ValueError(f"{name}: type must be 'action' or 'sequence', got {r['type']!r}")


def load_rules_v2(path) -> list:
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("rules file must be a JSON list")
    return [_validate_v2(r, i) for i, r in enumerate(data)]


def _action_matches(rule: ActionRule, action: Action, tags: set) -> bool:
    if rule.kinds and action.kind not in rule.kinds:
        return False
    if rule.tags_any and not (set(rule.tags_any) & tags):
        return False
    if rule.tags_all and not set(rule.tags_all) <= tags:
        return False
    if rule.pattern is not None and not _compiled(rule.pattern).search(action.text or ""):
        return False
    return True


def evaluate_rules(action: Action, tags, history, rules) -> RuleResult:
    """Score = max of matched rules (never a sum). history: tag sets of earlier actions, oldest first."""
    res = RuleResult()
    tags = set(tags)

    def hit(rule):
        res.hits.append(rule.id)
        res.score = max(res.score, rule.score)
        if rule.category not in res.categories:
            res.categories.append(rule.category)
        if rule.reason:
            res.reasons.append(rule.reason)

    for rule in rules:
        if isinstance(rule, ActionRule) and _action_matches(rule, action, tags):
            hit(rule)
            res.added_tags |= set(rule.add_tags)
    current = tags | res.added_tags
    for rule in rules:
        if (isinstance(rule, SequenceRule) and rule.current_tag in current
                and any(rule.previous_tag in past for past in history[-rule.within_actions:])):
            hit(rule)
    res.score = max(0.0, min(res.score, 10.0))
    return res
