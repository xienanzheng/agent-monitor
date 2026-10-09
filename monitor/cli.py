import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RES = ROOT / "results"


def hook_command(root: Path) -> str:
    """Hook command: the project venv's python in isolated mode (-I ignores PYTHON* env vars and cwd)."""
    return f'"{root / ".venv" / "bin" / "python"}" -I -m monitor.hook'


def install_live_hook(root: Path, settings: Path) -> Path:
    py = root / ".venv" / "bin" / "python"
    if not py.exists():
        raise SystemExit(f"error: {py} not found; run `uv sync` first. {settings} was not changed.")
    from monitor.hook import install_hook
    return install_hook(settings, hook_command(root))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="monitor")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ingest")
    e = sub.add_parser("eval")
    e.add_argument("--labelled", required=True)
    e.add_argument("--judge-model", default="qwen3:8b")
    e.add_argument("--no-judge", action="store_true")
    e.add_argument("--final", action="store_true", help="score the held-out test split (default: dev split only)")
    e.add_argument("--out", default=str(RES / "eval.json"))
    s = sub.add_parser("scan-real")
    s.add_argument("--threshold", type=float, required=True)
    s.add_argument("--judge-sample", type=int, default=0)
    s.add_argument("--judge-model", default="qwen3:8b")
    r = sub.add_parser("report")
    r.add_argument("--eval", default=str(RES / "eval.json"), help="eval results file (skipped if missing)")
    sub.add_parser("install-hook")
    u = sub.add_parser("uninstall-hook")
    u.add_argument("--backup", required=True)
    sub.add_parser("daemon", help="run the live monitor daemon in the foreground (Ctrl-C to stop)")
    doctor = sub.add_parser("doctor", help="read-only diagnostics for monitoring, agent hooks and local models")
    doctor.add_argument("--json", action="store_true", help="print structured status")
    rp = sub.add_parser("replay", help="feed a JSONL of recorded hook events through the pipeline "
                                       "(calls the local Ollama judges; never writes to the live logs)")
    rp.add_argument("file")
    rp.add_argument("--out-dir", default=str(ROOT / "logs" / "replay"),
                    help="where events.jsonl, incidents.jsonl and daemon_errors.log go (default: logs/replay)")
    rp.add_argument("--fresh", action="store_true", help="clear the previous replay output in --out-dir first")
    rp.add_argument("--now", action="store_true", help="shift event times so the newest is now (for demos)")
    ih = sub.add_parser("install-hooks", help="install the v2 live hooks for Claude Code and/or Codex")
    ih.add_argument("--agent", choices=["claude", "codex", "both"], default="both")
    uh = sub.add_parser("uninstall-hooks")
    uh.add_argument("--agent", choices=["claude", "codex"], required=True)
    uh.add_argument("--backup", required=True)
    sv = sub.add_parser("serve", help="start the local dashboard on 127.0.0.1 "
                                      "(needs `uv sync --extra dashboard` and a built dashboard/)")
    sv.add_argument("--port", type=int, default=8765)
    sv.add_argument("--logs-dir", default=str(ROOT / "logs"), help="live logs (replay is <logs-dir>/replay)")
    sv.add_argument("--open", action="store_true", help="open the dashboard in the browser")
    sv.add_argument("--home", default=None, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    RES.mkdir(exist_ok=True)
    settings = Path.home() / ".claude" / "settings.json"

    if a.cmd == "doctor":
        from monitor.server.serve import build_settings
        from monitor.server.logs import JsonlTail
        from monitor.server.status import build_status
        s = build_settings(ROOT, 8765, ROOT / "logs", "doctor")
        events, incidents = JsonlTail(s.logs_dir / "events.jsonl"), JsonlTail(s.logs_dir / "incidents.jsonl")
        events.refresh(); incidents.refresh()
        status = build_status(s, "live", events, incidents)
        if a.json:
            print(json.dumps(status, indent=2))
        else:
            print("Daemon:", "responsive" if status["daemon"].get("responsive") else "not responsive")
            for agent, health in status["health"]["agents"].items():
                print(f"{agent}: configured={health['configured']}, executable={health['executable_ok']}, observed={health['observed']}")
            print("Missing models:", ", ".join(status["health"]["ollama"]["missing"]) or "none")
            print("Spool backlog:", status["spool_backlog"], "Daemon errors:", status["daemon_errors"])
    elif a.cmd == "ingest":
        from monitor.ingest import discover, ingest
        stats = ingest(*discover(), ROOT / "data" / "real" / "actions.jsonl")
        (ROOT / "data" / "real" / "stats.json").write_text(json.dumps(stats, indent=1))
        print(json.dumps(stats["by_agent"]))
    elif a.cmd == "eval":
        from monitor.runs import run_eval
        result = run_eval(ROOT, a.labelled, no_judge=a.no_judge, judge_model=a.judge_model, final=a.final, out=a.out)
        res = result["scorers"]
        print(json.dumps({"split": result["split"], **{k: v["auc"] for k, v in res.items()}}))
        for name, row in res.items():
            if row.get("judge_failures"):
                print(f"WARNING: {name}: {row['judge_failures']} of {row['judge_calls']} judge calls failed")
    elif a.cmd == "scan-real":
        from monitor.runs import run_scan
        try:
            res = run_scan(ROOT, a.threshold, a.judge_sample, a.judge_model)
        except FileNotFoundError as e:
            raise SystemExit(f"error: {e}")
        print(res["n_alerts"], "alerts;", res["alerts_per_1000"], "per 1,000")
        if a.judge_sample > 0:
            js = res["judge_sample"]
            print("judge sample:", js["n_alerts"], "alerts in", js["n_scored"], "scored")
            if js["judge_failures"]:
                print(f"WARNING: {js['judge_failures']} of {js['judge_calls']} judge calls failed "
                      f"(is Ollama running with {a.judge_model}?)")
    elif a.cmd == "report":
        from monitor.report import render_files
        md = render_files(a.eval, RES / "real_scan.json")
        if md is None:
            sys.exit("nothing to report: run `monitor eval` and/or `monitor scan-real` first")
        (RES / "report.md").write_text(md)
        print(RES / "report.md")
    elif a.cmd == "install-hook":
        b = install_live_hook(ROOT, settings)
        print(f"installed; backup at {b}")
        print("restart any open Claude Code sessions for the hook to take effect")
    elif a.cmd == "uninstall-hook":
        from monitor.hook import uninstall_hook
        saved = uninstall_hook(settings, a.backup)
        if saved is None:
            print("restored", settings)
        else:
            print(f"{settings} changed since install: removed only the monitor hook; previous file saved at {saved}")
    elif a.cmd == "daemon":
        import asyncio
        from monitor.config import load_config
        from monitor.daemon import build_core, run_daemon
        try:  # bad monitor.toml / rules.json / features.json: refuse to start, naming the rule or tag
            cfg = load_config()
            core = build_core(cfg, ROOT)
        except (ValueError, OSError) as e:
            raise SystemExit(f"error: {e}")
        try:
            asyncio.run(run_daemon(core, cfg.socket_path, ROOT / "logs" / "spool.jsonl", cfg.queue_max))
        except KeyboardInterrupt:
            pass
        except (RuntimeError, ValueError, OSError) as e:  # daemon already running, bad socket path, bind failed
            raise SystemExit(f"error: {e}")
        print("stopped;", json.dumps(core.stats))
    elif a.cmd == "replay":
        from monitor.config import load_config
        from monitor.daemon import build_core, replay
        out_dir = Path(a.out_dir)
        if a.fresh:
            from monitor.daemon import clear_replay_outputs
            clear_replay_outputs(out_dir)
        src = Path(a.file)
        if a.now:
            from monitor.daemon import shift_events_to_now
            src = shift_events_to_now(src, out_dir / ".replay-input.jsonl")
        core = build_core(load_config(), ROOT, notifier=lambda title, body: None, logs_dir=out_dir)
        print(json.dumps(replay(core, src)))
        print(f"replay output in {out_dir} (events.jsonl, incidents.jsonl, daemon_errors.log if any errors)")
    elif a.cmd == "install-hooks":
        from monitor.install import install_live_hooks
        try:
            installed = install_live_hooks(ROOT, a.agent)
        except RuntimeError as e:
            raise SystemExit(f"error: {e}")
        for agent, path, backup in installed:
            print(f"{agent}: installed in {path}; backup at {backup}")
            print("  approve the new hooks in Codex with /hooks" if agent == "codex"
                  else "  restart any open Claude Code sessions")
        print("start the daemon with `uv run monitor daemon` (events are spooled until it runs)")
    elif a.cmd == "uninstall-hooks":
        from monitor.install import settings_path_for, uninstall_hooks
        path = settings_path_for(a.agent)
        saved = uninstall_hooks(path, a.backup)
        print(f"restored {path}" if saved is None else
              f"{path} changed since install: removed only the monitor hooks; previous file saved at {saved}")
    elif a.cmd == "serve":
        from monitor.server.serve import serve
        serve(ROOT, a.port, Path(a.logs_dir), open_browser=a.open, home=a.home)


if __name__ == "__main__":
    sys.exit(main())
