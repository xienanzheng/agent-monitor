from monitor.events import HookEvent, normalize_event

FAKE = "sk_live_ABCDEFGHIJKLMNOPQRSTUV"


def test_claude_prompt_is_redacted():
    ev = normalize_event("claude", {"hook_event_name": "UserPromptSubmit", "session_id": "s1", "cwd": "/p",
                                    "permission_mode": "default", "prompt": f"use key {FAKE} to fix tests"})
    assert ev.agent == "claude_code" and ev.event == "prompt" and ev.session_id == "s1"
    assert FAKE not in ev.prompt and "[REDACTED:stripe_key]" in ev.prompt


def test_claude_pre_tool_bash_and_post_tool_output():
    pre = normalize_event("claude", {"hook_event_name": "PreToolUse", "session_id": "s1", "cwd": "/p",
                                     "tool_name": "Bash", "tool_input": {"command": "pytest -q"}, "tool_use_id": "t1"})
    assert (pre.event, pre.kind, pre.text, pre.tool_use_id) == ("pre_tool", "shell", "pytest -q", "t1")
    post = normalize_event("claude", {"hook_event_name": "PostToolUse", "session_id": "s1", "tool_name": "Read",
                                      "tool_input": {"file_path": "/p/a.txt"}, "tool_output": f"x {FAKE}"})
    assert post.event == "post_tool" and post.kind == "file_read" and post.path == "/p/a.txt"
    assert FAKE not in post.output and "[REDACTED:stripe_key]" in post.output


def test_codex_bash_apply_patch_mcp_and_object_response():
    base = {"session_id": "c1", "cwd": "/r", "permission_mode": "danger-full-access", "turn_id": "u1"}
    b = normalize_event("codex", {**base, "hook_event_name": "PreToolUse", "tool_name": "Bash",
                                  "tool_input": {"command": "ls -la"}})
    assert (b.agent, b.kind, b.text, b.permission_mode, b.turn_id) == ("codex", "shell", "ls -la", "danger-full-access", "u1")
    p = normalize_event("codex", {**base, "hook_event_name": "PreToolUse", "tool_name": "apply_patch",
                                  "tool_input": {"command": "*** Begin Patch\n*** Add File: notes.md\n+hi\n*** End Patch"}})
    assert p.kind == "file_write" and "notes.md" in p.text
    m = normalize_event("codex", {**base, "hook_event_name": "PreToolUse", "tool_name": "mcp__svc__call",
                                  "tool_input": {"q": 1}})
    assert m.kind == "mcp" and m.text.startswith("mcp__svc__call")
    o = normalize_event("codex", {**base, "hook_event_name": "PostToolUse", "tool_name": "Bash",
                                  "tool_input": {"command": "env"}, "tool_response": {"stdout": f"KEY={FAKE}"}})
    assert FAKE not in o.output and "stdout" in o.output


def test_unknown_event_or_agent_is_ignored():
    assert normalize_event("claude", {"hook_event_name": "Notification"}) is None
    assert normalize_event("cursor", {"hook_event_name": "PreToolUse"}) is None


def test_session_events_and_round_trip():
    ev = normalize_event("codex", {"hook_event_name": "SessionStart", "session_id": "c1", "source": "startup", "cwd": "/r"})
    assert ev.event == "session_start" and ev.source == "startup"
    assert HookEvent.from_dict(ev.to_dict()) == ev


def test_codex_apply_patch_raw_string_input():
    ev = normalize_event("codex", {"hook_event_name": "PreToolUse", "session_id": "c1", "tool_name": "apply_patch",
                                   "tool_input": "*** Begin Patch\n*** Add File: notes.md\n+hi\n*** End Patch"})
    assert ev.kind == "file_write" and "notes.md" in ev.text
