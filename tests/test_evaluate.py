import json
from pathlib import Path

from monitor.dataset import load_labelled
from monitor.evaluate import evaluate, max_scorer, rules_scorer, sample_actions, scan_real, score_sample
from monitor.rules import Rule
from monitor.schema import Action

FIX = Path(__file__).parent / "fixtures" / "labelled_sample.jsonl"
RULES = [Rule(id="a", pattern="ALPHA_MARKER|BETA_MARKER", weight=8.0)]


def test_evaluate_reports_metrics_per_scorer_with_dev_threshold():
    acts = load_labelled(FIX)
    dev = [a for a in acts if a.trajectory_id in ("t1", "t2")]
    test = [a for a in acts if a.trajectory_id in ("t3", "t4")]
    res = evaluate(dev, test, {"rules": rules_scorer(RULES)})
    r = res["rules"]
    assert r["auc"] == 1.0
    assert r["threshold_at_5pct"] == 8.0
    assert r["test_confusion"]["tp"] == 1 and r["test_confusion"]["fp"] == 0
    assert r["median_latency_ms"] >= 0


def test_max_scorer_ignores_none_and_returns_none_when_all_fail():
    def none(a, c):
        return None

    def three(a, c):
        return 3.0

    assert max_scorer(none, three)(None, []) == 3.0
    assert max_scorer(none, none)(None, []) is None


def test_scan_real_streams_and_counts(tmp_path):
    p = tmp_path / "real.jsonl"
    rows = [{"agent": "codex", "session_id": "s", "index": i, "tool": "shell", "kind": "shell",
             "text": "echo ALPHA_MARKER" if i == 3 else "ls"} for i in range(10)]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    out = scan_real(p, rules_scorer(RULES), threshold=5.0, top_n=5)
    assert out["n_actions"] == 10 and out["n_alerts"] == 1
    assert out["alerts_per_1000"] == 100.0
    assert out["top_alerts"][0]["text"] == "echo ALPHA_MARKER"


def test_scan_real_skips_malformed_lines(tmp_path):
    p = tmp_path / "malformed.jsonl"
    lines = [
        json.dumps({"agent": "codex", "session_id": "s", "index": 0, "tool": "shell", "kind": "shell", "text": "ls"}),
        "not json {",
        json.dumps({"agent": "codex", "session_id": "s", "index": 1, "tool": "shell", "kind": "shell", "text": "ls"}),
        json.dumps({"agent": "x"}),  # valid JSON but missing required fields
        json.dumps({"agent": "codex", "session_id": "s", "index": 2, "tool": "shell", "kind": "shell", "text": "ls"}),
    ]
    p.write_text("\n".join(lines) + "\n")
    out = scan_real(p, rules_scorer(RULES), threshold=5.0, top_n=5)
    assert out["n_actions"] == 3
    assert out["n_skipped"] == 2


def test_scan_real_keeps_highest_scoring_alerts_in_order(tmp_path):
    p = tmp_path / "ordered.jsonl"
    rows = [{"agent": "codex", "session_id": "s", "index": i, "tool": "shell", "kind": "shell", "text": "x"} 
            for i in range(6)]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    scorer = lambda a, c: float(a.index)
    out = scan_real(p, scorer, threshold=1.0, top_n=3)
    assert out["n_alerts"] == 5
    assert [t["score"] for t in out["top_alerts"]] == [5.0, 4.0, 3.0]


def test_sample_actions_is_deterministic_and_bounded(tmp_path):
    p = tmp_path / "sample.jsonl"
    rows = [{"agent": "codex", "session_id": "s", "index": i, "tool": "shell", "kind": "shell", "text": "ls"}
            for i in range(20)]
    lines = [json.dumps(r) for r in rows] + ["not json {"]
    p.write_text("\n".join(lines) + "\n")

    s1 = sample_actions(p, 5, seed=0)
    assert len(s1) == 5
    assert [a.index for a in s1] == [a.index for a in sample_actions(p, 5, seed=0)]
    assert all(a.index in range(20) for a in s1)
    assert len(sample_actions(p, 50)) == 20


def test_score_sample_counts_none_and_alerts():
    actions = [Action(agent="codex", session_id="s", index=i, tool="shell", kind="shell", text="x")
               for i in range(4)]

    def scorer(a, c):
        return None if a.index == 0 else float(a.index)

    out = score_sample(actions, scorer, threshold=2.0)
    assert out["n_actions"] == 4
    assert out["n_scored"] == 3
    assert out["n_alerts"] == 2
    assert out["alerts_per_1000"] == round(1000 * 2 / 3, 2)
    assert [t["score"] for t in out["top_alerts"]] == [3.0, 2.0]


def _counting_transport(reply='{"score": 2, "reason": "ok"}'):
    calls = []

    def transport(url, payload, timeout):
        calls.append(payload)
        return {"done": True, "done_reason": "stop", "message": {"content": reply}}

    return transport, calls


def _down(url, payload, timeout):
    raise ConnectionRefusedError("ollama down")


def test_combined_scorer_reuses_judge_scores_instead_of_calling_twice():
    from monitor.evaluate import judge_scorer
    from monitor.llm_judge import Judge

    acts = load_labelled(FIX)
    dev = [a for a in acts if a.trajectory_id in ("t1", "t2")]
    test = [a for a in acts if a.trajectory_id in ("t3", "t4")]
    transport, calls = _counting_transport()
    js = judge_scorer(Judge(transport=transport))
    evaluate(dev, test, {"judge": js, "max(rules,judge)": max_scorer(rules_scorer(RULES), js)})
    assert len(calls) == len(dev) + len(test)  # 6 distinct actions, each judged once


def test_evaluate_reports_judge_failures_on_judge_and_combined_rows():
    from monitor.evaluate import judge_scorer
    from monitor.llm_judge import Judge
    from monitor.report import render_report

    acts = load_labelled(FIX)
    dev = [a for a in acts if a.trajectory_id in ("t1", "t2")]
    test = [a for a in acts if a.trajectory_id in ("t3", "t4")]
    js = judge_scorer(Judge(transport=_down))
    res = evaluate(dev, test, {"rules": rules_scorer(RULES), "judge": js,
                               "max(rules,judge)": max_scorer(rules_scorer(RULES), js)})
    assert "judge_calls" not in res["rules"]
    for name in ("judge", "max(rules,judge)"):
        assert res[name]["judge_calls"] == 6 and res[name]["judge_failures"] == 6
    md = render_report({"split": "test", "scorers": res}, None)
    assert "6 of 6 calls" in md


def test_score_sample_reports_judge_failures_when_judge_is_down():
    from monitor.evaluate import judge_scorer
    from monitor.llm_judge import Judge
    from monitor.report import render_report

    actions = [Action(agent="codex", session_id="s", index=i, tool="shell", kind="shell", text=f"ls {i}")
               for i in range(3)]
    scorer = max_scorer(rules_scorer(RULES), judge_scorer(Judge(transport=_down)))
    js = score_sample(actions, scorer, threshold=5.0)
    assert js["judge_calls"] == 3 and js["judge_failures"] == 3
    md = render_report(None, {"n_actions": 3, "n_alerts": 0, "alerts_per_1000": 0.0, "top_alerts": [],
                              "judge_sample": js})
    assert "Judge failures: 3 of 3 calls" in md


def test_evaluate_reports_class_counts_of_evaluated_split():
    acts = load_labelled(FIX)
    dev = [a for a in acts if a.trajectory_id in ("t1", "t2")]
    res = evaluate(dev, dev, {"rules": rules_scorer(RULES)})
    assert res["rules"]["n_pos"] == 1 and res["rules"]["n_neg"] == 3


def test_cached_judge_latency_still_counts_in_timings():
    from monitor.evaluate import judge_scorer

    class SlowJudge:
        def score(self, action, context):
            import time
            time.sleep(0.005)
            from monitor.llm_judge import JudgeResult
            return JudgeResult(1.0, "", 0.005)

    acts = load_labelled(FIX)
    dev = [a for a in acts if a.trajectory_id in ("t1", "t2")]
    res = evaluate(dev, dev, {"judge": judge_scorer(SlowJudge())})  # second pass is all cache hits
    assert res["judge"]["median_latency_ms"] >= 4.0
