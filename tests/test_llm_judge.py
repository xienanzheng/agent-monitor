from monitor.llm_judge import Judge, parse_judge_reply
from monitor.schema import Action


def act(text):
    return Action(agent="t", session_id="s", index=0, tool="Bash", kind="shell", text=text, task="run the tests")


def test_parse_plain_json():
    assert parse_judge_reply('{"score": 7, "reason": "off-task"}') == (7.0, "off-task")


def test_parse_handles_prose_around_json_and_clamps():
    assert parse_judge_reply('Sure. {"score": 14, "reason": "x"} done') == (10.0, "x")


def test_parse_unparseable_returns_none():
    score, reason = parse_judge_reply("no json here")
    assert score is None and "unparseable" in reason


def test_parse_handles_braces_inside_reason():
    assert parse_judge_reply('{"score": 3, "reason": "echoes {path} from the task"}') == (3.0, "echoes {path} from the task")


def test_judge_sends_task_context_and_action_and_parses_reply():
    seen = {}

    def fake(url, payload, timeout):
        seen["url"], seen["payload"] = url, payload
        return {"done": True, "done_reason": "stop", "message": {"content": '{"score": 3, "reason": "consistent with task"}'}}

    j = Judge(model="qwen3:4b", transport=fake)
    r = j.score(act("pytest -q"), context=[act("ls")])
    assert r.score == 3.0 and r.reason == "consistent with task"
    prompt = seen["payload"]["messages"][-1]["content"]
    assert "run the tests" in prompt and "pytest -q" in prompt and "ls" in prompt
    assert seen["url"].endswith("/api/chat") and seen["payload"]["model"] == "qwen3:4b"
    assert seen["payload"]["options"]["temperature"] == 0


def test_judge_returns_none_when_transport_fails():
    def boom(url, payload, timeout):
        raise TimeoutError("ollama down")

    r = Judge(transport=boom).score(act("ls"), context=[])
    assert r.score is None and "ollama down" in r.reason


def test_parse_rejects_non_finite_and_bool_scores():
    assert parse_judge_reply('{"score": NaN, "reason": "x"}')[0] is None
    assert parse_judge_reply('{"score": Infinity, "reason": "x"}')[0] is None
    assert parse_judge_reply('{"score": true, "reason": "x"}')[0] is None
    assert parse_judge_reply('{"score": true} then {"score": 4, "reason": "y"}') == (4.0, "y")


def test_http_transport_bypasses_environment_proxies(monkeypatch):
    import urllib.request

    from monitor import llm_judge

    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    is_proxy = lambda h: isinstance(h, urllib.request.ProxyHandler)  # noqa: E731
    assert any(map(is_proxy, urllib.request.build_opener().handlers))  # the default opener would use it
    assert not any(map(is_proxy, llm_judge._OPENER.handlers))  # the judge's opener connects directly
