"""Copy the demo logs into a scratch logs dir, shifting timestamps so the newest event is 'now'."""
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "tests" / "fixtures" / "demo_events"
TS_FIELDS = ("ts", "scored_ts", "opened", "updated")


def main(dest: str) -> None:
    out = Path(dest).resolve()
    if out.parent != Path(__file__).resolve().parent:
        raise SystemExit(f"refusing to write outside dashboard/e2e/: {out}")
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    files = {name: [json.loads(line) for line in (SRC / name).read_text().splitlines() if line.strip()]
             for name in ("events.jsonl", "incidents.jsonl")}
    newest = max(r[f] for rows in files.values() for r in rows for f in TS_FIELDS if isinstance(r.get(f), (int, float)))
    shift = time.time() - newest
    for name, rows in files.items():
        with open(out / name, "w") as f:
            for r in rows:
                for k in TS_FIELDS:
                    if isinstance(r.get(k), (int, float)):
                        r[k] += shift
                f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main(sys.argv[1])
