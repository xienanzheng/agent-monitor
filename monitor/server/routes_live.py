"""Live-data API: status, sessions, session timelines, incidents and the event feed (read-only)."""
from fastapi import APIRouter, HTTPException, Query

from monitor.server.logs import LogStore, latest_incidents, read_after, read_tail, session_actions, summarize_sessions
from monitor.server.respond import ok
from monitor.server.settings import ServerSettings
from monitor.server.status import build_status


def live_router(settings: ServerSettings, store: LogStore) -> APIRouter:
    r = APIRouter(prefix="/api")

    def source_dir(source: str):
        try:
            return settings.source_dir(source)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    def tail(source: str, name: str):
        t = store.tail(source_dir(source) / name)
        t.refresh()
        return t

    @r.get("/status")
    def status(source: str = "live"):
        return ok(build_status(settings, source, tail(source, "events.jsonl"), tail(source, "incidents.jsonl")))

    @r.get("/sessions")
    def sessions(source: str = "live"):
        return ok(summarize_sessions(tail(source, "events.jsonl").rows))

    @r.get("/analysis")
    def analysis(source: str = "live"):
        from monitor.server.analysis import build_analysis
        from monitor.config import load_config
        rows = tail(source, "events.jsonl").rows
        return ok(build_analysis(rows, source, load_config(settings.root / "monitor.toml").incident_at))

    @r.get("/sessions/{agent}/{session_id}/actions")
    def actions(agent: str, session_id: str, source: str = "live"):
        return ok(session_actions(tail(source, "events.jsonl").rows, agent, session_id))

    @r.get("/incidents")
    def incidents(source: str = "live", recent_hours: float | None = Query(default=None, gt=0)):
        return ok(latest_incidents(tail(source, "incidents.jsonl").rows, recent_hours))

    @r.get("/events")
    def events(source: str = "live", after: int | None = Query(default=None, ge=0),
               tail_n: int = Query(default=50, ge=1, le=500, alias="tail"),
               limit: int = Query(default=200, ge=1, le=1000),
               file_id: int | None = Query(default=None)):
        path = source_dir(source) / "events.jsonl"
        return ok(read_tail(path, tail_n) if after is None else read_after(path, after, limit, file_id))

    return r
