"""Step 2b: rebuild theme pools from the corrected labels and report v1->v2 confusion.

Uses the cached per-paper metadata (samples.json) and cached embeddings (embeddings.npz),
so nothing is re-embedded. Emits:
  - pools_v2.json: for each theme, the list of paper ids now assigned to it (v2), plus the
    per-paper embedding row index into a rebuilt flat embedding matrix.
  - emb_flat.npz: one flat (N, 768) matrix `emb` aligned to `pool_index` for all sampled
    papers (theme + unclassified), so later steps can index any paper by id.
  - confusion_v2.json: v1->v2 migration counts and headline stats.
"""
import json
from collections import defaultdict

import numpy as np

from common import WORK

UNCLS = "unclassifiable"


def main():
    samples = json.loads((WORK / "samples.json").read_text(encoding="utf-8"))
    corrected = json.loads((WORK / "theme_corrected.json").read_text(encoding="utf-8"))
    facts = json.loads((WORK / "db_facts.json").read_text(encoding="utf-8"))
    emb = np.load(WORK / "embeddings.npz")
    name_by_id = {t["id"]: t["name"] for t in facts["themes"]}
    name_by_id[None] = "(v1 unclassified)"
    assignments = corrected["assignments"]

    # flat embedding matrix + paper metadata, indexed by a stable position
    pid_to_emb = {}
    pid_to_paper = {}
    for tid, papers in samples["by_theme"].items():
        arr = emb[tid]
        for i, p in enumerate(papers):
            pid_to_emb[p["id"]] = arr[i]
            pid_to_paper[p["id"]] = p
    uarr = emb["__unclassified__"]
    for i, p in enumerate(samples["unclassified"]):
        pid_to_emb[p["id"]] = uarr[i]
        pid_to_paper[p["id"]] = p

    all_pids = list(pid_to_paper.keys())
    flat = np.vstack([pid_to_emb[pid] for pid in all_pids]).astype(np.float32)
    pool_index = {pid: i for i, pid in enumerate(all_pids)}

    # corrected pools
    pools = defaultdict(list)
    n_unclassifiable = 0
    for pid in all_pids:
        a = assignments.get(pid)
        if a is None:
            continue
        v2 = a["v2"]
        if v2 == UNCLS:
            n_unclassifiable += 1
            continue
        pools[v2].append(pid)

    # confusion v1 -> v2
    confusion = defaultdict(lambda: defaultdict(int))
    moved = 0
    stayed = 0
    from_unclassified = 0
    for pid in all_pids:
        a = assignments.get(pid)
        if a is None:
            continue
        v1, v2 = a["v1"], a["v2"]
        confusion[v1][v2] += 1
        if v1 is None:
            from_unclassified += 1
            continue
        if v2 == v1:
            stayed += 1
        else:
            moved += 1

    n_from_v1 = sum(1 for pid in all_pids if assignments.get(pid) and assignments[pid]["v1"])
    # biggest migrations (exclude same-theme and v1=None)
    migrations = []
    for v1, row in confusion.items():
        if v1 is None:
            continue
        for v2, c in row.items():
            if v2 == v1:
                continue
            label_v2 = name_by_id.get(v2, v2) if v2 != UNCLS else "UNCLASSIFIABLE"
            migrations.append((c, name_by_id[v1], label_v2))
    migrations.sort(reverse=True)

    # per-theme in/out summary
    theme_summary = []
    for t in facts["themes"]:
        tid = t["id"]
        v1_sampled = len(samples["by_theme"].get(tid, []))
        v2_size = len(pools.get(tid, []))
        kept = confusion[tid][tid]
        theme_summary.append({
            "theme": t["name"], "id": tid,
            "v1_sampled": v1_sampled,
            "v2_pool_size": v2_size,
            "kept_from_own_v1": kept,
            "purity_v1": round(kept / v1_sampled, 3) if v1_sampled else None,
        })

    out = {
        "n_total_sampled": len(all_pids),
        "n_from_v1_themes": n_from_v1,
        "n_from_v1_unclassified": len(samples["unclassified"]),
        "moved_theme": moved,
        "stayed_theme": stayed,
        "pct_moved": round(moved / n_from_v1, 3) if n_from_v1 else None,
        "n_unclassifiable": n_unclassifiable,
        "biggest_migrations": [
            {"count": c, "from": f, "to": to} for c, f, to in migrations[:25]
        ],
        "per_theme": theme_summary,
        "unclassified_sample_routed_to": {
            name_by_id.get(k, str(k)) if k != UNCLS else "UNCLASSIFIABLE": v
            for k, v in sorted(confusion[None].items(), key=lambda x: -x[1])
        },
    }
    (WORK / "confusion_v2.json").write_text(json.dumps(out, indent=2, ensure_ascii=False),
                                            encoding="utf-8")

    np.savez_compressed(WORK / "emb_flat.npz", emb=flat)
    pools_out = {
        "pool_index": pool_index,
        "pools": {tid: pids for tid, pids in pools.items()},
        "papers": pid_to_paper,
    }
    (WORK / "pools_v2.json").write_text(json.dumps(pools_out, ensure_ascii=False),
                                        encoding="utf-8")

    print(f"total sampled: {len(all_pids)}")
    print(f"from v1 themes: {n_from_v1} | moved: {moved} ({out['pct_moved']:.1%}) | stayed: {stayed}")
    print(f"unclassifiable: {n_unclassifiable}")
    print("corrected pool sizes:")
    for ts in sorted(theme_summary, key=lambda x: -x["v2_pool_size"]):
        print(f"  {ts['theme'][:45]:45} v1={ts['v1_sampled']:4} -> v2={ts['v2_pool_size']:4} "
              f"(kept {ts['kept_from_own_v1']}, purity {ts['purity_v1']})")
    print("biggest migrations:")
    for m in out["biggest_migrations"][:12]:
        print(f"  {m['count']:4}  {m['from'][:38]:38} -> {m['to']}")
    print("done")


if __name__ == "__main__":
    main()
