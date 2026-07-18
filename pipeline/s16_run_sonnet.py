"""STAGE 3 (part 1): Sonnet escalation.

Selects the escalation set from the Haiku full pass = papers with
confidence < 0.6 OR a schema violation (invalid/missing theme-domain), and
re-classifies them with claude-sonnet-4-5 (same prompt-cached v2 taxonomy and
schema). Appends to outputs/work/sonnet_escalation.jsonl. Resumable, checkpointed,
cost-guarded.

Usage:  python s16_run_sonnet.py [LIMIT]
"""
import json
import sys

from common import WORK
from s15_classify_lib import SONNET_OUT, run_classification, write_cost_tracker

MODEL = "claude-sonnet-4-5"
SOURCE = WORK / "papers_source.jsonl"
HAIKU_OUT = WORK / "haiku_full.jsonl"
CONF_THRESH = 0.6
MAX_WORKERS = 24


def needs_escalation(r):
    if not r.get("schema_valid"):
        return True
    c = r.get("confidence")
    if c is None:
        return True
    return c < CONF_THRESH


def load_source():
    src = {}
    with open(SOURCE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                p = json.loads(line)
                src[p["id"]] = p
    return src


def escalation_ids():
    ids = []
    with open(HAIKU_OUT, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if needs_escalation(r):
                ids.append(r["id"])
    return ids


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    src = load_source()
    esc = escalation_ids()
    esc = [i for i in esc if i in src]
    esc.sort()
    if limit:
        esc = esc[:limit]
    papers = [src[i] for i in esc]
    print(f"[sonnet] escalation set: {len(papers)} papers "
          f"(conf<{CONF_THRESH} or schema violation) limit={limit}", flush=True)

    res = run_classification(
        MODEL, papers, SONNET_OUT, max_workers=MAX_WORKERS,
        checkpoint_every=300, label="sonnet",
    )
    write_cost_tracker()
    print("[sonnet] RESULT:", json.dumps({k: (v if k != "missing" else len(v))
                                          for k, v in res.items()}))
    if res["missing"]:
        print(f"[sonnet] WARNING: {len(res['missing'])} still missing after passes")


if __name__ == "__main__":
    main()
