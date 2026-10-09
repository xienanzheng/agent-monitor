from pathlib import Path

from monitor.adapters.claude_code import load_claude_code
from monitor.adapters.codex import load_codex

FIX = Path(__file__).parent / "fixtures"


def test_claude_code_extracts_tool_calls_in_order_with_task():
    actions = load_claude_code(FIX / "claude_code_sample.jsonl")
    assert [a.tool for a in actions] == ["Bash", "Edit", "mcp__canvas-mcp__list_courses"]
    assert [a.kind for a in actions] == ["shell", "file_write", "mcp"]
    assert actions[0].text == "pytest -q"
    assert actions[0].task == "please fix the failing test"
    assert actions[0].output == "1 failed"
    assert actions[0].agent == "claude_code" and actions[0].session_id == "s1"
    assert "/proj/app.py" in actions[1].text


def test_codex_extracts_calls_policy_and_nested_exec_commands():
    actions = load_codex(FIX / "codex_sample.jsonl")
    assert [a.kind for a in actions] == ["shell", "file_write", "code_exec", "shell"]
    assert actions[0].text == "ls -la"
    assert actions[0].output == "total 0"
    assert actions[0].task == "list the files"
    assert actions[0].policy == {"approval": "never", "sandbox": "danger-full-access"}
    assert "notes.md" in actions[1].text
    assert "cat ~/.ssh/id_rsa" in actions[2].text  # command nested inside JS exec is surfaced
    assert actions[3].text == "git status"


def _write_jsonl(path, recs):
    import json

    path.write_text("\n".join(json.dumps(r) for r in recs) + "\n")
    return path


def _fake_pem(n):
    return "-----BEGIN RSA PRIVATE KEY-----\n" + "A" * n + "\n-----END RSA PRIVATE KEY-----"


def _leaks_key_material(actions) -> bool:
    import json
    import re

    return bool(re.search(r"A{10,}", json.dumps([a.to_dict() for a in actions])))


def test_claude_code_redacts_long_secrets_before_clipping(tmp_path):
    p = _write_jsonl(tmp_path / "cc.jsonl", [
        {"type": "user", "sessionId": "s1", "message": {"role": "user", "content": "show the key file"}},
        {"type": "assistant", "sessionId": "s1", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "cat key.pem"}},
            {"type": "tool_use", "id": "t2", "name": "Write",
             "input": {"file_path": "/p/key.pem", "content": _fake_pem(5000)}}]}},
        {"type": "user", "sessionId": "s1", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": _fake_pem(1750)}]}},
    ])
    actions = load_claude_code(p)
    assert [a.tool for a in actions] == ["Bash", "Write"]
    assert actions[0].output and not _leaks_key_material(actions)


def test_codex_redacts_long_secrets_before_clipping(tmp_path):
    p = _write_jsonl(tmp_path / "cx.jsonl", [
        {"type": "session_meta", "payload": {"id": "c1", "cwd": "/repo"}},
        {"type": "response_item", "payload": {"type": "function_call", "name": "exec_command",
                                              "arguments": '{"cmd": "cat key.pem"}', "call_id": "k1"}},
        {"type": "response_item", "payload": {"type": "function_call_output", "call_id": "k1",
                                              "output": _fake_pem(1750)}},
    ])
    actions = load_codex(p)
    assert len(actions) == 1 and actions[0].output and not _leaks_key_material(actions)


def test_claude_code_ignores_injected_meta_user_text_as_task(tmp_path):
    p = _write_jsonl(tmp_path / "cc.jsonl", [
        {"type": "user", "sessionId": "s1", "message": {"role": "user", "content": "please fix the failing test"}},
        {"type": "user", "sessionId": "s1", "message": {"role": "user",
                                                       "content": "<command-name>/clear</command-name>"}},
        {"type": "user", "sessionId": "s1", "message": {"role": "user", "content": [
            {"type": "text", "text": "<system-reminder>placeholder</system-reminder>"}]}},
        {"type": "user", "sessionId": "s1", "isMeta": True,
         "message": {"role": "user", "content": "Caveat: placeholder meta text"}},
        {"type": "assistant", "sessionId": "s1", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "pytest -q"}}]}},
        {"type": "user", "sessionId": "s1", "message": {"role": "user", "content": [
            {"type": "text", "text": "<system-reminder>placeholder</system-reminder>"},
            {"type": "text", "text": "now run the linter"}]}},
        {"type": "assistant", "sessionId": "s1", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t2", "name": "Bash", "input": {"command": "ruff check"}}]}},
    ])
    actions = load_claude_code(p)
    assert [a.task for a in actions] == ["please fix the failing test", "now run the linter"]
