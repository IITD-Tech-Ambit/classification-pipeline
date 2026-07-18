"""STAGE 2: full Haiku classification of all eligible papers.

Reads outputs/work/papers_source.jsonl (68,644 eligible papers), classifies each
with claude-haiku-4-5 against the edited v2 taxonomy (prompt-cached), and appends
one row per paper to outputs/work/haiku_full.jsonl. Fully resumable and
checkpointed; enforces the cumulative cost guardrail.

Usage:  python s15_run_haiku.py [LIMIT]     # LIMIT optional, for smoke tests
"""
import json
import sys

from common import WORK
from s15_classify_lib import HAIKU_OUT, run_classification, write_cost_tracker

MODEL = "claude-haiku-4-5"
SOURCE = WORK / "papers_source.jsonl"
MAX_WORKERS = 40


def load_papers(limit=None):
    papers = []
    with open(SOURCE, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                papers.append(json.loads(line))
    papers.sort(key=lambda p: p["id"])  # deterministic order
    if limit:
        papers = papers[:limit]
    return papers


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    papers = load_papers(limit)
    print(f"[haiku] loaded {len(papers)} papers (limit={limit})", flush=True)
    res = run_classification(
        MODEL, papers, HAIKU_OUT, max_workers=MAX_WORKERS,
        checkpoint_every=500, label="haiku",
    )
    write_cost_tracker()
    print("[haiku] RESULT:", json.dumps({k: (v if k != "missing" else len(v))
                                         for k, v in res.items()}))
    if res["missing"]:
        print(f"[haiku] WARNING: {len(res['missing'])} still missing after passes")


if __name__ == "__main__":
    main()
