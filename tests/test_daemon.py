import asyncio
import json
import os
import socket
import tempfile
import time

import pytest

from monitor.config import Config
from monitor.daemon import (
    Daemon,
    build_core,
    clear_replay_outputs,
    drain_spool,
    prepare_socket_path,
    replay,
    shift_events_to_now,
)
from monitor.events import normalize_event
from monitor.live_hook import run_live_hook
from tests.test_core import FAKE, Fake, core

PRE = {"hook_event_name": "PreToolUse", "session_id": "s1", "cwd": "/p", "tool_name": "Bash",
       "tool_input": {"command": "ls"}}


def short_dir():
    return tempfile.mkdtemp(prefix="am", dir="/tmp")


def test_socket_path_too_long_is_rejected():
    with pytest.raises(ValueError, match="too long"):
        prepare_socket_path("/tmp/" + "x" * 120 + "/m.sock")


def test_stale_socket_file_is_replaced_but_live_daemon_is_refused():
    p = os.path.join(short_dir(), "m.sock")
    s = socket.socket(socket.AF_UNIX)
    s.bind(p)
    s.close()  # stale socket file, nobody listening
    assert prepare_socket_path(p) == p and not os.path.exists(p)
    live = socket.socket(socket.AF_UNIX)
    live.bind(p)
    live.listen(1)
    try:
        with pytest.raises(RuntimeError, match="already listening"):
            prepare_socket_path(p)
    finally:
        live.close()


def test_directory_permissions_are_private():
    d = os.path.join(short_dir(), "sub")
    prepare_socket_path(os.path.join(d, "m.sock"))
    assert os.stat(d).st_mode & 0o777 == 0o700


def test_spool_is_drained_and_truncated(tmp_path):
    c, _, _ = core(tmp_path)
    spool = tmp_path / "spool.jsonl"
    run_live_hook("claude", json.dumps(PRE), os.path.join(short_dir(), "none.sock"), spool, tmp_path / "e")
    spool.write_text(spool.read_text() + "garbage\n")
    assert drain_spool(c, spool) == 1
    assert not spool.exists() and c.stats["bad_lines"] == 1
    assert len((tmp_path / "events.jsonl").read_text().splitlines()) == 1


def test_interrupted_drain_leftover_and_current_spool_are_both_processed(tmp_path):
    c, _, _ = core(tmp_path)
    spool = tmp_path / "spool.jsonl"
    line = json.dumps(normalize_event("claude", PRE).to_dict()) + "\n"
    (tmp_path / "spool.jsonl.draining").write_text(line)
    spool.write_text(line)
    assert drain_spool(c, spool) == 2
    assert not spool.exists() and not (tmp_path / "spool.jsonl.draining").exists()
    assert len((tmp_path / "events.jsonl").read_text().splitlines()) == 2


def test_spool_with_invalid_utf8_is_drained_not_fatal(tmp_path):
    c, _, _ = core(tmp_path)
    spool = tmp_path / "spool.jsonl"
    spool.write_bytes(b"\xff\xfe not utf8\n" + (json.dumps(normalize_event("claude", PRE).to_dict()) + "\n").encode())
    assert drain_spool(c, spool) == 1 and c.stats["bad_lines"] == 1


def test_daemon_receives_hook_events_end_to_end(tmp_path):
    c, _, _ = core(tmp_path)
    sock = os.path.join(short_dir(), "m.sock")

    async def scenario():
        d = Daemon(c, sock, tmp_path / "spool.jsonl", queue_max=10)
        await d.start()
        loop = asyncio.get_running_loop()
        payload = json.dumps({**PRE, "tool_input": {"command": f"echo ALPHA_MARKER {FAKE}"}})
        await loop.run_in_executor(None, run_live_hook, "claude", payload, sock, tmp_path / "spool.jsonl", tmp_path / "e")
        for _ in range(100):
            if (tmp_path / "events.jsonl").exists():
                break
            await asyncio.sleep(0.05)
        await d.stop()

    asyncio.run(scenario())
    [row] = [json.loads(line) for line in (tmp_path / "events.jsonl").read_text().splitlines()]
    assert row["rule_hits"] == ["alpha"] and not os.path.exists(sock)
    written = (tmp_path / "events.jsonl").read_text()
    if (tmp_path / "incidents.jsonl").exists():
        written += (tmp_path / "incidents.jsonl").read_text()
    assert FAKE not in written


def test_queue_overflow_drops_oldest_as_judge_failed(tmp_path):
    c, _, _ = core(tmp_path)
    d = Daemon(c, os.path.join(short_dir(), "m.sock"), tmp_path / "spool.jsonl", queue_max=1)
    d.queue = asyncio.Queue()
    for _ in range(2):
        d._enqueue(c.ingest(normalize_event("claude", {**PRE, "tool_input": {"command": "echo ALPHA_MARKER"}})))
    assert d.queue.qsize() == 1 and c.stats["dropped"] == 1
    row = json.loads((tmp_path / "events.jsonl").read_text().splitlines()[0])
    assert row["settled_by"] == "dropped" and row["judge_failed"] is True


def test_clear_replay_outputs_removes_only_replay_files(tmp_path):
    for name in ("events.jsonl", "incidents.jsonl", "daemon_errors.log", "keep.txt"):
        (tmp_path / name).write_text("x\n")
    clear_replay_outputs(tmp_path)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["keep.txt"]
    clear_replay_outputs(tmp_path / "missing")  # no error when nothing is there


def test_shift_events_to_now_moves_the_newest_event_to_now(tmp_path):
    src = tmp_path / "rec.jsonl"
    src.write_text('{"event": "prompt", "ts": 100.0}\n{"event": "pre_tool", "ts": 160.0, "text": "ls"}\n')
    out = shift_events_to_now(src, tmp_path / "out" / "shifted.jsonl", now=1000.0)
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert [r["ts"] for r in rows] == [940.0, 1000.0] and rows[1]["text"] == "ls"


def test_replay_processes_a_recorded_file(tmp_path):
    c, _, _ = core(tmp_path)
    rec = tmp_path / "rec.jsonl"
    evs = [normalize_event("claude", {**PRE, "hook_event_name": "UserPromptSubmit", "prompt": "t"}),
           normalize_event("claude", {**PRE, "tool_input": {"command": "echo ALPHA_MARKER"}})]
    rec.write_text("".join(json.dumps(e.to_dict()) + "\n" for e in evs))
    stats = replay(c, rec)
    assert stats["events"] == 2 and stats["judged"] == 1


def test_a_crashing_event_is_counted_and_does_not_stop_replay(tmp_path):
    c, _, _ = core(tmp_path)
    real, calls = c.ingest, []

    def flaky(ev):
        calls.append(ev)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return real(ev)

    c.ingest = flaky
    rec = tmp_path / "rec.jsonl"
    ev = normalize_event("claude", PRE)
    rec.write_text((json.dumps(ev.to_dict()) + "\n") * 2)
    stats = replay(c, rec)
    assert stats["errors"] == 1 and len((tmp_path / "events.jsonl").read_text().splitlines()) == 1
    [err] = [json.loads(line) for line in (tmp_path / "daemon_errors.log").read_text().splitlines()]
    assert err["error"] == "RuntimeError"


def test_build_core_loads_rules_and_optional_features(tmp_path):
    (tmp_path / "rules").mkdir()
    (tmp_path / "rules" / "rules.json").write_text('[{"id": "x", "pattern": "ALPHA_MARKER", "weight": 3}]')
    c = build_core(Config(), tmp_path, notifier=lambda t, b: None)
    assert [r.id for r in c.rules] == ["x"] and c.features == []
    assert c.events_path == tmp_path / "logs" / "events.jsonl"
    out = build_core(Config(), tmp_path, notifier=lambda t, b: None, logs_dir=tmp_path / "out")
    assert out.events_path == tmp_path / "out" / "events.jsonl"
    assert out.errors_path == tmp_path / "out" / "daemon_errors.log"
    assert out.incidents.out_path == tmp_path / "out" / "incidents.jsonl"


class Slow(Fake):
    """A judge that takes 1 s and then gives a low score with high confidence."""

    def __call__(self, url, payload, timeout):
        time.sleep(1.0)
        return super().__call__(url, payload, timeout)


def test_startup_drain_queues_judging_instead_of_waiting(tmp_path):
    c, _, _ = core(tmp_path, triage=Slow(score=2))
    spool, dead = tmp_path / "spool.jsonl", os.path.join(short_dir(), "none.sock")
    for _ in range(2):
        payload = json.dumps({**PRE, "tool_input": {"command": "echo ALPHA_MARKER"}})
        run_live_hook("claude", payload, dead, spool, tmp_path / "e")

    async def scenario():
        d = Daemon(c, os.path.join(short_dir(), "m.sock"), spool, queue_max=10)
        t0 = time.perf_counter()
        await d.start()
        elapsed = time.perf_counter() - t0
        await d.stop(grace_s=5)
        return d, elapsed

    d, elapsed = asyncio.run(scenario())
    assert elapsed < 0.5 and d.drained == 2
    assert len((tmp_path / "events.jsonl").read_text().splitlines()) == 2


def test_second_daemon_is_refused_and_does_not_steal_the_socket(tmp_path):
    c, _, _ = core(tmp_path)
    sock = os.path.join(short_dir(), "m.sock")

    async def scenario():
        a = Daemon(c, sock, tmp_path / "spool.jsonl", queue_max=10)
        await a.start()
        try:
            b = Daemon(c, sock, tmp_path / "spool.jsonl", queue_max=10)
            try:
                with pytest.raises(RuntimeError, match="already running"):
                    await b.start()
            finally:
                await b.stop()  # as run_daemon's finally would
            assert os.path.exists(sock)
            probe = socket.socket(socket.AF_UNIX)
            try:
                probe.connect(sock)  # A still owns the socket and accepts connections
            finally:
                probe.close()
        finally:
            await a.stop()

    asyncio.run(scenario())


def test_non_socket_file_at_socket_path_is_never_deleted():
    p = os.path.join(short_dir(), "m.sock")
    with open(p, "w") as f:
        f.write("not a socket")
    with pytest.raises(RuntimeError, match="not a socket"):
        prepare_socket_path(p)
    assert os.path.exists(p)


def test_relative_socket_path_is_rejected():
    with pytest.raises(ValueError, match="absolute"):
        prepare_socket_path("m.sock")


def test_stop_after_overflow_returns_promptly(tmp_path):
    c, _, _ = core(tmp_path)

    async def scenario():
        d = Daemon(c, os.path.join(short_dir(), "m.sock"), tmp_path / "spool.jsonl", queue_max=1)
        await d.start()
        for _ in range(3):  # the worker can't run between these calls, so the queue overflows twice
            d._enqueue(c.ingest(normalize_event("claude", {**PRE, "tool_input": {"command": "echo ALPHA_MARKER"}})))
        t0 = time.perf_counter()
        await d.stop(grace_s=3)
        return time.perf_counter() - t0

    elapsed = asyncio.run(scenario())
    assert elapsed < 1.5 and c.stats["dropped"] == 2


async def _wait_for(path, tries=100):
    for _ in range(tries):
        if path.exists():
            return
        await asyncio.sleep(0.05)


def test_crashing_event_through_the_socket_is_logged_and_the_daemon_keeps_going(tmp_path):
    c, _, _ = core(tmp_path)
    real, calls = c.ingest, []

    def flaky(ev):
        calls.append(ev)
        if len(calls) == 1:
            raise RuntimeError("boom")
        return real(ev)

    c.ingest = flaky
    sock = os.path.join(short_dir(), "m.sock")

    async def scenario():
        d = Daemon(c, sock, tmp_path / "spool.jsonl", queue_max=10)
        await d.start()
        loop = asyncio.get_running_loop()
        payload = json.dumps({**PRE, "tool_input": {"command": "echo ALPHA_MARKER"}})
        for _ in range(2):
            await loop.run_in_executor(None, run_live_hook, "claude", payload, sock, tmp_path / "spool.jsonl",
                                       tmp_path / "e")
        await _wait_for(tmp_path / "events.jsonl")
        await d.stop()

    asyncio.run(scenario())
    assert c.stats["errors"] == 1 and not (tmp_path / "spool.jsonl").exists()
    assert len((tmp_path / "daemon_errors.log").read_text().splitlines()) == 1
    assert len((tmp_path / "events.jsonl").read_text().splitlines()) == 1


def test_enqueue_failure_on_a_connection_is_logged_and_later_lines_still_count(tmp_path):
    c, _, _ = core(tmp_path)
    sock = os.path.join(short_dir(), "m.sock")
    line = (json.dumps(normalize_event("claude", {**PRE, "tool_input": {"command": "echo ALPHA_MARKER"}}).to_dict())
            + "\n").encode()

    async def scenario():
        d = Daemon(c, sock, tmp_path / "spool.jsonl", queue_max=10)
        await d.start()
        real, calls = d._enqueue, []

        def flaky(p):
            calls.append(p)
            if len(calls) == 1:
                raise RuntimeError("queue trouble")
            real(p)

        d._enqueue = flaky
        reader, writer = await asyncio.open_unix_connection(sock)
        writer.write(line * 2)  # two events on one connection: the first fails to enqueue
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        await _wait_for(tmp_path / "events.jsonl")
        await d.stop()

    asyncio.run(scenario())
    assert c.stats["errors"] == 1 and len((tmp_path / "daemon_errors.log").read_text().splitlines()) == 1
    assert len((tmp_path / "events.jsonl").read_text().splitlines()) == 1
