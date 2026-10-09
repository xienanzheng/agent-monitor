import json

from monitor.evaluate import evaluate, rules_v2_scorer, scan_real
from monitor.features import Feature
from monitor.rules import ActionRule, SequenceRule
from monitor.schema import Action

RULES = [ActionRule(id="a", category="other", score=2.0, pattern="ALPHA_MARKER", add_tags=("alpha_seen",)),
         SequenceRule(id="s", category="data_exfiltration", score=9.0, previous_tag="alpha_seen", current_tag="beta",
                      within_actions=3)]
FEATS = [Feature(tag="beta", pattern="BETA_MARKER")]


def act(i, text, label=0, sid="t1"):
    return Action(agent="labelled", session_id=sid, index=i, tool="Bash", kind="shell", text=text, label=label,
                  trajectory_id=sid)


def test_v2_scorer_sees_sequences_within_a_trajectory():
    s = rules_v2_scorer(RULES, FEATS)
    a0, a1 = act(0, "echo ALPHA_MARKER"), act(1, "echo BETA_MARKER")
    assert s(a0, []) == 2.0 and s(a1, [a0]) == 9.0 and s(a1, []) == 0.0


def test_v2_scorer_in_evaluate_and_scan_real(tmp_path):
    dev = [act(0, "echo ALPHA_MARKER", 0, "t1"), act(1, "echo BETA_MARKER", 1, "t1"), act(0, "ls", 0, "t2")]
    res = evaluate(dev, dev, {"rules": rules_v2_scorer(RULES, FEATS)})
    assert res["rules"]["auc"] == 1.0
    p = tmp_path / "real.jsonl"
    p.write_text("".join(json.dumps(a.to_dict()) + "\n" for a in dev))
    assert scan_real(p, rules_v2_scorer(RULES, FEATS), threshold=5.0)["n_alerts"] == 1
