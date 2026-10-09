import json
from pathlib import Path


def _f(v, fmt):
    return "n/a" if v is None else format(v, fmt)


def _ms(v) -> str:
    return "n/a" if v is None else f"{v:.1f}" if v >= 1 else f"{v:.3f}"


def _judge_failures(r: dict) -> str:
    return f"{r['judge_failures']} of {r['judge_calls']} calls" if "judge_calls" in r else "-"


def _na_reason(r: dict) -> str:
    if not r.get("n_test"):
        return "no actions in the evaluated split"
    if not r.get("n_scored"):
        return "no scores (judge failed or unavailable)"
    return f"only one class in the evaluated split (pos={r.get('n_pos', '?')}, neg={r.get('n_neg', '?')})"


def _alert_rows(alerts) -> list[str]:
    lines = ["| score | agent | tool | action |", "|---|---|---|---|"]
    for a in alerts:
        text = a["text"].replace("|", "\\|").replace("\n", " ")[:160]
        lines.append(f"| {a['score']:.1f} | {a['agent']} | {a['tool']} | `{text}` |")
    return lines


def _eval_section(eval_res: dict) -> list[str]:
    rows = eval_res.get("scorers", eval_res)  # older eval.json files hold the rows at the top level
    split = eval_res.get("split") if "scorers" in eval_res else None
    lines = []
    if eval_res.get('schema_version') != 2 or not eval_res.get('provenance'):
        lines += ['Legacy measurements: unknown provenance; dataset and threshold selection are unverified.', '']
    else:
        p = eval_res['provenance']
        lines += [f"Dataset: {p['dataset']} ({p['dataset_kind']}); recorded {p['created_at']}.",
                  'Rates use assessed actions; thresholds at every operating point were selected on development data.', '']
        lines += ['- ' + x for x in eval_res.get('limitations', [])] + ['']
    if split == "dev":
        lines += ["Evaluated split: dev (threshold chosen and measured on the same data; "
                  "run `monitor eval --final` for held-out test numbers).", ""]
    elif split:
        lines += [f"Evaluated split: {split} (held-out; threshold chosen on dev).", ""]
    lines += ["| monitor | AUC | recall at dev 1% target | recall at dev 5% target | precision | recall | scored/total "
              "| median latency (ms) | judge failures |",
              "|---|---|---|---|---|---|---|---|---|"]
    notes = []
    for name, r in rows.items():
        c = r.get("test_confusion") or {}
        lines.append(f"| {name} | {_f(r['auc'], '.3f')} | {_f(r['tpr_at_fpr'].get('0.01'), '.2f')} | "
                     f"{_f(r['tpr_at_fpr'].get('0.05'), '.2f')} | {_f(c.get('precision'), '.2f')} | "
                     f"{_f(c.get('recall'), '.2f')} | {r['n_scored']}/{r['n_test']} | "
                     f"{_ms(r.get('median_latency_ms'))} | {_judge_failures(r)} |")
        if r["auc"] is None:
            notes.append(f"n/a ({name}): {_na_reason(r)}")
    if eval_res.get('schema_version') == 2:
        lines += ['', '| monitor | false alarm rate | miss rate | coverage | incomplete | dev threshold / achieved FPR |', '|---|---|---|---|---|---|']
        for name,r in rows.items():
            m = r.get('metrics') or {}
            op = r.get('operating_points', {}).get('0.05', {})
            threshold = 'reject all' if op.get('reject_all') else str(op.get('threshold', 'n/a'))
            lines.append(f"| {name} | {_f(m.get('false_alarm_rate'), '.3f')} | {_f(m.get('miss_rate'), '.3f')} | {_f(r.get('coverage'), '.3f')} | {r.get('n_incomplete','?')} | {threshold} / {_f(op.get('actual_fpr'), '.3f')} |")
    if notes:
        lines += [""] + [f"- {n}" for n in notes]
    return lines


def render_report(eval_res: dict | None, real_res: dict | None) -> str:
    lines = ["# Agent traffic monitor: results", ""]
    if eval_res:
        lines += _eval_section(eval_res)
    if real_res:
        lines += ["", "## Real traffic", "",
                  f"{real_res['n_alerts']} alerts in {real_res['n_actions']:,} real actions: "
                  f"{real_res['alerts_per_1000']} alerts per 1,000 actions "
                  f"({real_res.get('n_skipped', 0)} malformed lines skipped).", ""]
        lines += ["This is unlabelled alert volume, not a false-positive rate.", ""]
        lines += _alert_rows(real_res["top_alerts"])
        js = real_res.get("judge_sample")
        if js:
            health = f" Judge failures: {js['judge_failures']} of {js['judge_calls']} calls." if "judge_calls" in js else ""
            lines += ["", f"Judge sample (rules + judge, {js['n_scored']} of {js['n_actions']} sampled actions "
                          f"scored): {js['n_alerts']} alerts, {js['alerts_per_1000']} per 1,000.{health}", ""]
            lines += _alert_rows(js["top_alerts"])
    return "\n".join(lines) + "\n"


def render_files(eval_path, real_path) -> str | None:
    """Render whichever result files exist; None when there is nothing to report."""
    ev = json.loads(Path(eval_path).read_text()) if Path(eval_path).exists() else None
    real = json.loads(Path(real_path).read_text()) if Path(real_path).exists() else None
    if ev is None and real is None:
        return None
    return render_report(ev, real)
