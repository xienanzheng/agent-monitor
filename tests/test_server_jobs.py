import json
import threading
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from monitor.schema import Action  # noqa: E402
from monitor.server.app import create_app  # noqa: E402
from monitor.server.jobs import JobRunner  # noqa: E402
from monitor.server.settings import ServerSettings  # noqa: E402

TOKEN = "t0k"
H = {"X-Monitor-Token": TOKEN}
FAKE = "sk_live_ABCDEFGHIJKLMNOPQRSTUV"
ROOT = Path(__file__).resolve().parent.parent


def project(tmp_path, actions=True):
    (tmp_path / "rules").mkdir()
    (tmp_path / "rules" / "rules.json").write_text(json.dumps([{"id": "alpha", "pattern": "ALPHA_MARKER", "weight": 7}]))
    if actions:
        real = tmp_path / "data" / "real"
        real.mkdir(parents=True)
        rows = [Action(agent="codex", session_id="s", index=i, tool="Bash", kind="shell", text=t)
                for i, t in enumerate(["ls", "echo ALPHA_MARKER"])]
        (real / "actions.jsonl").write_text("".join(json.dumps(a.to_dict()) + "\n" for a in rows))
    (tmp_path / "tests" / "fixtures").mkdir(parents=True)
    (tmp_path / "tests" / "fixtures" / "labelled_sample.jsonl").write_text(
        (ROOT / "tests" / "fixtures" / "labelled_sample.jsonl").read_text())
    return tmp_path


def make(root, **kw):
    s = ServerSettings(root=root, logs_dir=root / "logs", token=TOKEN, home=root / "home", dist_dir=root / "dist")
    app = create_app(s, **kw)
    return app, TestClient(app, base_url="http://127.0.0.1:8765")


def test_job_runner_done_and_failed():
    runner = JobRunner()
    good, started = runner.start("scan", lambda: {"n": 1})
    runner.wait(good.id, 5)
    assert started and good.status == "done" and good.summary == {"n": 1} and good.finished is not None

    def boom():
        raise RuntimeError(f"key {FAKE} rejected")

    bad, _ = runner.start("scan", boom)
    runner.wait(bad.id, 5)
    assert bad.status == "failed" and "RuntimeError" in bad.error and FAKE not in bad.error


def test_job_runner_refuses_a_second_job_while_one_runs():
    runner, gate = JobRunner(), threading.Event()
    first, _ = runner.start("scan", lambda: gate.wait(5) and {})
    second, started = runner.start("eval", lambda: {})
    assert not started and second is first
    gate.set()
    runner.wait(first.id, 5)
    third, started = runner.start("eval", lambda: {})
    runner.wait(third.id, 5)
    assert started and third.status == "done"


def test_run_scan_needs_the_token(tmp_path):
    _, c = make(project(tmp_path))
    assert c.post("/api/run/scan", json={"threshold": 5}).status_code == 403
    assert c.post("/api/run/scan", json={"threshold": 5}, headers={"X-Monitor-Token": "nope"}).status_code == 403


def test_run_scan_job_writes_results_and_reports_a_summary(tmp_path):
    app, c = make(project(tmp_path))
    job = c.post("/api/run/scan", json={"threshold": 5}, headers=H).json()["job"]
    app.state.jobs.wait(job["id"], 10)
    done = c.get(f"/api/jobs/{job['id']}").json()
    assert done["status"] == "done" and done["summary"]["n_alerts"] == 1
    assert json.loads((tmp_path / "results" / "real_scan.json").read_text())["n_alerts"] == 1


def test_failed_scan_keeps_old_results(tmp_path):
    root = project(tmp_path, actions=False)
    (root / "results").mkdir()
    (root / "results" / "real_scan.json").write_text('{"old": true}')
    app, c = make(root)
    job = c.post("/api/run/scan", json={"threshold": 5}, headers=H).json()["job"]
    app.state.jobs.wait(job["id"], 10)
    done = c.get(f"/api/jobs/{job['id']}").json()
    assert done["status"] == "failed" and "monitor ingest" in done["error"]
    assert (root / "results" / "real_scan.json").read_text() == '{"old": true}'


def test_run_eval_only_accepts_allowed_labelled_files(tmp_path):
    app, c = make(project(tmp_path))
    assert c.post("/api/run/eval", json={"labelled": "../secret.jsonl"}, headers=H).status_code == 400
    job = c.post("/api/run/eval", json={"labelled": "tests/fixtures/labelled_sample.jsonl"}, headers=H).json()["job"]
    app.state.jobs.wait(job["id"], 10)
    done = c.get(f"/api/jobs/{job['id']}").json()
    assert done["status"] == "done" and done["summary"]["split"] == "dev" and "rules" in done["summary"]["auc"]


def test_second_post_while_running_is_409(tmp_path):
    gate = threading.Event()
    app, c = make(project(tmp_path), scan_fn=lambda root, threshold, judge_sample: gate.wait(5) and {"n_alerts": 0})
    first = c.post("/api/run/scan", json={"threshold": 5}, headers=H)
    second = c.post("/api/run/scan", json={"threshold": 5}, headers=H)
    assert first.status_code == 200 and second.status_code == 409
    assert second.json()["job"]["id"] == first.json()["job"]["id"]
    gate.set()
    app.state.jobs.wait(first.json()["job"]["id"], 5)


def test_jobs_current_and_unknown_id(tmp_path):
    _, c = make(project(tmp_path))
    assert c.get("/api/jobs/current").json() is None
    assert c.get("/api/jobs/nope").status_code == 404
