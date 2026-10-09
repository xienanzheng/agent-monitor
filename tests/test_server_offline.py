import json

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from monitor.schema import Action  # noqa: E402
from monitor.server.app import create_app  # noqa: E402
from monitor.server.offline import ActionsCache, labelled_files  # noqa: E402
from monitor.server.settings import ServerSettings  # noqa: E402


def client(root):
    s = ServerSettings(root=root, logs_dir=root / "logs", token="t", home=root / "home", dist_dir=root / "dist")
    return TestClient(create_app(s), base_url="http://127.0.0.1:8765")


def write_actions(root, texts):
    real = root / "data" / "real"
    real.mkdir(parents=True, exist_ok=True)
    rows = [Action(agent="codex" if i % 2 else "claude_code", session_id="s", index=i, tool="Bash",
                   kind="shell" if i < 2 else "file_read", text=t) for i, t in enumerate(texts)]
    (real / "actions.jsonl").write_text("".join(json.dumps(a.to_dict()) + "\n" for a in rows))


def test_overview_and_alerts_missing_then_present(tmp_path):
    c = client(tmp_path)
    assert c.get("/api/overview").json() == {"missing": True}
    assert c.get("/api/alerts").json() == {"missing": True}
    (tmp_path / "data" / "real").mkdir(parents=True)
    (tmp_path / "data" / "real" / "stats.json").write_text(json.dumps({"by_agent": {"codex": 2}}))
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "real_scan.json").write_text(json.dumps({"n_alerts": 1, "top_alerts": []}))
    assert c.get("/api/overview").json() == {"by_agent": {"codex": 2}}
    assert c.get("/api/alerts").json()["n_alerts"] == 1


def test_actions_filters_and_pages(tmp_path):
    write_actions(tmp_path, ["ls", "echo ALPHA_MARKER", "cat README", "alpha_marker again"])
    c = client(tmp_path)
    assert c.get("/api/actions").json()["total"] == 4
    assert [r["text"] for r in c.get("/api/actions?q=Alpha_Marker").json()["rows"]] == \
        ["echo ALPHA_MARKER", "alpha_marker again"]
    assert {r["agent"] for r in c.get("/api/actions?agent=codex").json()["rows"]} == {"codex"}
    assert c.get("/api/actions?kind=file_read").json()["total"] == 2
    page2 = c.get("/api/actions?page=2&page_size=3").json()
    assert page2["total"] == 4 and [r["text"] for r in page2["rows"]] == ["alpha_marker again"]


def test_actions_cache_reloads_when_the_file_changes(tmp_path):
    write_actions(tmp_path, ["ls"])
    cache = ActionsCache(tmp_path / "data" / "real" / "actions.jsonl")
    assert len(cache.load()) == 1
    write_actions(tmp_path, ["ls", "pwd", "whoami"])
    assert len(cache.load()) == 3


def test_eval_layouts_are_normalised(tmp_path):
    (tmp_path / "results").mkdir()
    p = tmp_path / "results" / "eval.json"
    p.write_text(json.dumps({"rules": {"auc": 0.5}}))
    c = client(tmp_path)
    assert c.get("/api/eval").json() == {"split": "unknown", "scorers": {"rules": {"auc": 0.5}}, 'legacy':True}
    p.write_text(json.dumps({"split": "dev", "scorers": {"rules": {"auc": 0.75}}}))
    assert c.get("/api/eval").json() == {"split": "dev", "scorers": {"rules": {"auc": 0.75}}, 'legacy':True}


def test_unreadable_results_are_an_error_not_a_crash(tmp_path):
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "eval.json").write_text("{not json")
    (tmp_path / "results" / "real_scan.json").write_text("[1, 2]")
    c = client(tmp_path)
    assert "eval.json" in c.get("/api/eval").json()["error"]
    assert "not a JSON object" in c.get("/api/alerts").json()["error"]


def test_rules_and_features_with_an_invalid_rules_file(tmp_path):
    (tmp_path / "rules").mkdir()
    (tmp_path / "rules" / "rules.json").write_text(json.dumps(
        [{"id": "bad", "type": "action", "category": "nope", "match": {"pattern": "x"}, "score": 1}]))
    (tmp_path / "rules" / "features.json").write_text(json.dumps([{"tag": "alpha", "pattern": "ALPHA_MARKER"}]))
    body = client(tmp_path).get("/api/rules").json()
    assert "rule bad" in body["rules"]["error"] and body["features"][0]["tag"] == "alpha"
    (tmp_path / "rules" / "rules.json").write_text(json.dumps([{"id": "alpha", "pattern": "ALPHA_MARKER", "weight": 3}]))
    rules = client(tmp_path).get("/api/rules").json()["rules"]
    assert (rules[0]["type"], rules[0]["score"], rules[0]["category"]) == ("action", 3.0, "other")


def test_labelled_files_lists_only_allowed_paths(tmp_path):
    (tmp_path / "data" / "labelled").mkdir(parents=True)
    (tmp_path / "data" / "labelled" / "set.jsonl").write_text("")
    (tmp_path / "data" / "labelled" / "README.md").write_text("")
    assert labelled_files(tmp_path) == ["data/labelled/set.jsonl"]
    (tmp_path / "tests" / "fixtures").mkdir(parents=True)
    (tmp_path / "tests" / "fixtures" / "labelled_sample.jsonl").write_text("")
    assert client(tmp_path).get("/api/labelled-files").json() == \
        ["data/labelled/set.jsonl", "tests/fixtures/labelled_sample.jsonl"]
