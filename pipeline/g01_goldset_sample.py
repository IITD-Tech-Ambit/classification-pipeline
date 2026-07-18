"""GOLD-SET step 1: build a stratified 250-paper sample for accuracy estimation.

Reads outputs/classification_v2_final.jsonl (classified rows only,
unclassifiable=false) and draws a reproducible stratified sample that is
stratified BOTH by thematic area (proportional, with a ~10-per-theme floor) AND
by confidence band, deliberately over-sampling the low-confidence tail so we can
measure accuracy per band rather than only overall.

Confidence bands:
    A "<0.5"     : confidence < 0.5      (target ~40% of sample)
    B "0.5-0.8"  : 0.5 <= confidence < 0.8 (target ~30%)
    C ">=0.8"    : confidence >= 0.8      (target ~30%)

Output: outputs/work/goldset_sample.jsonl  (one row per sampled paper with
id, thematic_area, domain, confidence, source_model, escalated, band).

READ-ONLY. Does not touch Mongo or git.
"""
import json
import random
from collections import Counter, defaultdict

from common import OUTPUTS, WORK

FINAL = OUTPUTS / "classification_v2_final.jsonl"
SAMPLE_OUT = WORK / "goldset_sample.jsonl"

SEED = 20260718
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
    """Apportion `total` integer slots across keys by their float `shares`
    (a dict) using the largest-remainder method. Returns dict key->int."""
    raw = {k: v * total for k, v in shares.items()}
    floor = {k: int(v) for k, v in raw.items()}
    used = sum(floor.values())
    rem = total - used
    order = sorted(shares, key=lambda k: raw[k] - floor[k], reverse=True)
    for i in range(rem):
        floor[order[i % len(order)]] += 1
    return floor


def main():
    rng = random.Random(SEED)

    rows = []
    skipped_no_conf = 0
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
                skipped_no_conf += 1
                continue
            rows.append({
                "id": r["id"],
                "thematic_area": r.get("thematic_area"),
                "domain": r.get("domain"),
                "confidence": conf,
                "source_model": r.get("source_model"),
                "escalated": r.get("escalated"),
                "band": b,
            })

    print(f"classified pool (unclassifiable=false, conf present): {len(rows)} "
          f"(skipped no-confidence: {skipped_no_conf})")

    themes = sorted({r["thematic_area"] for r in rows if r["thematic_area"]})
    theme_counts = Counter(r["thematic_area"] for r in rows)
    print(f"themes present: {len(themes)}")

    # ---- theme allocation: floor of THEME_FLOOR + proportional remainder ---- #
    base = {t: THEME_FLOOR for t in themes}
    remaining = N_TOTAL - sum(base.values())
    prop_shares = {t: theme_counts[t] / len(rows) for t in themes}
    extra = largest_remainder(prop_shares, remaining)
    theme_alloc = {t: base[t] + extra[t] for t in themes}
    assert sum(theme_alloc.values()) == N_TOTAL, sum(theme_alloc.values())

    # pool of ids indexed by (theme, band)
    pool = defaultdict(list)
    for r in rows:
        pool[(r["thematic_area"], r["band"])].append(r)
    for k in pool:
        pool[k].sort(key=lambda r: r["id"])  # deterministic before shuffle

    # ---- within each theme, split its allocation across bands to hit 40/30/30,
    #      capped by availability, redistributing any shortfall ------------- #
    sampled = []
    used_ids = set()
    per_cell = {}
    for t in themes:
        want = theme_alloc[t]
        avail = {b: len(pool[(t, b)]) for b in BANDS}
        # desired band split for this theme
        desired = largest_remainder(BAND_TARGET, want)
        # cap by availability, collect shortfall
        take = {}
        shortfall = 0
        for b in BANDS:
            take[b] = min(desired[b], avail[b])
            shortfall += desired[b] - take[b]
        # redistribute shortfall to bands that still have headroom
        while shortfall > 0:
            headroom = {b: avail[b] - take[b] for b in BANDS}
            if sum(headroom.values()) == 0:
                break  # theme simply doesn't have `want` papers
            # prefer filling the largest-target bands with headroom first
            for b in sorted(BANDS, key=lambda x: BAND_TARGET[x], reverse=True):
                if shortfall <= 0:
                    break
                if headroom[b] > 0:
                    take[b] += 1
                    shortfall -= 1
        per_cell[t] = take
        for b in BANDS:
            picks = rng.sample(pool[(t, b)], take[b])
            for p in picks:
                sampled.append(p)
                used_ids.add(p["id"])

    # ---- if any theme fell short of `want` (rare theme), top up globally to
    #      keep total near N_TOTAL, preserving band ratios where possible --- #
    if len(sampled) < N_TOTAL:
        deficit = N_TOTAL - len(sampled)
        leftovers = [r for r in rows if r["id"] not in used_ids]
        # sort so we prefer under-filled bands first for the deficit
        band_now = Counter(p["band"] for p in sampled)
        band_target_ct = largest_remainder(BAND_TARGET, N_TOTAL)

        def band_need(r):
            return band_target_ct[r["band"]] - band_now[r["band"]]
        leftovers.sort(key=lambda r: (-band_need(r), r["id"]))
        rng.shuffle(leftovers)  # break ties randomly but reproducibly
        leftovers.sort(key=lambda r: -band_need(r))
        for r in leftovers[:deficit]:
            sampled.append(r)
            used_ids.add(r["id"])
            band_now[r["band"]] += 1

    rng.shuffle(sampled)

    # ---- persist ---- #
    with open(SAMPLE_OUT, "w", encoding="utf-8") as fh:
        for p in sampled:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")

    # ---- report composition ---- #
    band_dist = Counter(p["band"] for p in sampled)
    theme_dist = Counter(p["thematic_area"] for p in sampled)
    src_dist = Counter(p["source_model"] for p in sampled)
    print(f"\nSAMPLED {len(sampled)} papers (unique ids: {len(used_ids)}) seed={SEED}")
    print("band distribution:")
    for b in BANDS:
        pct = 100 * band_dist[b] / len(sampled)
        print(f"  {b:9} {band_dist[b]:4}  ({pct:.1f}%)  target {BAND_TARGET[b]*100:.0f}%")
    print("theme distribution (alloc vs actual):")
    for t in themes:
        print(f"  {theme_dist[t]:3} (alloc {theme_alloc[t]:3})  {t}")
    print("source_model distribution:", dict(src_dist))
    print(f"\nwrote {SAMPLE_OUT}")


if __name__ == "__main__":
    main()
