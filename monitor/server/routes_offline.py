"""Offline-analysis API (read-only)."""
from fastapi import APIRouter, Query

from monitor.server.offline import ActionsCache, browse, eval_results, labelled_files, read_json, rules_view
from monitor.server.respond import ok
from monitor.server.settings import ServerSettings


def offline_router(settings: ServerSettings) -> APIRouter:
    r = APIRouter(prefix="/api")
    root = settings.root
    actions_cache = ActionsCache(root / "data" / "real" / "actions.jsonl")

    @r.get("/overview")
    def overview():
        return ok(read_json(root / "data" / "real" / "stats.json"))

    @r.get("/actions")
    def actions(agent: str = "", kind: str = "", q: str = "", page: int = Query(default=1, ge=1),
                page_size: int = Query(default=50, ge=1, le=200)):
        return ok(browse(actions_cache.load(), agent, kind, q, page, page_size))

    @r.get("/alerts")
    def alerts():
        return ok(read_json(root / "results" / "real_scan.json"))

    @r.get("/eval")
    def evaluation():
        return ok(eval_results(root))

    @r.get("/rules")
    def rules():
        return ok(rules_view(root))

    @r.get("/labelled-files")
    def labelled():
        return ok(labelled_files(root))

    return r
