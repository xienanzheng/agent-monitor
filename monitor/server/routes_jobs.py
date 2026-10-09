"""Run endpoints (token-guarded) and job status."""
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from monitor.server.jobs import JobRunner
from monitor.server.offline import labelled_files
from monitor.server.respond import ok
from monitor.server.settings import ServerSettings


class ScanRequest(BaseModel):
    threshold: float = Field(ge=0, le=10)
    judge_sample: int = Field(default=0, ge=0, le=500)


class EvalRequest(BaseModel):
    labelled: str
    no_judge: bool = True


def scan_summary(res: dict) -> dict:
    out = {k: res.get(k) for k in ("n_actions", "n_alerts", "alerts_per_1000")}
    if isinstance(res.get("judge_sample"), dict):
        out["judge_sample_alerts"] = res["judge_sample"].get("n_alerts")
    return out


def eval_summary(res: dict) -> dict:
    return {"split": res["split"], "auc": {name: row.get("auc") for name, row in res["scorers"].items()}}


def jobs_router(settings: ServerSettings, runner: JobRunner, guard, scan_fn, eval_fn) -> APIRouter:
    r = APIRouter(prefix="/api")

    def respond(job, started: bool):
        if started:
            return ok({"job": asdict(job)})
        return ok({"error": "a job is already running", "job": asdict(job)}, status_code=409)

    @r.post("/run/scan", dependencies=[Depends(guard)])
    def run_scan(body: ScanRequest):
        return respond(*runner.start(
            "scan", lambda: scan_summary(scan_fn(settings.root, body.threshold, body.judge_sample))))

    @r.post("/run/eval", dependencies=[Depends(guard)])
    def run_eval(body: EvalRequest):
        if body.labelled not in labelled_files(settings.root):
            raise HTTPException(status_code=400, detail="labelled must be one of /api/labelled-files")
        path = settings.root / body.labelled
        return respond(*runner.start(
            "eval", lambda: eval_summary(eval_fn(settings.root, path, no_judge=body.no_judge))))

    @r.get("/jobs/current")
    def current():
        return ok(asdict(runner.current) if runner.current else None)

    @r.get("/jobs/{job_id}")
    def job(job_id: str):
        found = runner.get(job_id)
        if found is None:
            raise HTTPException(status_code=404, detail="no such job")
        return ok(asdict(found))

    return r
