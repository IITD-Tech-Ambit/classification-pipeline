"""STAGE D step 1: fresh stratified 250-paper sample from classification_v3_final.

Same stratification approach as the original gold check (g01): proportional
across themes with a 10-per-theme floor, deliberately over-sampling the <0.5 and
0.5-0.8 confidence bands. Uses a DIFFERENT fixed seed than the original so this
is a genuine independent re-test, not a re-score of the same papers.

Output: outputs/work/goldset_v3_sample.jsonl.  READ-ONLY. No git.
"""
import json
import random
from collections import Counter, defaultdict

from common import OUTPUTS, WORK

FINAL = OUTPUTS / "classification_v3_final.jsonl"
SAMPLE_OUT = WORK / "goldset_v3_sample.jsonl"

SEED = 20260719  # different from the original gold check (20260718)
N_TOTAL = 250
THEME_FLOOR = 10
BAND_TARGET = {"<0.5": 0.40, "0.5-0.8": 0.30, ">=0.8": 0.30}
BANDS = ["<0.5", "0.5-0.8", ">=0.8"]


def band_of(conf):
    if conf is None:
        return None
    if conf < 0.5:
        return "<0.5"
    if conf < 0.8:
        return "0.5-0.8"
    return ">=0.8"


def largest_remainder(shares, total):
    raw = {k: v * total for k, v in shares.items()}
    floor = {k: int(v) for k, v in raw.items()}
    rem = total - sum(floor.values())
    order = sorted(shares, key=lambda k: raw[k] - floor[k], reverse=True)
    for i in range(rem):
        floor[order[i % len(order)]] += 1
    return floor


def main():
    rng = random.Random(SEED)
    rows = []
    with open(FINAL, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("unclassifiable"):
                continue
            conf = r.get("confidence")
            b = band_of(conf)
            if b is None:
                continue
            rows.append({"id": r["id"], "thematic_area": r.get("thematic_area"),
                         "domain": r.get("domain"), "confidence": conf,
                         "source_model": r.get("source_model"),
                         "escalated": r.get("escalated"),
                         "changed_from_v2": r.get("changed_from_v2"), "band": b})

    themes = sorted({r["thematic_area"] for r in rows if r["thematic_area"]})
    theme_counts = Counter(r["thematic_area"] for r in rows)
    base = {t: THEME_FLOOR for t in themes}
    prop = {t: theme_counts[t] / len(rows) for t in themes}
    extra = largest_remainder(prop, N_TOTAL - sum(base.values()))
    theme_alloc = {t: base[t] + extra[t] for t in themes}

    pool = defaultdict(list)
    for r in rows:
        pool[(r["thematic_area"], r["band"])].append(r)
    for k in pool:
        pool[k].sort(key=lambda r: r["id"])

    sampled, used = [], set()
    for t in themes:
        want = theme_alloc[t]
        avail = {b: len(pool[(t, b)]) for b in BANDS}
        desired = largest_remainder(BAND_TARGET, want)
        take, shortfall = {}, 0
        for b in BANDS:
            take[b] = min(desired[b], avail[b])
            shortfall += desired[b] - take[b]
        while shortfall > 0:
            headroom = {b: avail[b] - take[b] for b in BANDS}
            if sum(headroom.values()) == 0:
                break
            for b in sorted(BANDS, key=lambda x: BAND_TARGET[x], reverse=True):
                if shortfall <= 0:
                    break
                if headroom[b] > 0:
                    take[b] += 1
                    shortfall -= 1
        for b in BANDS:
            for p in rng.sample(pool[(t, b)], take[b]):
                sampled.append(p)
                used.add(p["id"])

    if len(sampled) < N_TOTAL:
        deficit = N_TOTAL - len(sampled)
        band_now = Counter(p["band"] for p in sampled)
        band_target_ct = largest_remainder(BAND_TARGET, N_TOTAL)
        leftovers = [r for r in rows if r["id"] not in used]

        def need(r):
            return band_target_ct[r["band"]] - band_now[r["band"]]
        rng.shuffle(leftovers)
        leftovers.sort(key=lambda r: -need(r))
        for r in leftovers[:deficit]:
            sampled.append(r)
            used.add(r["id"])
            band_now[r["band"]] += 1

    rng.shuffle(sampled)
    with open(SAMPLE_OUT, "w", encoding="utf-8") as fh:
        for p in sampled:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")

    band_dist = Counter(p["band"] for p in sampled)
    theme_dist = Counter(p["thematic_area"] for p in sampled)
    print(f"SAMPLED {len(sampled)} (unique {len(used)}) seed={SEED}")
    for b in BANDS:
        print(f"  {b:9} {band_dist[b]:4} ({100*band_dist[b]/len(sampled):.1f}%)")
    print("theme distribution:")
    for t in themes:
        print(f"  {theme_dist[t]:3} (alloc {theme_alloc[t]:3})  {t}")
    print(f"changed_from_v2 in sample: {sum(1 for p in sampled if p['changed_from_v2'])}")
    print(f"wrote {SAMPLE_OUT}")


if __name__ == "__main__":
    main()
