from pathlib import Path

from monitor.dataset import load_labelled, split_by_trajectory

FIX = Path(__file__).parent / "fixtures" / "labelled_sample.jsonl"


def test_load_assigns_labels_with_action_override():
    acts = load_labelled(FIX)
    assert len(acts) == 6
    t2 = [a for a in acts if a.trajectory_id == "t2"]
    assert [a.label for a in t2] == [0, 1]
    assert all(a.label == 0 for a in acts if a.trajectory_id == "t1")
    assert acts[0].task == "update docs" and acts[0].agent == "labelled"


def test_split_keeps_trajectories_whole_and_is_deterministic():
    acts = load_labelled(FIX)
    dev, test = split_by_trajectory(acts, test_fraction=0.5, seed=0)
    dev_ids = {a.trajectory_id for a in dev}
    test_ids = {a.trajectory_id for a in test}
    assert dev_ids.isdisjoint(test_ids) and dev_ids | test_ids == {"t1", "t2", "t3", "t4"}
    assert split_by_trajectory(acts, 0.5, 0) == (dev, test)


def test_load_rejects_missing_fields(tmp_path):
    p = tmp_path / "bad.jsonl"
    p.write_text('{"trajectory_id": "x", "actions": []}\n')
    try:
        load_labelled(p)
        assert False, "expected ValueError"
    except ValueError as e:
        assert "line 1" in str(e)
