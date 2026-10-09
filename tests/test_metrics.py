from monitor.metrics import confusion, roc_auc, threshold_for_fpr, tpr_at_fpr

S, L = [9, 8, 3, 1], [1, 1, 0, 0]


def test_perfect_separation():
    assert roc_auc(S, L) == 1.0
    assert tpr_at_fpr(S, L, 0.0) == 1.0


def test_auc_with_ties_counts_half():
    assert roc_auc([5, 5], [1, 0]) == 0.5


def test_threshold_respects_fpr_budget():
    scores, labels = [9, 7, 6, 5, 2], [1, 0, 1, 0, 0]
    t = threshold_for_fpr(scores, labels, fpr=0.34)  # at most 1 of 3 negatives flagged
    assert t == 6
    assert tpr_at_fpr(scores, labels, 0.34) == 1.0


def test_confusion_counts():
    c = confusion([9, 7, 6, 5, 2], [1, 0, 1, 0, 0], threshold=6)
    assert (c["tp"], c["fp"], c["tn"], c["fn"]) == (2, 1, 2, 0)
    assert c["precision"] == 2 / 3 and c["recall"] == 1.0


def test_metrics_return_none_with_one_class_and_ignore_none_scores():
    assert roc_auc([1, 2], [0, 0]) is None
    assert tpr_at_fpr([1, 2], [1, 1], 0.05) is None
    assert roc_auc([9, None, 1], [1, 1, 0]) == 1.0
