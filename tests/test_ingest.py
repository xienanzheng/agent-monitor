import json
from pathlib import Path

from monitor.ingest import ingest

FIX = Path(__file__).parent / "fixtures"


def test_ingest_writes_redacted_actions_and_returns_stats(tmp_path):
    secret_cc = tmp_path / "cc.jsonl"
    secret_cc.write_text(
        (FIX / "claude_code_sample.jsonl").read_text().replace("pytest -q", "echo sk_live_ABCDEFGHIJKLMNOPQRST")
    )
    out = tmp_path / "actions.jsonl"
    stats = ingest(claude_files=[secret_cc], codex_files=[FIX / "codex_sample.jsonl"], out_path=out)
    rows = [json.loads(line) for line in out.read_text().splitlines()]
    assert len(rows) == 7
    assert stats["by_agent"] == {"claude_code": 3, "codex": 4}
    assert stats["by_kind"]["shell"] == 3
    assert "sk_live_" not in out.read_text()
    assert stats["policy"]["never/danger-full-access"] == 4


def test_discover_includes_nested_subagent_transcripts(tmp_path):
    from monitor.ingest import discover

    proj = tmp_path / ".claude" / "projects" / "p1"
    (proj / "sess1" / "subagents").mkdir(parents=True)
    (proj / "sess1.jsonl").write_text("{}\n")
    (proj / "sess1" / "subagents" / "agent-x.jsonl").write_text("{}\n")
    codex = tmp_path / ".codex" / "sessions" / "2026" / "10" / "01"
    codex.mkdir(parents=True)
    (codex / "rollout-1.jsonl").write_text("{}\n")
    claude, cx = discover(home=tmp_path)
    assert set(claude) == {proj / "sess1.jsonl", proj / "sess1" / "subagents" / "agent-x.jsonl"}
    assert cx == [codex / "rollout-1.jsonl"]
