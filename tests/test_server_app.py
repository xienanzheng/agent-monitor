import math

import pytest

pytest.importorskip("fastapi")

from fastapi import Depends, FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from monitor.server.app import create_app, token_guard  # noqa: E402
from monitor.server.respond import redact_obj  # noqa: E402
from monitor.server.settings import ServerSettings  # noqa: E402

TOKEN = "t0k-test"
FAKE = "sk_live_ABCDEFGHIJKLMNOPQRSTUV"


def settings(tmp_path, **kw):
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True, exist_ok=True)
    (dist / "index.html").write_text('<meta name="monitor-token" content="__MONITOR_TOKEN__"><div id="root"></div>')
    (dist / "assets" / "app.js").write_text("console.log(1)")
    return ServerSettings(root=tmp_path, logs_dir=tmp_path / "logs", token=TOKEN, home=tmp_path / "home",
                          dist_dir=dist, **kw)


def client(s, base=None):
    return TestClient(create_app(s), base_url=base or f"http://127.0.0.1:{s.port}")


def test_index_has_token_injected_on_every_page_path(tmp_path):
    c = client(settings(tmp_path))
    for path in ("/", "/live", "/sessions/claude_code/abc"):
        r = c.get(path)
        assert r.status_code == 200 and TOKEN in r.text and "__MONITOR_TOKEN__" not in r.text


def test_built_assets_are_served(tmp_path):
    assert client(settings(tmp_path)).get("/assets/app.js").text == "console.log(1)"


def test_wrong_host_is_refused_and_localhost_is_allowed(tmp_path):
    s = settings(tmp_path)
    for base in ("http://evil.example:8765", "http://127.0.0.1:9999", "http://testserver"):
        assert client(s, base).get("/").status_code == 403
    assert client(s, "http://localhost:8765").get("/").status_code == 200


def test_unknown_api_path_is_404_not_the_page(tmp_path):
    assert client(settings(tmp_path)).get("/api/nope").status_code == 404


def test_files_outside_dist_are_never_served(tmp_path):
    (tmp_path / "secret.txt").write_text("top secret")
    r = client(settings(tmp_path)).get("/%2e%2e/secret.txt")
    assert "top secret" not in r.text


def test_index_html_by_name_also_gets_the_token(tmp_path):
    r = client(settings(tmp_path)).get("/index.html")
    assert r.status_code == 200 and TOKEN in r.text and "__MONITOR_TOKEN__" not in r.text


def test_pages_and_api_refuse_to_be_framed(tmp_path):
    c = client(settings(tmp_path))
    for path in ("/", "/api/nope"):
        r = c.get(path)
        assert r.headers["x-frame-options"] == "DENY"
        assert r.headers["content-security-policy"] == "frame-ancestors 'none'"


def test_missing_build_returns_503_with_the_build_command(tmp_path):
    s = settings(tmp_path)
    (s.dist() / "index.html").unlink()
    r = client(s).get("/live")
    assert r.status_code == 503 and "npm --prefix dashboard run build" in r.text


def test_token_guard_needs_the_exact_token():
    app = FastAPI()

    @app.post("/x", dependencies=[Depends(token_guard(TOKEN))])
    def x():
        return {"ok": True}

    c = TestClient(app)
    assert c.post("/x").status_code == 403
    assert c.post("/x", headers={"X-Monitor-Token": "wrong"}).status_code == 403
    assert c.post("/x", headers={"X-Monitor-Token": TOKEN}).status_code == 200


def test_redact_obj_walks_nested_values():
    out = redact_obj({"a": [FAKE, {"b": f"x {FAKE}"}], "t": (FAKE,), "n": 3, "none": None, "nan": math.nan})
    assert FAKE not in str(out) and out["n"] == 3 and out["none"] is None and out["nan"] is None


def test_empty_token_is_refused(tmp_path):
    with pytest.raises(ValueError, match="token"):
        create_app(ServerSettings(root=tmp_path, logs_dir=tmp_path, token=""))
