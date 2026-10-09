import json
from pathlib import Path

import pytest

from monitor.runs import run_eval, run_scan
from monitor.schema import Action

ROOT = Path(__file__).resolve().parent.parent


def project(tmp_path):
    (tmp_path / "rules").mkdir()
    (tmp_path / "rules" / "rules.json").write_text(json.dumps([{"id": "alpha", "pattern": "ALPHA_MARKER", "weight": 7}]))
    return tmp_path


def test_run_scan_writes_results_and_returns_them(tmp_path):
    root = project(tmp_path)
    real = root / "data" / "real"
    real.mkdir(parents=True)
    rows = [Action(agent="codex", session_id="s", index=i, tool="Bash", kind="shell", text=t)
            for i, t in enumerate(["ls", "echo ALPHA_MARKER"])]
    (real / "actions.jsonl").write_text("".join(json.dumps(a.to_dict()) + "\n" for a in rows))
    res = run_scan(root, threshold=5)
    assert res["n_alerts"] == 1
    assert json.loads((root / "results" / "real_scan.json").read_text()) == res


def test_run_scan_without_ingest_explains_and_writes_nothing(tmp_path):
    root = project(tmp_path)
    with pytest.raises(FileNotFoundError, match="monitor ingest"):
        run_scan(root, threshold=5)
    assert not (root / "results").exists()


def test_run_eval_writes_split_and_scorers(tmp_path):
    root = project(tmp_path)
    result = run_eval(root, ROOT / "tests" / "fixtures" / "labelled_sample.jsonl", no_judge=True)
    assert result["split"] == "dev" and list(result["scorers"]) == ["rules"]
    assert json.loads((root / "results" / "eval.json").read_text()) == result
