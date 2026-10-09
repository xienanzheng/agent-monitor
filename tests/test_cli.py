from monitor.report import render_report


def test_report_contains_table_rows_and_handles_missing_metrics():
    md = render_report(
        {"rules": {"auc": 0.91, "tpr_at_fpr": {"0.01": 0.5, "0.05": 0.8}, "threshold_at_5pct": 6.0,
                   "test_confusion": {"precision": 0.75, "recall": 0.8}, "n_test": 40, "n_scored": 40},
         "judge": {"auc": None, "tpr_at_fpr": {"0.01": None, "0.05": None}, "threshold_at_5pct": None,
                   "test_confusion": None, "n_test": 40, "n_scored": 0}},
        {"n_actions": 21276, "n_alerts": 42, "alerts_per_1000": 1.97, "top_alerts": []},
    )
    assert "| rules | 0.910 | 0.50 | 0.80 |" in md
    assert "| judge | n/a | n/a | n/a |" in md
    assert "1.97 alerts per 1,000" in md


def test_report_renders_judge_sample_block():
    md = render_report({}, {
        "n_actions": 10, "n_alerts": 0, "alerts_per_1000": 0.0, "top_alerts": [],
        "judge_sample": {"n_actions": 5, "n_scored": 4, "n_alerts": 1, "alerts_per_1000": 250.0,
                          "top_alerts": [{"score": 7.0, "agent": "codex", "tool": "shell",
                                          "text": "echo ALPHA_MARKER"}]},
    })
    assert "Judge sample (rules + judge, 4 of 5 sampled actions scored): 1 alerts, 250.0 per 1,000." in md
    assert "| 7.0 | codex | shell | `echo ALPHA_MARKER` |" in md


def test_hook_command_uses_isolated_mode_and_quoted_venv_python(tmp_path):
    from monitor.cli import hook_command

    cmd = hook_command(tmp_path)
    assert f'"{tmp_path / ".venv" / "bin" / "python"}"' in cmd
    assert " -I -m monitor.hook" in cmd


def test_install_refuses_when_venv_python_missing(tmp_path):
    import pytest

    from monitor.cli import install_live_hook

    settings = tmp_path / "home" / ".claude" / "settings.json"
    with pytest.raises(SystemExit) as e:
        install_live_hook(tmp_path, settings)
    assert "uv sync" in str(e.value.code)
    assert not settings.exists() and not settings.parent.exists()


ROW = {"auc": 0.91, "tpr_at_fpr": {"0.01": 0.5, "0.05": 0.8}, "threshold_at_5pct": 6.0,
       "test_confusion": {"precision": 0.75, "recall": 0.8}, "n_test": 40, "n_scored": 40,
       "n_pos": 10, "n_neg": 30, "median_latency_ms": 12.5}
REAL = {"n_actions": 21276, "n_alerts": 42, "alerts_per_1000": 1.97, "top_alerts": [], "n_skipped": 3}


def test_report_without_eval_renders_real_traffic_only():
    md = render_report(None, REAL)
    assert "## Real traffic" in md and "1.97 alerts per 1,000" in md
    assert "| monitor |" not in md


def test_report_shows_split_latency_skipped_and_explains_na():
    one_class = {**ROW, "auc": None, "tpr_at_fpr": {"0.01": None, "0.05": None}, "n_pos": 0, "n_neg": 40}
    no_scores = {**ROW, "auc": None, "tpr_at_fpr": {"0.01": None, "0.05": None}, "n_scored": 0,
                 "n_pos": 0, "n_neg": 0, "judge_calls": 40, "judge_failures": 40}
    md = render_report({"split": "dev", "scorers": {"rules": ROW, "judge": no_scores, "other": one_class}}, REAL)
    assert "Evaluated split: dev" in md
    assert "median latency (ms)" in md and "| 12.5 |" in md
    assert "n/a (other): only one class in the evaluated split (pos=0, neg=40)" in md
    assert "n/a (judge): no scores (judge failed or unavailable)" in md
    assert "40 of 40 calls" in md
    assert "3 malformed lines skipped" in md


def test_render_files_handles_missing_eval_and_missing_everything(tmp_path):
    import json

    from monitor.report import render_files

    real = tmp_path / "real_scan.json"
    assert render_files(tmp_path / "eval.json", real) is None
    real.write_text(json.dumps(REAL))
    assert "## Real traffic" in render_files(tmp_path / "eval.json", real)


def test_eval_defaults_to_dev_split_and_honours_out_and_final(tmp_path):
    import json
    from pathlib import Path

    from monitor.cli import main
    from monitor.dataset import load_labelled, split_by_trajectory

    fix = Path(__file__).parent / "fixtures" / "labelled_sample.jsonl"
    dev, test = split_by_trajectory(load_labelled(fix))
    main(["eval", "--labelled", str(fix), "--no-judge", "--out", str(tmp_path / "dev.json")])
    d = json.loads((tmp_path / "dev.json").read_text())
    assert d["split"] == "dev" and d["scorers"]["rules"]["n_test"] == len(dev)
    main(["eval", "--labelled", str(fix), "--no-judge", "--final", "--out", str(tmp_path / "test.json")])
    t = json.loads((tmp_path / "test.json").read_text())
    assert t["split"] == "test" and t["scorers"]["rules"]["n_test"] == len(test)
