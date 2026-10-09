"""Labelled trajectories (user-authored or converted public data) -> Actions."""
import json
import random

from monitor.schema import Action, KINDS

_REQUIRED = ("trajectory_id", "task", "label", "actions")


def load_labelled(path) -> list[Action]:
    out: list[Action] = []
    seen = set()
    with open(path) as f:
        for n, line in enumerate(f, 1):
            if not line.strip():
                continue
            t = json.loads(line)
            if not isinstance(t, dict):
                raise ValueError(f"{path} line {n}: trajectory must be an object")
            missing = [k for k in _REQUIRED if k not in t]
            if missing:
                raise ValueError(f"{path} line {n}: missing {missing}")
            tid = t['trajectory_id']
            if not isinstance(tid, str) or not tid or tid in seen:
                raise ValueError(f"{path} line {n}: invalid or duplicate trajectory_id")
            seen.add(tid)
            if type(t['label']) is not int or t['label'] not in (0, 1):
                raise ValueError(f"{path} line {n}: label must be integer 0 or 1")
            if not isinstance(t['task'], str) or not isinstance(t['actions'], list) or not t['actions']:
                raise ValueError(f"{path} line {n}: task must be text and actions must be non-empty")
            if t.get('split') not in (None, 'dev', 'test'):
                raise ValueError(f"{path} line {n}: split must be dev or test")
            for i, a in enumerate(t["actions"]):
                if not isinstance(a, dict) or a.get('kind', 'other') not in KINDS:
                    raise ValueError(f"{path} line {n}: invalid action or kind")
                label = a.get('label', t['label'])
                if type(label) is not int or label not in (0, 1):
                    raise ValueError(f"{path} line {n}: action label must be integer 0 or 1")
                out.append(Action(agent="labelled", session_id=t["trajectory_id"], index=i, tool=a.get("tool", ""),
                                  kind=a.get("kind", "other"), text=a.get("text", ""), task=t["task"],
                                  label=label, category=t.get("category"), trajectory_id=tid,
                                  output=a.get('output', ''), cwd=a.get('cwd', t.get('cwd')), path=a.get('path'),
                                  group_id=t.get('group_id', tid), split=t.get('split'),
                                  policy=a.get('policy', t.get('policy', {}))))
    return out


def split_by_trajectory(actions, test_fraction: float = 0.4, seed: int = 0):
    explicit = {a.split for a in actions}
    if explicit != {None} and actions:
        if None in explicit:
            raise ValueError('every trajectory needs a split when any explicit split is provided')
        groups = {}
        for a in actions:
            group = a.group_id or a.trajectory_id
            if group in groups and groups[group] != a.split:
                raise ValueError('paired group crosses explicit dev/test splits')
            groups[group] = a.split
        return [a for a in actions if a.split == 'dev'], [a for a in actions if a.split == 'test']
    ids = sorted({a.group_id or a.trajectory_id for a in actions})
    random.Random(seed).shuffle(ids)
    test_ids = set(ids[: round(len(ids) * test_fraction)])
    return [a for a in actions if (a.group_id or a.trajectory_id) not in test_ids], [a for a in actions if (a.group_id or a.trajectory_id) in test_ids]
