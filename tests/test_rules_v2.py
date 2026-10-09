import json

import pytest

from monitor.rules import ActionRule, SequenceRule, evaluate_rules, load_rules_v2
from monitor.schema import Action


def act(text="ls", kind="shell"):
    return Action(agent="t", session_id="s", index=0, tool="Bash", kind=kind, text=text)


def load(tmp_path, rules):
    p = tmp_path / "rules.json"
    p.write_text(json.dumps(rules))
    return load_rules_v2(p)


def test_v1_rule_reads_as_action_rule(tmp_path):
    [r] = load(tmp_path, [{"id": "old", "pattern": "ALPHA_MARKER", "weight": 12, "kinds": ["shell"]}])
    assert r == ActionRule(id="old", category="other", score=10.0, pattern="ALPHA_MARKER", kinds=("shell",))


def test_action_rule_conditions_all_must_hold():
    r = ActionRule(id="a", category="other", score=4.0, pattern="ALPHA", kinds=("shell",),
                   tags_any=("t1", "t2"), tags_all=("t3",))
    assert evaluate_rules(act("ALPHA"), {"t1", "t3"}, [], [r]).hits == ["a"]
    assert evaluate_rules(act("ALPHA"), {"t1"}, [], [r]).hits == []
    assert evaluate_rules(act("ALPHA"), {"t3"}, [], [r]).hits == []
    assert evaluate_rules(act("ALPHA", kind="file_read"), {"t1", "t3"}, [], [r]).hits == []
    assert evaluate_rules(act("other"), {"t1", "t3"}, [], [r]).hits == []


def test_score_is_max_not_sum_and_categories_dedup():
    rules = [ActionRule(id="a", category="other", score=4.0, pattern="X"),
             ActionRule(id="b", category="other", score=6.0, pattern="X", reason="why b")]
    res = evaluate_rules(act("X"), set(), [], rules)
    assert res.score == 6.0 and res.hits == ["a", "b"] and res.categories == ["other"] and res.reasons == ["why b"]


def test_added_tags_feed_sequence_rules_within_window():
    rules = [ActionRule(id="mark", category="other", score=2.0, pattern="BETA", add_tags=("beta_seen",)),
             SequenceRule(id="seq", category="data_exfiltration", score=9.0, previous_tag="alpha_seen",
                          current_tag="beta_seen", within_actions=2)]
    res = evaluate_rules(act("BETA"), set(), [{"alpha_seen"}, set()], rules)
    assert res.hits == ["mark", "seq"] and res.score == 9.0 and "data_exfiltration" in res.categories
    res = evaluate_rules(act("BETA"), set(), [{"alpha_seen"}, set(), set()], rules)
    assert res.hits == ["mark"] and res.score == 2.0


def test_load_rules_v2_parses_both_types(tmp_path):
    rules = load(tmp_path, [
        {"id": "a", "type": "action", "category": "unapproved_dependency", "match": {"tags_any": ["t"]},
         "score": 3, "add_tags": ["x"], "reason": "r"},
        {"id": "s", "type": "sequence", "category": "data_exfiltration", "previous_tag": "x", "current_tag": "y",
         "within_actions": 5, "score": 9}])
    assert rules[0] == ActionRule(id="a", category="unapproved_dependency", score=3.0, tags_any=("t",),
                                  add_tags=("x",), reason="r")
    assert rules[1] == SequenceRule(id="s", category="data_exfiltration", score=9.0, previous_tag="x",
                                    current_tag="y", within_actions=5)


@pytest.mark.parametrize("bad,msg", [
    ({"id": "a", "type": "action", "category": "nope", "match": {"pattern": "x"}, "score": 1}, "category must be one of"),
    ({"id": "a", "type": "action", "category": "other", "match": {}, "score": 1}, "match must be a non-empty object"),
    ({"id": "a", "type": "action", "category": "other", "match": {"regex": "x"}, "score": 1}, "unknown match keys"),
    ({"id": "a", "type": "action", "category": "other", "match": {"pattern": "("}, "score": 1}, "invalid regex"),
    ({"id": "a", "type": "action", "category": "other", "match": {"pattern": "x"}, "score": 11}, "between 0 and 10"),
    ({"id": "s", "type": "sequence", "category": "other", "previous_tag": "x", "current_tag": "y",
      "within_actions": 0, "score": 1}, "within_actions"),
    ({"id": "s", "type": "trajectory", "category": "other", "score": 1}, "type must be"),
])
def test_load_rules_v2_rejects_bad_rules(tmp_path, bad, msg):
    with pytest.raises(ValueError, match=msg):
        load(tmp_path, [bad])
