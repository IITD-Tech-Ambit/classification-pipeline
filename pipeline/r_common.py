"""Shared helpers for the v3 refinement (Stage B re-pass + Stage D re-validation).

Reuses the low-level, already-validated machinery in s15_classify_lib
(classify_task, Validator, cost_from_usage, PRICING) but points at the v3
taxonomy and injects the taxonomy-level global_rules into the system prompt.

READ-ONLY DB. No git.
"""
import json
import re

from common import OUTPUTS, WORK
from s15_classify_lib import build_system_prompt as _base_prompt

V3_TAXONOMY = OUTPUTS / "taxonomy-draft-v3.json"
FINAL_V2 = OUTPUTS / "classification_v2_final.jsonl"
PAPERS = WORK / "papers_source.jsonl"

SINK_DOMAINS = {
    "Grid Integration & Smart Microgrids",
    "Semiconductor Photovoltaic & Photodetection Devices",
    "Materials, Joining & Mechanical Behavior",
    "Power Systems & Grid Control",
    "Algorithms & Computational Complexity",
}


def load_taxonomy_v3():
    tax = json.loads(V3_TAXONOMY.read_text(encoding="utf-8"))
    themes = tax["themes"]
    theme_to_domains = {t["name"]: [d["name"] for d in t["domains"]] for t in themes}
    return tax, themes, theme_to_domains


# sentences carrying a routing/tie-break decision are kept verbatim; purely
# descriptive prose is dropped to shrink the cached prompt (cache-read is the
# dominant per-paper cost). This removes NO exclusion or tie-break logic.
_DECISION_RE = re.compile(
    r"assign|belong|instead|rather than|\bnot\b|tie-?break|exclud|route|"
    r"->|\u2192|primary contribution|classify by|goes to|remain|reserve|"
    r"only when|only assign|do not|does not|never|when a paper|if a paper|"
    r"if the|whereas", re.I)


def _split_sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.;])\s+", text.strip()) if s.strip()]


def compact_scope(scope_note):
    """Keep the first (theme-summary) sentence + every decision-bearing sentence."""
    sents = _split_sentences(scope_note)
    if not sents:
        return scope_note
    kept = [sents[0]]
    for s in sents[1:]:
        if _DECISION_RE.search(s):
            kept.append(s)
    return " ".join(kept)


def _compact_themes(themes):
    out = []
    for t in themes:
        t2 = dict(t)
        t2["scope_note"] = compact_scope(t["scope_note"])
        out.append(t2)
    return out


def build_system_prompt_v3(tax, themes, compact=True):
    """Full v2-style prompt (frozen taxonomy + strict-JSON output rules) plus a
    prominent GLOBAL RULES block carrying the v3 method-vs-application and
    out-of-scope routing rules, and a terse-reason instruction to hold down
    output-token cost. When compact=True the theme scope_notes are reduced to
    their decision-bearing sentences (all tie-break/exclusion logic retained;
    only descriptive prose dropped) to cut the cached-prompt size."""
    use_themes = _compact_themes(themes) if compact else themes
    base = _base_prompt(use_themes)
    gr = tax.get("global_rules", [])
    block = ["", "=" * 70, "GLOBAL RULES (apply to EVERY paper, across all themes):"]
    for i, g in enumerate(gr, 1):
        block.append(f"{i}. {g}")
    block.append(
        "OUTPUT SIZE (mandatory, overrides 'one concise sentence' above): keep the "
        "whole JSON object small. 'reason' must be a TERSE fragment of at most 8 "
        "words -- not a sentence, do NOT restate the title. For out-of-scope papers "
        "set unclassifiable=true and begin reason with 'out_of_scope:'.")
    block.append("=" * 70)
    return base + "\n" + "\n".join(block)


def band_of(c):
    if c is None:
        return None
    if c < 0.5:
        return "<0.5"
    if c < 0.8:
        return "0.5-0.8"
    return ">=0.8"


def load_v2_rows():
    rows = []
    with open(FINAL_V2, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def load_text_map():
    m = {}
    with open(PAPERS, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                r = json.loads(line)
                m[r["id"]] = r
    return m


def build_repass_set(rows):
    """The Stage B re-classification set:
       (a) every classified paper with confidence < 0.8, PLUS
       (b) every classified paper with confidence >= 0.8 sitting in a sink domain.
    Returns (set_of_ids, reason_map id->'lowconf'|'hi_conf_sink')."""
    ids, why = set(), {}
    for r in rows:
        if r.get("unclassifiable"):
            continue
        c = r.get("confidence")
        if c is None:
            continue
        if c < 0.8:
            ids.add(r["id"]); why[r["id"]] = "lowconf"
        elif r.get("domain") in SINK_DOMAINS:
            ids.add(r["id"]); why[r["id"]] = "hi_conf_sink"
    return ids, why
