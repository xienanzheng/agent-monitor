import json
from pathlib import Path

import pytest

from monitor.features import CONTEXT_TAGS, Feature, extract_tags, load_features
from monitor.schema import Action

ROOT = Path(__file__).resolve().parent.parent


def act(text="ls", kind="shell", output="", cwd="/proj", policy=None):
    return Action(agent="t", session_id="s", index=0, tool="Bash", kind=kind, text=text, output=output,
                  cwd=cwd, policy=policy or {})


def test_builtin_secret_markers():
    assert "secret_marker" in extract_tags(act("echo [REDACTED:stripe_key]"), [])
    assert "secret_in_output" in extract_tags(act(output="token [REDACTED:github_token]"), [])
    assert extract_tags(act("ls"), []) == set()


def test_builtin_outside_workspace_uses_explicit_path_only():
    assert "outside_workspace" in extract_tags(act(kind="file_write"), [], path="/etc/hosts")
    assert "outside_workspace" not in extract_tags(act(kind="file_write"), [], path="/proj/src/a.py")
    assert "outside_workspace" not in extract_tags(act(kind="file_write"), [], path="src/a.py")
    assert "outside_workspace" not in extract_tags(act(kind="file_write", cwd=None), [], path="/etc/hosts")


def test_builtin_mode_and_kind_tags():
    assert "full_access_mode" in extract_tags(act(), [], permission_mode="bypassPermissions")
    assert "full_access_mode" in extract_tags(act(policy={"sandbox": "danger-full-access"}), [])
    assert "network_tool" in extract_tags(act(kind="browser"), [])
    assert "new_subagent" in extract_tags(act(kind="agent"), [])
    assert CONTEXT_TAGS == {"full_access_mode", "outside_workspace"}


def test_user_vocabulary_matches_fields_and_kinds():
    feats = [Feature(tag="alpha", pattern="ALPHA_MARKER", kinds=("shell",), fields=("text",)),
             Feature(tag="beta_out", pattern="BETA_MARKER", fields=("output",)),
             Feature(tag="gamma_path", pattern=r"\.gamma$", fields=("path",))]
    assert "alpha" in extract_tags(act("echo ALPHA_MARKER"), feats)
    assert "alpha" not in extract_tags(act("echo ALPHA_MARKER", kind="file_read"), feats)
    assert "beta_out" in extract_tags(act(output="BETA_MARKER"), feats)
    assert "beta_out" not in extract_tags(act("BETA_MARKER"), feats)
    assert "gamma_path" in extract_tags(act(kind="file_read"), feats, path="/proj/x.gamma")


def test_load_features_validates(tmp_path):
    p = tmp_path / "features.json"
    p.write_text(json.dumps([{"tag": "alpha", "pattern": "ALPHA_MARKER"}]))
    assert load_features(p) == [Feature(tag="alpha", pattern="ALPHA_MARKER", kinds=(), fields=("text",))]
    for bad, msg in [([{"pattern": "x"}], "missing tag"),
                     ([{"tag": "a", "pattern": "("}], "feature a: invalid regex"),
                     ([{"tag": "a", "pattern": "x", "kinds": ["shel"]}], "feature a: kinds"),
                     ([{"tag": "a", "pattern": "x", "fields": ["body"]}], "feature a: fields"),
                     ({"tag": "a"}, "must be a JSON list")]:
        p.write_text(json.dumps(bad))
        with pytest.raises(ValueError, match=msg):
            load_features(p)


def test_shipped_features_file_loads():
    assert load_features(ROOT / "rules" / "features.json")
