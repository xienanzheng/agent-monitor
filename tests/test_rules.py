import json

from monitor.rules import Rule, load_rules, score_rules
from monitor.schema import Action


def act(text, kind="shell"):
    return Action(agent="test", session_id="s", index=0, tool="Bash", kind=kind, text=text)


def test_matching_rule_adds_its_weight():
    rules = [Rule(id="r1", pattern=r"ALPHA_MARKER", weight=4.0)]
    assert score_rules(act("echo ALPHA_MARKER"), rules) == (4.0, ["r1"])


def test_kind_filter_limits_where_rule_applies():
    rules = [Rule(id="r1", pattern=r"ALPHA_MARKER", weight=4.0, kinds=("file_write",))]
    assert score_rules(act("ALPHA_MARKER", kind="shell"), rules) == (0.0, [])
    assert score_rules(act("ALPHA_MARKER", kind="file_write"), rules) == (4.0, ["r1"])


def test_score_is_capped_at_ten():
    rules = [Rule(id=f"r{i}", pattern="BETA", weight=6.0) for i in range(3)]
    assert score_rules(act("BETA"), rules)[0] == 10.0


def test_load_rules_reads_json_and_rejects_bad_regex(tmp_path):
    p = tmp_path / "rules.json"
    p.write_text(json.dumps([{"id": "r1", "pattern": "GAMMA", "weight": 2}]))
    assert load_rules(p) == [Rule(id="r1", pattern="GAMMA", weight=2.0, kinds=())]
    p.write_text(json.dumps([{"id": "bad", "pattern": "(", "weight": 1}]))
    try:
        load_rules(p)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "bad" in str(e)


def test_score_is_floored_at_zero():
    rules = [Rule(id="r1", pattern="DELTA", weight=-5.0)]
    assert score_rules(act("DELTA"), rules) == (0.0, ["r1"])


def _load_error(tmp_path, rules) -> str:
    import pytest

    p = tmp_path / "rules.json"
    p.write_text(json.dumps(rules))
    with pytest.raises(ValueError) as e:
        load_rules(p)
    return str(e.value)


def test_load_rules_rejects_string_kinds(tmp_path):
    msg = _load_error(tmp_path, [{"id": "r-str", "pattern": "GAMMA", "weight": 1, "kinds": "shell"}])
    assert "r-str" in msg and "kinds" in msg


def test_load_rules_rejects_unknown_kind(tmp_path):
    msg = _load_error(tmp_path, [{"id": "r-kind", "pattern": "GAMMA", "weight": 1, "kinds": ["shel"]}])
    assert "r-kind" in msg and "shel" in msg


def test_load_rules_rejects_non_numeric_weight(tmp_path):
    msg = _load_error(tmp_path, [{"id": "r-w", "pattern": "GAMMA", "weight": "high"}])
    assert "r-w" in msg and "weight" in msg
    msg = _load_error(tmp_path, [{"id": "r-b", "pattern": "GAMMA", "weight": True}])
    assert "r-b" in msg and "weight" in msg


def test_load_rules_rejects_missing_fields_naming_rule_or_index(tmp_path):
    msg = _load_error(tmp_path, [{"id": "ok", "pattern": "GAMMA", "weight": 1}, {"pattern": "GAMMA", "weight": 1}])
    assert "index 1" in msg and "id" in msg
    msg = _load_error(tmp_path, [{"id": "r-np", "weight": 1}])
    assert "r-np" in msg and "pattern" in msg
    msg = _load_error(tmp_path, [{"id": "r-nw", "pattern": "GAMMA"}])
    assert "r-nw" in msg and "weight" in msg


def test_load_rules_accepts_absent_or_valid_kinds(tmp_path):
    p = tmp_path / "rules.json"
    p.write_text(json.dumps([{"id": "a", "pattern": "G", "weight": 1},
                             {"id": "b", "pattern": "G", "weight": 1.5, "kinds": ["shell", "file_write"]}]))
    assert [r.kinds for r in load_rules(p)] == [(), ("shell", "file_write")]
