import pytest

from monitor.categories import CATEGORIES, normalize_category
from monitor.config import Config, load_config


def test_categories_are_apollo_failure_modes_plus_other():
    assert len(CATEGORIES) == 14 and CATEGORIES[-1] == "other"
    assert "data_exfiltration" in CATEGORIES and "oversight_subversion" in CATEGORIES


def test_normalize_category_maps_unknown_to_other():
    assert normalize_category("privilege_escalation") == "privilege_escalation"
    assert normalize_category("made_up") == "other"
    assert normalize_category(None) == "other"


def test_missing_config_file_gives_defaults(tmp_path):
    cfg = load_config(tmp_path / "monitor.toml")
    assert cfg == Config() and cfg.settle_low == 1.0 and cfg.gateway_model == "qwen3:8b"


def test_config_overrides_and_coerces_ints(tmp_path):
    p = tmp_path / "monitor.toml"
    p.write_text('notify = false\nescalate_at = 6\ntriage_model = "qwen3:1.7b"\n')
    cfg = load_config(p)
    assert cfg.notify is False and cfg.escalate_at == 6.0 and isinstance(cfg.escalate_at, float)
    assert cfg.triage_model == "qwen3:1.7b"


def test_config_rejects_unknown_keys_and_wrong_types(tmp_path):
    p = tmp_path / "monitor.toml"
    p.write_text("setle_low = 2\n")
    with pytest.raises(ValueError, match="unknown key 'setle_low'"):
        load_config(p)
    p.write_text('notify = "yes"\n')
    with pytest.raises(ValueError, match="notify must be bool"):
        load_config(p)
    p.write_text("queue_max = true\n")
    with pytest.raises(ValueError, match="queue_max must be int"):
        load_config(p)


@pytest.mark.parametrize("toml, key", [
    ("queue_max = 0\n", "queue_max"),
    ("settle_low = 9\nsettle_high = 9\n", "settle_low"),
    ('socket_path = "m.sock"\n', "socket_path"),
    ("min_confidence = 1.5\n", "min_confidence"),
])
def test_config_rejects_out_of_range_values(tmp_path, toml, key):
    p = tmp_path / "monitor.toml"
    p.write_text(toml)
    with pytest.raises(ValueError, match=key):
        load_config(p)
