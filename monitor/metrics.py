def _clean(scores, labels):
    pairs = [(float(s), int(y)) for s, y in zip(scores, labels) if s is not None]
    pos = [s for s, y in pairs if y == 1]
    neg = [s for s, y in pairs if y == 0]
    return pos, neg


def roc_auc(scores, labels):
    pos, neg = _clean(scores, labels)
    if not pos or not neg:
        return None
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def threshold_for_fpr(scores, labels, fpr):
    pos, neg = _clean(scores, labels)
    if not pos or not neg:
        return None
    for t in sorted(set(pos + neg)):
        if sum(n >= t for n in neg) / len(neg) <= fpr:
            return t
    return float("inf")


def tpr_at_fpr(scores, labels, fpr):
    t = threshold_for_fpr(scores, labels, fpr)
    if t is None:
        return None
    pos, _ = _clean(scores, labels)
    return sum(p >= t for p in pos) / len(pos)


def confusion(scores, labels, threshold):
    pos, neg = _clean(scores, labels)
    tp, fn = sum(p >= threshold for p in pos), sum(p < threshold for p in pos)
    fp, tn = sum(n >= threshold for n in neg), sum(n < threshold for n in neg)
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "fpr": fp / (fp + tn) if fp + tn else None}
