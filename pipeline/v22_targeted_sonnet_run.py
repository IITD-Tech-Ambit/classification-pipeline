"""v2.2 targeted Sonnet correction — gap-fill taxonomy + high-yield queue.

Follow-up constraints:
  - concurrency start 50, ramp toward 80 if 429 rate stays low
  - HARD total budget $70; stop correction expansion near $55 (reserve ~$15 validation)
  - resume from checkpoints (same outputs); do not start a competing second full run
  - accept v2.2 only if honest validation improves vs frozen v2.1
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
import threading
import time
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anthropic
from dotenv import load_dotenv

from common import OUTPUTS, ROOT, WORK

# ----------------------------- fixed paths --------------------------------- #
BASELINE = OUTPUTS / "classification_v2_1_candidate.jsonl"
FROZEN = OUTPUTS / "safe_baseline" / "classification_v21_frozen.jsonl"
PAPERS = WORK / "papers_source.jsonl"
TAXONOMY_PATH = OUTPUTS / "taxonomy-draft-v22.json"

QUEUE_OUT = WORK / "v22_target_queue.jsonl"
TARGETED_OUT = WORK / "sonnet_targeted_v22.jsonl"
COST_OUT = WORK / "sonnet_v22_cost.json"
CANDIDATE_OUT = OUTPUTS / "classification_v2_2_candidate.jsonl"
VALIDATION_JSONL = WORK / "v22_random_subset_adjudication.jsonl"
RUN_REPORT_MD = OUTPUTS / "v22_run_report.md"
VALIDATION_MD = OUTPUTS / "v22_validation_random_subset.md"
AUDIT50_MD = OUTPUTS / "audit_50_random_v22.md"
DECISION_JSON = WORK / "v22_decision.json"

# ------------------------------ run config --------------------------------- #
TOTAL_BUDGET_USD = 70.0
VALIDATION_BUDGET_RESERVE = 15.0
CORRECTION_BUDGET_USD = TOTAL_BUDGET_USD - VALIDATION_BUDGET_RESERVE  # 55
CORRECTION_SOFT_STOP = 55.0

START_WORKERS = 50
RAMP_WORKERS = 65
MAX_WORKERS = 80
PILOT_ROWS = 80
PILOT_WORKERS = 20
CHECKPOINT_EVERY = 200

MAX_API_ATTEMPTS = 6
PHASE_429_OK = 0.05
PHASE_5XX_OK = 0.03

QUEUE_HARD_CAP = int(os.environ.get("V22_QUEUE_HARD_CAP", "7000"))
RPM_LIMIT = int(os.environ.get("V22_RPM_LIMIT", "2000"))
TPM_LIMIT = int(os.environ.get("V22_TPM_LIMIT", "1000000"))

VALIDATION_SAMPLE_N = int(os.environ.get("V22_VALIDATION_SAMPLE_N", "180"))
VALIDATION_SEED = int(os.environ.get("V22_VALIDATION_SEED", "20260720"))
AUDIT50_SEED = int(os.environ.get("V22_AUDIT50_SEED", "20260721"))

CORRECTION_MODEL_CANDIDATES = ["claude-sonnet-4-5"]
JUDGE_MODEL_CANDIDATES = [
    "claude-opus-4-5",
    "claude-opus-4-1",
    "claude-sonnet-4-5",
]

PRICING = {
    "claude-haiku-4-5": {"in": 1.00, "out": 5.00, "cache_write": 1.25, "cache_read": 0.10},
    "claude-sonnet-4-5": {"in": 3.00, "out": 15.00, "cache_write": 3.75, "cache_read": 0.30},
    "claude-opus-4-1": {"in": 15.00, "out": 75.00, "cache_write": 18.75, "cache_read": 1.50},
    "claude-opus-4-5": {"in": 15.00, "out": 75.00, "cache_write": 18.75, "cache_read": 1.50},
}

# Domain rename identity map (v2.1 label → v2.2 taxonomy name)
DOMAIN_RENAME = {
    "Clinical Biosensors & Point-of-Care Devices": "Clinical Biosensors & Implant Bioelectronics",
}

GAP_FILL_DOMAINS = {
    "Thermoelectric & Energy-Harvesting Materials",
    "Optical Metrology & Interferometric Instrumentation",
    "Computer Architecture & Systems",
    "Clinical Biosensors & Implant Bioelectronics",
}

SINK_DOMAINS = {
    "Energy Storage Materials",
    "Solar Thermal Energy & Heat Transfer Systems",
    "Clinical Biosensors & Point-of-Care Devices",
    "Clinical Biosensors & Implant Bioelectronics",
    "Algorithms & Computational Complexity",
    "Materials, Joining & Mechanical Behavior",
    "Power Systems & Grid Control",
    "Digital Culture & Consumer Experience",
    "Biomanufacturing & Fermentation Processes",
    "Fiber Photonic Devices & Engineering",
    "Plasmonic & Fiber Optic Sensors",
    "Electric Motor Drives & Power Electronics",
}

KEYWORD_GROUPS: list[tuple[str, re.Pattern[str]]] = [
    ("thermoelectric", re.compile(r"\bthermoelectric|seebeck|peltier|figure of merit|\bzt\b|skutterudite|energy.?harvest", re.I)),
    ("optical_metrology", re.compile(r"interferometr|white.?light interfer|optical metrology|michelson|phase.?shifting interfer", re.I)),
    ("implant_power", re.compile(r"implantable|wireless power transfer|\bimd\b|inductive (power|coupling).*implant|implant.*inductive", re.I)),
    ("architecture", re.compile(r"\bvliw\b|computer architecture|microarchitecture|on.?chip interconnect|memory hierarchy|\bisa\b|many.?core", re.I)),
    ("accelerator_rf", re.compile(r"accelerator.*(rf|llrf|cavity|phase.?lock)|superconducting (rf|cavity)|particle accelerator", re.I)),
    ("fuel_additive", re.compile(r"fuel additive|engine deposit|deposit control|combustion deposit", re.I)),
    ("pat_biopharma", re.compile(r"\bpat\b|monoclonal antibod|biosimilar|glycosylation|aggregation.*(mab|antibody)|biopharmaceutical", re.I)),
    ("mechanism_design", re.compile(r"mechanism design|peer.?prediction|incentive.?compat|algorithmic game", re.I)),
]


@dataclass
class Taxonomy:
    path: Path
    themes: list[dict[str, Any]]
    theme_to_domains: dict[str, list[dict[str, Any]]]
    theme_to_domain_names: dict[str, list[str]]
    domain_to_theme: dict[str, str]
    global_rules: list[str]


class RateLimiter:
    def __init__(self, rpm_limit: int, tpm_limit: int):
        self.rpm_limit = rpm_limit
        self.tpm_limit = tpm_limit
        self.req_events: deque = deque()
        self.tok_events: deque = deque()
        self.tok_sum = 0
        self.lock = threading.Lock()

    def _prune(self, now: float) -> None:
        cutoff = now - 60.0
        while self.req_events and self.req_events[0] < cutoff:
            self.req_events.popleft()
        while self.tok_events and self.tok_events[0][0] < cutoff:
            _, tok = self.tok_events.popleft()
            self.tok_sum -= tok

    def acquire(self, est_tokens: int) -> None:
        while True:
            with self.lock:
                now = time.time()
                self._prune(now)
                req_used = len(self.req_events)
                tok_used = self.tok_sum
                if req_used < self.rpm_limit and (tok_used + est_tokens) <= self.tpm_limit:
                    self.req_events.append(now)
                    self.tok_events.append((now, est_tokens))
                    self.tok_sum += est_tokens
                    return
                req_wait = 0.05
                tok_wait = 0.05
                if req_used >= self.rpm_limit and self.req_events:
                    req_wait = max(0.05, 60.0 - (now - self.req_events[0]) + 0.01)
                if (tok_used + est_tokens) > self.tpm_limit and self.tok_events:
                    tok_wait = max(0.05, 60.0 - (now - self.tok_events[0][0]) + 0.01)
                wait_s = max(req_wait, tok_wait)
            time.sleep(min(wait_s, 1.0))


# concurrency telemetry
_ACTIVE_WORKERS = 0
_PEAK_PARALLEL = 0
_ACTIVE_LOCK = threading.Lock()


def track_enter() -> None:
    global _ACTIVE_WORKERS, _PEAK_PARALLEL
    with _ACTIVE_LOCK:
        _ACTIVE_WORKERS += 1
        if _ACTIVE_WORKERS > _PEAK_PARALLEL:
            _PEAK_PARALLEL = _ACTIVE_WORKERS


def track_exit() -> None:
    global _ACTIVE_WORKERS
    with _ACTIVE_LOCK:
        _ACTIVE_WORKERS -= 1


def now_ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def parse_json_object(text: str) -> dict[str, Any]:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1)
    s = text.find("{")
    e = text.rfind("}")
    if s < 0 or e < 0:
        raise ValueError("no JSON object found")
    return json.loads(text[s : e + 1])


def usage_dict(u: Any) -> dict[str, int]:
    return {
        "input_tokens": int(getattr(u, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(u, "output_tokens", 0) or 0),
        "cache_write": int(getattr(u, "cache_creation_input_tokens", 0) or 0),
        "cache_read": int(getattr(u, "cache_read_input_tokens", 0) or 0),
    }


def add_usage(a: dict[str, int], b: dict[str, int]) -> None:
    for k in ("input_tokens", "output_tokens", "cache_write", "cache_read"):
        a[k] = a.get(k, 0) + b.get(k, 0)


def cost_from_usage(model: str, usage: dict[str, int]) -> float:
    p = PRICING.get(model)
    if not p:
        return 0.0
    return (
        usage.get("input_tokens", 0) / 1e6 * p["in"]
        + usage.get("output_tokens", 0) / 1e6 * p["out"]
        + usage.get("cache_write", 0) / 1e6 * p["cache_write"]
        + usage.get("cache_read", 0) / 1e6 * p["cache_read"]
    )


def normalize(s: str | None) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def band_of(c: float | None) -> str:
    if c is None:
        return "none"
    if c < 0.5:
        return "<0.5"
    if c < 0.8:
        return "0.5-0.8"
    return ">=0.8"


def out_of_scope_evidence(reason: str | None) -> bool:
    r = normalize(reason)
    if not r:
        return False
    keys = [
        "out_of_scope",
        "outside taxonomy",
        "no research signal",
        "front matter",
        "editorial",
        "no abstract",
        "insufficient signal",
        "cannot classify",
        "accelerator rf",
        "fuel-additive",
        "fuel additive",
    ]
    return any(k in r for k in keys)


def tie_break_reason(reason: str | None) -> bool:
    r = normalize(reason)
    if not r:
        return False
    keys = ["tie-break", "rather than", "instead of", "primary contribution", "rule", "because", "prefer"]
    return any(k in r for k in keys)


def read_taxonomy() -> Taxonomy:
    if not TAXONOMY_PATH.exists():
        raise SystemExit(f"missing taxonomy {TAXONOMY_PATH}; run v22_build_taxonomy.py first")
    tax = json.loads(TAXONOMY_PATH.read_text(encoding="utf-8"))
    themes = tax["themes"]
    theme_to_domains: dict[str, list[dict[str, Any]]] = {}
    theme_to_domain_names: dict[str, list[str]] = {}
    domain_to_theme: dict[str, str] = {}
    for t in themes:
        tname = t["name"]
        domains = t["domains"]
        theme_to_domains[tname] = domains
        theme_to_domain_names[tname] = [d["name"] for d in domains]
        for d in domains:
            domain_to_theme[d["name"]] = tname
    return Taxonomy(
        path=TAXONOMY_PATH,
        themes=themes,
        theme_to_domains=theme_to_domains,
        theme_to_domain_names=theme_to_domain_names,
        domain_to_theme=domain_to_theme,
        global_rules=list(tax.get("global_rules") or []),
    )


def ensure_frozen_baseline() -> None:
    FROZEN.parent.mkdir(parents=True, exist_ok=True)
    if not FROZEN.exists():
        if not BASELINE.exists():
            raise SystemExit("v2.1 candidate missing")
        FROZEN.write_bytes(BASELINE.read_bytes())
        print(f"[freeze] wrote {FROZEN}")


def load_baseline_rows() -> list[dict[str, Any]]:
    src = FROZEN if FROZEN.exists() else BASELINE
    rows = load_jsonl(src)
    if len(rows) != 70298:
        print(f"[warn] baseline rows={len(rows)} (expected 70298)")
    return rows


def load_papers_map() -> dict[str, dict[str, Any]]:
    m: dict[str, dict[str, Any]] = {}
    with open(PAPERS, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            m[r["id"]] = r
    return m


def paper_text(p: dict[str, Any]) -> str:
    return f"{p.get('title') or ''}\n{p.get('abstract') or ''}"


def build_target_queue(
    v21_rows: list[dict[str, Any]],
    papers: dict[str, dict[str, Any]],
) -> tuple[list[str], dict[str, str], dict[str, Any]]:
    """High-yield queue only — gap sinks + keyword recall. Prefer quality over size."""
    scored: list[tuple[int, float, str]] = []  # (priority, conf, id) lower priority first
    why: dict[str, str] = {}
    stats = Counter()

    for r in v21_rows:
        pid = r["id"]
        p = papers.get(pid)
        if not p:
            continue
        dom = r.get("domain") or ""
        conf = r.get("confidence")
        try:
            conf_f = float(conf) if conf is not None else 0.5
        except Exception:
            conf_f = 0.5
        text = paper_text(p)
        kw_hits = [name for name, pat in KEYWORD_GROUPS if pat.search(text)]
        in_sink = dom in SINK_DOMAINS

        if not kw_hits and not in_sink:
            continue

        # Priority tiers (1=highest)
        if kw_hits and in_sink:
            pri = 1
            reason = f"sink+kw:{dom}|{','.join(kw_hits[:3])}"
        elif kw_hits:
            pri = 2
            reason = f"keyword:{','.join(kw_hits[:3])}"
        elif in_sink and conf_f < 0.8:
            pri = 3
            reason = f"sink_lowconf:{dom}"
        elif in_sink and conf_f < 0.92 and any(
            x in normalize(dom)
            for x in [
                "energy storage",
                "algorithms",
                "digital culture",
                "biomanufacturing",
                "power systems",
                "materials, joining",
                "clinical biosensor",
                "fiber photonic",
            ]
        ):
            pri = 4
            reason = f"sink_gap:{dom}"
        else:
            continue

        # Boost known gap patterns
        if "thermoelectric" in kw_hits and "energy storage" in normalize(dom):
            pri = 1
        if "architecture" in kw_hits and "algorithm" in normalize(dom):
            pri = 1
        if "mechanism_design" in kw_hits and "digital culture" in normalize(dom):
            pri = 1
        if "accelerator_rf" in kw_hits and "power systems" in normalize(dom):
            pri = 1
        if "pat_biopharma" in kw_hits and "biomanufacturing" in normalize(dom):
            pri = 1

        scored.append((pri, conf_f, pid))
        why[pid] = reason
        stats[f"pri_{pri}"] += 1
        if kw_hits:
            for h in kw_hits:
                stats[f"kw_{h}"] += 1

    scored.sort(key=lambda x: (x[0], x[1], x[2]))
    ordered = []
    seen = set()
    for _, _, pid in scored:
        if pid in seen:
            continue
        seen.add(pid)
        ordered.append(pid)

    meta = {
        "pre_cap_total": len(ordered),
        "queue_hard_cap": QUEUE_HARD_CAP,
        "priority_counts": {k: stats[k] for k in sorted(stats) if k.startswith("pri_")},
        "keyword_hits": {k: stats[k] for k in sorted(stats) if k.startswith("kw_")},
    }
    if len(ordered) > QUEUE_HARD_CAP:
        ordered = ordered[:QUEUE_HARD_CAP]
        kept = set(ordered)
        why = {k: v for k, v in why.items() if k in kept}
        meta["capped"] = True
        meta["dropped_due_hard_cap"] = meta["pre_cap_total"] - len(ordered)
    else:
        meta["capped"] = False
        meta["dropped_due_hard_cap"] = 0

    # persist queue
    with open(QUEUE_OUT, "w", encoding="utf-8") as fh:
        for pid in ordered:
            old = next((r for r in v21_rows if r["id"] == pid), None)
            # faster: use map outside — rebuild below
            fh.write(json.dumps({"id": pid, "queue_reason": why.get(pid)}, ensure_ascii=False) + "\n")
    # rewrite with domain info efficiently
    by_id = {r["id"]: r for r in v21_rows}
    with open(QUEUE_OUT, "w", encoding="utf-8") as fh:
        for pid in ordered:
            old = by_id[pid]
            fh.write(
                json.dumps(
                    {
                        "id": pid,
                        "queue_reason": why.get(pid),
                        "old_theme": old.get("thematic_area"),
                        "old_domain": old.get("domain"),
                        "old_confidence": old.get("confidence"),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
    meta["written"] = len(ordered)
    return ordered, why, meta


def estimate_tokens(text: str) -> int:
    return max(16, int(len(text) / 4))


def build_correction_system_prompt(taxonomy: Taxonomy) -> str:
    L: list[str] = []
    A = L.append
    A("You are a strict taxonomy classifier for IIT Delhi research papers.")
    A("PRIMARY MODE: theme-locked domain correction using the UPDATED v2.2 taxonomy.")
    A("Choose exactly one domain from the locked theme's allowed list.")
    A("Judge by PRIMARY scientific contribution, not incidental keywords.")
    A("")
    A("Global routing / tie-breaks (apply strictly):")
    for i, b in enumerate(taxonomy.global_rules, 1):
        A(f"{i}. {b}")
    A("")
    A("Output STRICT JSON only:")
    A('{"thematic_area": str, "domain": str, "confidence": float, "unclassifiable": bool, "reason": str}')
    A("reason <=18 words, concrete. Use unclassifiable=true ONLY with explicit out_of_scope evidence.")
    return "\n".join(L)


def build_full_reassess_system_prompt(taxonomy: Taxonomy) -> str:
    L: list[str] = []
    A = L.append
    A("You are an expert taxonomy adjudicator. Full reassessment mode.")
    A("Choose best thematic_area and one allowed domain from that theme.")
    A("Use unclassifiable only with strict out_of_scope evidence.")
    A("")
    A("Global rules:")
    for i, b in enumerate(taxonomy.global_rules, 1):
        A(f"{i}. {b}")
    A("")
    A("Taxonomy (theme -> domains):")
    for t in taxonomy.themes:
        A(f"- {t['name']}:")
        for d in t["domains"]:
            A(f"  - {d['name']}: {d.get('definition','')[:160]}")
    A("")
    A("Output STRICT JSON only:")
    A('{"thematic_area": str, "domain": str, "confidence": float, "unclassifiable": bool, "reason": str}')
    return "\n".join(L)


def build_theme_locked_user_prompt(paper, old, theme_domains) -> str:
    tname = old.get("thematic_area") or ""
    L = [
        "Classify this paper in theme-locked mode.",
        f"LOCKED_THEMATIC_AREA: {tname}",
        "Allowed domains:",
    ]
    for d in theme_domains:
        L.append(f"- {d['name']}: {d.get('definition','')[:180]}")
    L += [
        "",
        f"Current label: theme={old.get('thematic_area')} | domain={old.get('domain')} | confidence={old.get('confidence')}",
        "Paper:",
        f"Title: {paper.get('title') or ''}",
        f"Abstract: {(paper.get('abstract') or '')[:1500] or '(no abstract)'}",
        "",
        "Return JSON only.",
    ]
    return "\n".join(L)


def build_full_reassess_user_prompt(paper, old) -> str:
    return "\n".join(
        [
            "Hard-case full reassessment.",
            f"Previous label: theme={old.get('thematic_area')} | domain={old.get('domain')} | confidence={old.get('confidence')}",
            "Paper:",
            f"Title: {paper.get('title') or ''}",
            f"Abstract: {(paper.get('abstract') or '')[:1700] or '(no abstract)'}",
            "Return STRICT JSON only.",
        ]
    )


def parse_and_validate(obj, taxonomy: Taxonomy, locked_theme: str | None):
    if obj is None:
        return None, "no_object"
    theme = obj.get("thematic_area")
    domain = obj.get("domain")
    # accept renamed biosensor if model emits old name
    if domain in DOMAIN_RENAME:
        domain = DOMAIN_RENAME[domain]
    reason = obj.get("reason")
    unclass = bool(obj.get("unclassifiable", False))
    try:
        conf = float(obj.get("confidence"))
    except Exception:
        conf = None

    if locked_theme:
        theme = locked_theme
        allowed = set(taxonomy.theme_to_domain_names.get(locked_theme, []))
        if not unclass and domain not in allowed:
            return None, f"domain_not_in_locked_theme:{domain!r}"
    else:
        if not unclass:
            if theme not in taxonomy.theme_to_domain_names:
                return None, f"theme_not_in_taxonomy:{theme!r}"
            if domain not in taxonomy.theme_to_domain_names.get(theme, []):
                return None, f"domain_not_in_theme:{domain!r}"
    return {
        "thematic_area": theme,
        "domain": domain,
        "confidence": conf,
        "unclassifiable": unclass,
        "reason": reason,
    }, "ok"


def api_json_call(client, limiter, model, system_prompt, user_prompt, max_tokens=260, max_attempts=MAX_API_ATTEMPTS):
    usage_total = {"input_tokens": 0, "output_tokens": 0, "cache_write": 0, "cache_read": 0}
    err = None
    raw = ""
    stats = {"calls": 0, "rate_limit": 0, "server_5xx": 0, "timeout_conn": 0, "parse_error": 0}
    for attempt in range(max_attempts):
        est = estimate_tokens(system_prompt) + estimate_tokens(user_prompt) + max_tokens
        limiter.acquire(est)
        try:
            track_enter()
            try:
                stats["calls"] += 1
                resp = client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
                    messages=[{"role": "user", "content": user_prompt}],
                )
            finally:
                track_exit()
            u = usage_dict(resp.usage)
            add_usage(usage_total, u)
            raw = (resp.content[0].text if resp.content else "").strip()
            return parse_json_object(raw), raw, usage_total, None, stats
        except ValueError as e:
            stats["parse_error"] += 1
            err = f"parse_error:{e}"
            time.sleep(0.3 * (attempt + 1))
        except anthropic.RateLimitError as e:
            stats["rate_limit"] += 1
            err = f"rate_limit:{e}"
            time.sleep(min(30.0, (2**attempt) + random.uniform(0, 0.7)))
        except anthropic.APIStatusError as e:
            code = getattr(e, "status_code", None)
            err = f"api_status_{code}:{e}"
            if code == 429:
                stats["rate_limit"] += 1
            elif code and code >= 500:
                stats["server_5xx"] += 1
            time.sleep(min(30.0, (2**attempt) + random.uniform(0, 0.7)))
        except (anthropic.APITimeoutError, anthropic.APIConnectionError) as e:
            stats["timeout_conn"] += 1
            err = f"timeout_or_connection:{e}"
            time.sleep(min(20.0, (2**attempt) + random.uniform(0, 0.5)))
        except Exception as e:  # noqa: BLE001
            err = f"unexpected:{repr(e)}"
            time.sleep(0.5 * (attempt + 1))
    return None, raw, usage_total, err, stats


def probe_model(client, model):
    try:
        resp = client.messages.create(model=model, max_tokens=1, messages=[{"role": "user", "content": "Reply with token ok"}])
        u = usage_dict(resp.usage)
        return {"model": model, "resolved": True, "usage": u, "cost_usd": round(cost_from_usage(model, u), 6)}
    except Exception as e:  # noqa: BLE001
        return {"model": model, "resolved": False, "error": repr(e)}


def summarize_targeted_output(path: Path) -> dict[str, Any]:
    rows = 0
    ids = set()
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_write": 0, "cache_read": 0}
    cost = 0.0
    if not path.exists():
        return {"rows": 0, "unique_ids": 0, "usage": usage, "cost_usd": 0.0}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            rows += 1
            ids.add(r["id"])
            u = r.get("usage")
            m = r.get("model")
            if u and m in PRICING:
                for k in usage:
                    usage[k] += int(u.get(k, 0))
                cost += cost_from_usage(m, u)
    return {"rows": rows, "unique_ids": len(ids), "usage": usage, "cost_usd": round(cost, 4)}


def load_done_ids(path: Path) -> set[str]:
    done = set()
    if not path.exists():
        return done
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                done.add(json.loads(line)["id"])
            except Exception:
                continue
    return done


def run_correction_chunk(
    *,
    client,
    limiter,
    model,
    taxonomy,
    system_primary,
    system_full,
    chunk_ids,
    v21_by_id,
    papers,
    queue_why,
    workers,
    chunk_label,
    cost_stop_usd,
):
    lock = threading.Lock()
    fh = open(TARGETED_OUT, "a", encoding="utf-8")
    stats = Counter()
    phase_usage = {"input_tokens": 0, "output_tokens": 0, "cache_write": 0, "cache_read": 0}
    t0 = time.time()
    written = 0
    stop_flag = threading.Event()

    def classify_one(pid: str) -> dict[str, Any] | None:
        if stop_flag.is_set():
            return None
        old = v21_by_id[pid]
        paper = papers[pid]
        allowed = taxonomy.theme_to_domains.get(old.get("thematic_area"), [])
        usage_total = {"input_tokens": 0, "output_tokens": 0, "cache_write": 0, "cache_read": 0}
        api_stats_total = Counter()

        obj1, raw1, usage1, err1, st1 = api_json_call(
            client, limiter, model, system_primary, build_theme_locked_user_prompt(paper, old, allowed), 260
        )
        add_usage(usage_total, usage1)
        api_stats_total.update(st1)
        p1, p1_note = parse_and_validate(obj1, taxonomy, old.get("thematic_area"))
        chosen = p1
        pass_mode = "theme_locked"
        schema_note = p1_note if p1 is None else "ok"

        need_secondary = (
            chosen is None
            or chosen.get("confidence") is None
            or (chosen.get("confidence") or 0.0) < 0.45
            or (chosen.get("unclassifiable") and not out_of_scope_evidence(chosen.get("reason")))
            or queue_why.get(pid, "").startswith("keyword:")
            or "accelerator_rf" in queue_why.get(pid, "")
            or "mechanism_design" in queue_why.get(pid, "")
            or "fuel_additive" in queue_why.get(pid, "")
            or "pat_biopharma" in queue_why.get(pid, "")
        )
        # always full-reassess for theme-suspect keyword cases
        if need_secondary and not stop_flag.is_set():
            obj2, raw2, usage2, err2, st2 = api_json_call(
                client, limiter, model, system_full, build_full_reassess_user_prompt(paper, old), 320
            )
            add_usage(usage_total, usage2)
            api_stats_total.update(st2)
            p2, p2_note = parse_and_validate(obj2, taxonomy, None)
            if p2 is not None:
                p1c = p1.get("confidence") if p1 else None
                p2c = p2.get("confidence")
                if p1 is None or (p2c is not None and (p1c is None or p2c >= (p1c or 0) + 0.03)):
                    chosen = p2
                    pass_mode = "full_reassess"
                    schema_note = p2_note
            elif chosen is None:
                schema_note = p2_note

        if chosen is None:
            chosen = {
                "thematic_area": old.get("thematic_area"),
                "domain": DOMAIN_RENAME.get(old.get("domain"), old.get("domain")),
                "confidence": old.get("confidence"),
                "unclassifiable": bool(old.get("unclassifiable")),
                "reason": f"api_failure_keep_old:{err1}"[:300],
            }
            pass_mode = "fallback_keep_old"

        return {
            "id": pid,
            "old_theme": old.get("thematic_area"),
            "old_domain": old.get("domain"),
            "old_confidence": old.get("confidence"),
            "new_theme": chosen.get("thematic_area"),
            "new_domain": chosen.get("domain"),
            "new_confidence": chosen.get("confidence"),
            "changed_theme": chosen.get("thematic_area") != old.get("thematic_area"),
            "changed_domain": chosen.get("domain") != DOMAIN_RENAME.get(old.get("domain"), old.get("domain")),
            "unclassifiable": bool(chosen.get("unclassifiable")),
            "reason": chosen.get("reason"),
            "model": model,
            "usage": usage_total,
            "pass_mode": pass_mode,
            "queue_reason": queue_why.get(pid),
            "schema_note": schema_note,
            "updated": now_ts(),
            "api_stats": dict(api_stats_total),
        }

    ex = ThreadPoolExecutor(max_workers=workers)
    futs = {ex.submit(classify_one, pid): pid for pid in chunk_ids}
    since = 0
    try:
        for fut in as_completed(futs):
            pid = futs[fut]
            try:
                rec = fut.result()
            except Exception as e:  # noqa: BLE001
                old = v21_by_id[pid]
                rec = {
                    "id": pid,
                    "old_theme": old.get("thematic_area"),
                    "old_domain": old.get("domain"),
                    "old_confidence": old.get("confidence"),
                    "new_theme": old.get("thematic_area"),
                    "new_domain": DOMAIN_RENAME.get(old.get("domain"), old.get("domain")),
                    "new_confidence": old.get("confidence"),
                    "changed_theme": False,
                    "changed_domain": False,
                    "unclassifiable": bool(old.get("unclassifiable")),
                    "reason": f"worker_exception_keep_old:{repr(e)}"[:300],
                    "model": model,
                    "usage": {"input_tokens": 0, "output_tokens": 0, "cache_write": 0, "cache_read": 0},
                    "pass_mode": "worker_exception_fallback",
                    "queue_reason": queue_why.get(pid),
                    "schema_note": "worker_exception",
                    "updated": now_ts(),
                    "api_stats": {},
                }
                stats["worker_exceptions"] += 1

            if rec is None:
                stats["skipped_cost_stop"] += 1
                continue

            with lock:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            written += 1
            since += 1
            stats["rows_written"] += 1
            if rec.get("changed_domain"):
                stats["changed_domain_raw"] += 1
            if rec.get("changed_theme"):
                stats["changed_theme_raw"] += 1
            if rec.get("pass_mode") == "full_reassess":
                stats["full_reassess_calls"] += 1
            api_stats = rec.get("api_stats") or {}
            stats["api_calls"] += int(api_stats.get("calls", 0))
            stats["rate_limit"] += int(api_stats.get("rate_limit", 0))
            stats["server_5xx"] += int(api_stats.get("server_5xx", 0))
            stats["timeout_conn"] += int(api_stats.get("timeout_conn", 0))
            add_usage(phase_usage, rec.get("usage", {}))

            if since >= CHECKPOINT_EVERY:
                since = 0
                fh.flush()
                os.fsync(fh.fileno())
                # live cost check vs already-written + this phase
                live = summarize_targeted_output(TARGETED_OUT)
                if live["cost_usd"] >= cost_stop_usd:
                    print(f"[cost-stop] correction soft stop ${live['cost_usd']:.2f} >= ${cost_stop_usd:.2f}")
                    stop_flag.set()

            if stop_flag.is_set() and since % 50 == 0:
                pass
    finally:
        ex.shutdown(wait=True, cancel_futures=True)
        fh.flush()
        os.fsync(fh.fileno())
        fh.close()

    elapsed = max(time.time() - t0, 1e-6)
    stats["elapsed_sec"] = round(elapsed, 2)
    stats["workers"] = workers
    stats["chunk_size"] = len(chunk_ids)
    stats["rows_written"] = written
    stats["rows_per_sec"] = round(written / elapsed, 2)
    stats["chunk_label"] = chunk_label
    stats["phase_usage"] = phase_usage
    stats["phase_cost_usd"] = round(cost_from_usage(model, phase_usage), 4)
    stats["peak_parallel_observed"] = _PEAK_PARALLEL
    stats["cost_stop_triggered"] = stop_flag.is_set()
    return dict(stats)


def accept_candidate(old, new) -> tuple[bool, str]:
    old_theme = old.get("thematic_area")
    old_domain = DOMAIN_RENAME.get(old.get("domain"), old.get("domain"))
    try:
        old_conf_f = float(old.get("confidence")) if old.get("confidence") is not None else None
    except Exception:
        old_conf_f = None
    new_theme = new.get("new_theme")
    new_domain = new.get("new_domain")
    try:
        new_conf_f = float(new.get("new_confidence")) if new.get("new_confidence") is not None else None
    except Exception:
        new_conf_f = None
    new_unclass = bool(new.get("unclassifiable"))
    reason = new.get("reason")

    if new_unclass:
        if out_of_scope_evidence(reason) and (new_conf_f is None or new_conf_f >= 0.65):
            # reject spam: don't convert high-conf good labels to unclass without strong evidence
            if old_conf_f is not None and old_conf_f >= 0.85 and (new_conf_f or 0) < 0.8:
                return False, "reject_unclass_high_old_conf"
            return True, "accept_unclass_oos_evidence"
        return False, "reject_unclass_weak_evidence"

    if new_theme != old_theme:
        # theme change: stricter, but allow gap-fill domains with high confidence
        if new_domain in GAP_FILL_DOMAINS and new_conf_f is not None and new_conf_f >= 0.75:
            if old_conf_f is None or old_conf_f <= 0.85 or new_conf_f >= old_conf_f + 0.05:
                return True, "accept_theme_change_gapfill"
        if (old_conf_f is not None and old_conf_f < 0.55) and (new_conf_f is not None and new_conf_f >= 0.8):
            return True, "accept_theme_change_low_old_high_new"
        return False, "reject_theme_change_threshold"

    if new_domain != old_domain:
        # prefer gap-fill domain moves within theme
        if new_domain in GAP_FILL_DOMAINS and new_conf_f is not None and new_conf_f >= 0.6:
            return True, "accept_domain_gapfill"
        if new_conf_f is not None and old_conf_f is not None and new_conf_f >= old_conf_f:
            return True, "accept_domain_conf_nonregression"
        if tie_break_reason(reason) and new_conf_f is not None and (old_conf_f is None or new_conf_f >= max(0.55, old_conf_f - 0.1)):
            return True, "accept_domain_tiebreak_reason"
        return False, "reject_domain_change_weak"

    return False, "reject_no_label_change"


def merge_candidate(v21_rows, targeted_by_id):
    merged = []
    stats = Counter()
    for old in v21_rows:
        pid = old["id"]
        base = dict(old)
        # identity rename for taxonomy continuity
        if base.get("domain") in DOMAIN_RENAME:
            base["domain"] = DOMAIN_RENAME[base["domain"]]
            stats["identity_rename_biosensor"] += 1

        new = targeted_by_id.get(pid)
        if new is None:
            merged.append(base)
            stats["kept_no_targeted_row"] += 1
            continue
        accept, rule = accept_candidate(old, new)
        if not accept:
            merged.append(base)
            stats[f"kept_{rule}"] += 1
            continue
        rec = dict(base)
        rec["thematic_area"] = new.get("new_theme")
        rec["domain"] = new.get("new_domain")
        rec["confidence"] = new.get("new_confidence")
        rec["unclassifiable"] = bool(new.get("unclassifiable"))
        rec["reason"] = new.get("reason")
        rec["source_model"] = "sonnet_v2_2_targeted"
        rec["escalated"] = True
        merged.append(rec)
        stats["accepted_total"] += 1
        if rec["thematic_area"] != old.get("thematic_area"):
            stats["accepted_theme_change"] += 1
        if rec["domain"] != DOMAIN_RENAME.get(old.get("domain"), old.get("domain")):
            stats["accepted_domain_change"] += 1
        if rec["unclassifiable"] != bool(old.get("unclassifiable")):
            stats["accepted_unclass_change"] += 1
        stats[f"accepted_{rule}"] += 1
    return merged, dict(stats)


def stratified_sample(rows, n, rng, strata_key):
    if n >= len(rows):
        out = rows[:]
        rng.shuffle(out)
        return out
    groups = defaultdict(list)
    for r in rows:
        groups[strata_key(r)].append(r)
    keys = list(groups.keys())
    total = len(rows)
    alloc = {}
    rem = []
    assigned = 0
    for k in keys:
        exact = n * (len(groups[k]) / total)
        base = min(len(groups[k]), int(math.floor(exact)))
        alloc[k] = base
        assigned += base
        rem.append((exact - base, k))
    remaining = n - assigned
    rem.sort(reverse=True, key=lambda x: x[0])
    for _, k in rem:
        if remaining <= 0:
            break
        if alloc[k] < len(groups[k]):
            alloc[k] += 1
            remaining -= 1
    out = []
    for k, g in groups.items():
        rng.shuffle(g)
        out.extend(g[: alloc[k]])
    rng.shuffle(out)
    if len(out) < n:
        seen = {r["id"] for r in out}
        rest = [r for r in rows if r["id"] not in seen]
        rng.shuffle(rest)
        out.extend(rest[: n - len(out)])
    return out[:n]


def build_judge_system_prompt(taxonomy: Taxonomy) -> str:
    L = [
        "You are an independent blind A/B judge for taxonomy labels.",
        "Decide which label better matches the paper's primary scientific contribution.",
        "Prefer tie if both labels are similarly defensible.",
        "Unclassifiable is valid only with explicit out_of_scope/no-signal evidence.",
        "",
        "Taxonomy themes/domains:",
    ]
    for t in taxonomy.themes:
        L.append(f"- {t['name']}:")
        for d in t["domains"]:
            L.append(f"  - {d['name']}")
    L.append("")
    L.append('JSON: {"winner":"A|B|tie","theme_winner":"A|B|tie","domain_winner":"A|B|tie","confidence":"high|medium|low","rationale":"<=30 words"}')
    return "\n".join(L)


def run_validation_judging(*, client, limiter, judge_model, judge_system_prompt, sample_rows, v21_by_id, v22_by_id, papers):
    existing = {}
    if VALIDATION_JSONL.exists():
        for r in load_jsonl(VALIDATION_JSONL):
            existing[r["id"]] = r
    todo = [r for r in sample_rows if r["id"] not in existing]
    fh = open(VALIDATION_JSONL, "a", encoding="utf-8")
    lock = threading.Lock()
    stats = Counter()
    usage_total = {"input_tokens": 0, "output_tokens": 0, "cache_write": 0, "cache_read": 0}

    def judge_one(s):
        pid = s["id"]
        old = v21_by_id[pid]
        new = v22_by_id[pid]
        # normalize rename for fair compare
        old_cmp = dict(old)
        if old_cmp.get("domain") in DOMAIN_RENAME:
            old_cmp["domain"] = DOMAIN_RENAME[old_cmp["domain"]]
        p = papers[pid]
        order_flip = random.Random(f"{VALIDATION_SEED}-{pid}").random() < 0.5
        if order_flip:
            A_lab, B_lab = new, old_cmp
            map_ab = {"A": "v2_2", "B": "v2_1"}
        else:
            A_lab, B_lab = old_cmp, new
            map_ab = {"A": "v2_1", "B": "v2_2"}

        def lab_txt(x):
            return (
                f"theme={x.get('thematic_area')}; domain={x.get('domain')}; "
                f"confidence={x.get('confidence')}; unclassifiable={bool(x.get('unclassifiable'))}"
            )

        user_prompt = "\n".join(
            [
                "Paper:",
                f"Title: {p.get('title') or ''}",
                f"Abstract: {(p.get('abstract') or '')[:1500] or '(no abstract)'}",
                "",
                f"Label A: {lab_txt(A_lab)}",
                f"Label B: {lab_txt(B_lab)}",
                "Return strict JSON only.",
            ]
        )
        obj, raw, usage, err, call_stats = api_json_call(client, limiter, judge_model, judge_system_prompt, user_prompt, 200, 5)
        decision = {"winner": "tie", "theme_winner": "tie", "domain_winner": "tie", "confidence": "low", "rationale": "judge_failed"}
        if obj is not None:
            for k in ("winner", "theme_winner", "domain_winner"):
                v = str(obj.get(k, "tie")).strip()
                decision[k] = v if v in ("A", "B", "tie") else "tie"
            conf = str(obj.get("confidence", "low")).strip().lower()
            decision["confidence"] = conf if conf in ("high", "medium", "low") else "low"
            decision["rationale"] = str(obj.get("rationale") or "")[:300]
        elif err:
            decision["rationale"] = f"judge_error:{err}"[:300]

        mapped = {k: (map_ab.get(decision[k], "tie") if decision[k] != "tie" else "tie") for k in ("winner", "theme_winner", "domain_winner")}
        return {
            "id": pid,
            "changed": s["changed"],
            "band": s["band"],
            "theme_bucket": s["theme_bucket"],
            "order_flip": order_flip,
            "winner": mapped["winner"],
            "theme_winner": mapped["theme_winner"],
            "domain_winner": mapped["domain_winner"],
            "judge_confidence": decision["confidence"],
            "rationale": decision["rationale"],
            "judge_model": judge_model,
            "usage": usage,
            "judge_calls": call_stats,
            "updated": now_ts(),
        }

    ex = ThreadPoolExecutor(max_workers=30)
    futs = {ex.submit(judge_one, s): s for s in todo}
    try:
        for fut in as_completed(futs):
            rec = fut.result()
            with lock:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            stats["rows_written"] += 1
            add_usage(usage_total, rec.get("usage", {}))
            jc = rec.get("judge_calls") or {}
            stats["api_calls"] += int(jc.get("calls", 0))
            stats["rate_limit"] += int(jc.get("rate_limit", 0))
    finally:
        ex.shutdown(wait=True, cancel_futures=True)
        fh.flush()
        os.fsync(fh.fileno())
        fh.close()

    all_rows = load_jsonl(VALIDATION_JSONL)
    chosen = {r["id"] for r in sample_rows}
    judged = [r for r in all_rows if r["id"] in chosen]
    stats["usage"] = usage_total
    stats["cost_usd_new_rows"] = round(cost_from_usage(judge_model, usage_total), 4)
    return judged, dict(stats)


def compute_validation_summary(judged):
    win = Counter(r.get("winner") for r in judged)
    theme = Counter(r.get("theme_winner") for r in judged)
    domain = Counter(r.get("domain_winner") for r in judged)
    n_comp = win.get("v2_2", 0) + win.get("v2_1", 0)
    net_margin = win.get("v2_2", 0) - win.get("v2_1", 0)
    changed = [r for r in judged if r.get("changed")]
    cwin = Counter(r.get("winner") for r in changed)
    c_non = cwin.get("v2_2", 0) + cwin.get("v2_1", 0)
    return {
        "n_judged": len(judged),
        "overall_wins": dict(win),
        "theme_wins": dict(theme),
        "domain_wins": dict(domain),
        "n_non_tie": n_comp,
        "net_margin_v2_2_minus_v2_1": net_margin,
        "v2_2_win_rate_non_tie_pct": round((win.get("v2_2", 0) / n_comp) * 100, 2) if n_comp else None,
        "theme_non_regression": theme.get("v2_2", 0) >= theme.get("v2_1", 0),
        "domain_improvement_signal": domain.get("v2_2", 0) > domain.get("v2_1", 0),
        "changed_subset": {
            "n": len(changed),
            "wins": dict(cwin),
            "n_non_tie": c_non,
            "net_margin": cwin.get("v2_2", 0) - cwin.get("v2_1", 0),
        },
    }


def top_changed_patterns(judged, v21_by_id, v22_by_id):
    win = Counter()
    lose = Counter()
    for r in judged:
        if not r.get("changed"):
            continue
        pid = r["id"]
        old = v21_by_id[pid]
        new = v22_by_id[pid]
        od = DOMAIN_RENAME.get(old.get("domain"), old.get("domain"))
        key = f"{old.get('thematic_area')} / {od} -> {new.get('thematic_area')} / {new.get('domain')}"
        if r.get("winner") == "v2_2":
            win[key] += 1
        elif r.get("winner") == "v2_1":
            lose[key] += 1
    return {
        "improved_patterns": [{"pattern": k, "count": v} for k, v in win.most_common(10)],
        "regressed_patterns": [{"pattern": k, "count": v} for k, v in lose.most_common(10)],
    }


def write_validation_md(judged, sample_rows, summary, judge_model, judge_is_independent, patterns, v21_by_id, v22_by_id):
    sample_map = {r["id"]: r for r in sample_rows}
    judged = sorted(judged, key=lambda x: x["id"])
    L = [
        "# v2.2 Random-Subset Validation (Blind A/B)\n",
        f"- Sample size judged: **{summary['n_judged']}** (seed `{VALIDATION_SEED}`).",
        f"- Judge model: **{judge_model}** (independent={judge_is_independent}).",
        f"- Overall: v2_2={summary['overall_wins'].get('v2_2',0)}, v2_1={summary['overall_wins'].get('v2_1',0)}, tie={summary['overall_wins'].get('tie',0)}.",
        f"- Net margin (v2_2 - v2_1): **{summary['net_margin_v2_2_minus_v2_1']}** on {summary['n_non_tie']} non-ties.",
        f"- Theme non-regression: **{'PASS' if summary['theme_non_regression'] else 'FAIL'}**.",
        f"- Domain improvement signal: **{'PASS' if summary['domain_improvement_signal'] else 'FAIL'}**.",
        f"- Changed subset net margin: **{summary['changed_subset']['net_margin']}** (n={summary['changed_subset']['n']}).\n",
        "## Top v2.2 wins (changed)",
    ]
    for p in patterns["improved_patterns"][:8]:
        L.append(f"- {p['count']}x: {p['pattern']}")
    L.append("## Top v2.2 losses (changed)")
    for p in patterns["regressed_patterns"][:8]:
        L.append(f"- {p['count']}x: {p['pattern']}")
    L += ["", "## Per-paper adjudication", "", "| # | id | changed | v2.1 domain | v2.2 domain | winner | rationale |", "|---:|---|---|---|---|---|---|"]
    for i, r in enumerate(judged, 1):
        pid = r["id"]
        old = v21_by_id[pid]
        new = v22_by_id[pid]
        od = DOMAIN_RENAME.get(old.get("domain"), old.get("domain"))
        rat = (r.get("rationale") or "").replace("|", "\\|").replace("\n", " ")
        L.append(f"| {i} | {pid} | {sample_map[pid]['changed']} | {od} | {new.get('domain')} | {r.get('winner')} | {rat} |")
    VALIDATION_MD.write_text("\n".join(L), encoding="utf-8")


def write_audit50_md(sample_rows, judged_by_id, papers, v21_by_id, v22_by_id):
    rng = random.Random(AUDIT50_SEED)
    rows = sample_rows[:]
    rng.shuffle(rows)
    picks = rows[:50]
    L = [
        f"# Random 50-Paper Audit — v2.2 (Seed: {AUDIT50_SEED})\n",
        "| # | id | title | v2.1 domain | v2.2 domain | winner | rationale |",
        "|---:|---|---|---|---|---|---|",
    ]
    for i, s in enumerate(picks, 1):
        pid = s["id"]
        j = judged_by_id.get(pid, {})
        p = papers.get(pid, {})
        title = (p.get("title") or "").replace("|", "\\|").replace("\n", " ")
        if len(title) > 90:
            title = title[:87] + "..."
        od = DOMAIN_RENAME.get(v21_by_id[pid].get("domain"), v21_by_id[pid].get("domain"))
        L.append(
            f"| {i} | {pid} | {title} | {od} | {v22_by_id[pid].get('domain')} | {j.get('winner','tie')} | {(j.get('rationale') or '').replace('|','\\|').replace(chr(10),' ')} |"
        )
    AUDIT50_MD.write_text("\n".join(L), encoding="utf-8")


def write_run_report(**kw):
    L = [
        "# v2.2 Overnight Run Report (for owner)\n",
        "## Bottom line\n",
        f"- **Accepted?** {kw['decision']['accepted']}",
        f"- **Recommended file:** `{kw['decision']['recommended_file']}`",
        f"- **Papers updated (accepted domain/theme/unclass changes):** {kw['acceptance_stats'].get('accepted_total', 0)}",
        f"- **Total spend:** ${kw['spent']['total']:.2f} / ${TOTAL_BUDGET_USD:.2f} hard cap",
        "",
        "## What we did\n",
        "- Closed taxonomy gaps (thermoelectric, optical metrology, implant bioelectronics sharpening, computer architecture) plus explicit out_of_scope routing for accelerator RF and fuel-additive screening.",
        "- Re-labeled ONLY a high-yield affected queue (not all 70k).",
        "- Conservative acceptance gate; rejected weak changes.",
        "",
        "## Concurrency / speed\n",
        f"- Configured workers: start={START_WORKERS}, ramp={RAMP_WORKERS}, max={MAX_WORKERS}",
        f"- Peak observed parallel in-flight API calls: **{kw['peak_parallel']}**",
        f"- Phase plan / workers used: {kw['workers_used']}",
        f"- Budget soft-stop for correction: ${CORRECTION_SOFT_STOP:.2f}; triggered={kw['budget_stop_worked']}",
        "",
        "## Queue\n",
        f"- Queue size: **{kw['queue_meta'].get('written')}** (pre-cap {kw['queue_meta'].get('pre_cap_total')})",
        f"- Priority counts: {kw['queue_meta'].get('priority_counts')}",
        f"- Keyword hits: {kw['queue_meta'].get('keyword_hits')}",
        "",
        "## Correction\n",
        f"- Model: **{kw['correction_model']}**",
        f"- Targeted rows written: **{kw['targeted_summary']['unique_ids']}**",
        f"- Correction spend: **${kw['spent']['correction']:.2f}**",
        "",
        "## Acceptance\n",
        f"- Accepted total: **{kw['acceptance_stats'].get('accepted_total',0)}**",
        f"- Domain changes: **{kw['acceptance_stats'].get('accepted_domain_change',0)}**",
        f"- Theme changes: **{kw['acceptance_stats'].get('accepted_theme_change',0)}**",
        f"- Unclass conversions: **{kw['acceptance_stats'].get('accepted_unclass_change',0)}**",
        f"- Identity rename (biosensor domain): **{kw['acceptance_stats'].get('identity_rename_biosensor',0)}**",
        "",
        "## Validation (honest)\n",
        f"- Judge: **{kw['judge_model']}**",
        f"- Overall wins: v2_2={kw['validation_summary']['overall_wins'].get('v2_2',0)} vs v2_1={kw['validation_summary']['overall_wins'].get('v2_1',0)} (ties={kw['validation_summary']['overall_wins'].get('tie',0)})",
        f"- Net margin: **{kw['validation_summary']['net_margin_v2_2_minus_v2_1']}**",
        f"- Theme non-regression: **{'PASS' if kw['validation_summary']['theme_non_regression'] else 'FAIL'}**",
        f"- Domain signal: **{'PASS' if kw['validation_summary']['domain_improvement_signal'] else 'FAIL'}**",
        f"- Changed-subset net margin: **{kw['validation_summary']['changed_subset']['net_margin']}**",
        f"- Decision reason: {kw['decision']['reason']}",
        "",
        "## What improved / what didn't\n",
        "### Improved patterns",
    ]
    for p in kw["patterns"]["improved_patterns"][:6]:
        L.append(f"- {p['count']}x {p['pattern']}")
    L.append("### Regressed patterns")
    for p in kw["patterns"]["regressed_patterns"][:6]:
        L.append(f"- {p['count']}x {p['pattern']}")
    L += [
        "",
        "## Cost breakdown\n",
        f"- Correction: ${kw['spent']['correction']:.2f}",
        f"- Validation: ${kw['spent']['validation']:.2f}",
        f"- Verify/probe: ${kw['spent']['verify']:.2f}",
        f"- **Total: ${kw['spent']['total']:.2f}** (hard cap ${TOTAL_BUDGET_USD:.2f}; correction soft-stop ${CORRECTION_SOFT_STOP:.2f})",
        f"- Budget stop worked: **{kw['budget_stop_worked']}**",
        "",
        "## What to tell the team\n",
        kw["team_blurb"],
        "",
        "## Artifacts\n",
        f"- `{CANDIDATE_OUT}`",
        f"- `{TAXONOMY_PATH}`",
        f"- `{QUEUE_OUT}`",
        f"- `{TARGETED_OUT}`",
        f"- `{COST_OUT}`",
        f"- `{VALIDATION_MD}`",
        f"- `{AUDIT50_MD}`",
        f"- Frozen baseline: `{FROZEN}`",
    ]
    RUN_REPORT_MD.write_text("\n".join(L), encoding="utf-8")


def main() -> None:
    load_dotenv(ROOT / ".env")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY missing")

    # Stage 1 if needed
    if not TAXONOMY_PATH.exists():
        from v22_build_taxonomy import main as build_tax

        build_tax()

    ensure_frozen_baseline()
    taxonomy = read_taxonomy()

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=120.0, max_retries=0)
    limiter = RateLimiter(RPM_LIMIT, TPM_LIMIT)

    v21_rows = load_baseline_rows()
    v21_by_id = {r["id"]: r for r in v21_rows}
    papers = load_papers_map()

    # Stage 2 queue (reuse if exists and non-empty unless FORCE)
    if QUEUE_OUT.exists() and QUEUE_OUT.stat().st_size > 0 and not os.environ.get("V22_REBUILD_QUEUE"):
        qrows = load_jsonl(QUEUE_OUT)
        queue_ids = [r["id"] for r in qrows]
        queue_why = {r["id"]: r.get("queue_reason", "") for r in qrows}
        queue_meta = {"written": len(queue_ids), "pre_cap_total": len(queue_ids), "reused": True}
        print(f"[queue] resumed existing queue n={len(queue_ids)}")
    else:
        queue_ids, queue_why, queue_meta = build_target_queue(v21_rows, papers)
        print(f"[queue] built n={len(queue_ids)} meta={queue_meta}")

    # probe models
    probes = []
    for m in dict.fromkeys(CORRECTION_MODEL_CANDIDATES + JUDGE_MODEL_CANDIDATES):
        probes.append(probe_model(client, m))
    corr = next((p for p in probes if p["model"] in CORRECTION_MODEL_CANDIDATES and p["resolved"]), None)
    if corr is None:
        raise SystemExit("Sonnet model not resolved")
    correction_model = corr["model"]
    judge = None
    for m in JUDGE_MODEL_CANDIDATES:
        hit = next((p for p in probes if p["model"] == m and p["resolved"]), None)
        if hit and m != correction_model:
            judge = hit
            break
    if judge is None:
        judge = corr
    judge_model = judge["model"]
    verify_spend = sum(p.get("cost_usd", 0.0) for p in probes if p.get("resolved"))

    system_primary = build_correction_system_prompt(taxonomy)
    system_full = build_full_reassess_system_prompt(taxonomy)

    correction_phases = []
    workers_used = []
    budget_stop_worked = False

    already = summarize_targeted_output(TARGETED_OUT)
    print(f"[resume] targeted already unique_ids={already['unique_ids']} cost=${already['cost_usd']:.4f}")

    done = load_done_ids(TARGETED_OUT)
    pending = [pid for pid in queue_ids if pid not in done]

    # Pilot if no cost estimate yet
    avg_cost = (already["cost_usd"] / already["unique_ids"]) if already["unique_ids"] else None
    if avg_cost is None and pending:
        pilot_ids = pending[: min(PILOT_ROWS, len(pending))]
        pstats = run_correction_chunk(
            client=client,
            limiter=limiter,
            model=correction_model,
            taxonomy=taxonomy,
            system_primary=system_primary,
            system_full=system_full,
            chunk_ids=pilot_ids,
            v21_by_id=v21_by_id,
            papers=papers,
            queue_why=queue_why,
            workers=PILOT_WORKERS,
            chunk_label="pilot_cost_estimation",
            cost_stop_usd=CORRECTION_SOFT_STOP,
        )
        correction_phases.append(pstats)
        workers_used.append(PILOT_WORKERS)
        already = summarize_targeted_output(TARGETED_OUT)
        avg_cost = (already["cost_usd"] / max(already["unique_ids"], 1)) if already["unique_ids"] else 0.01
        done = load_done_ids(TARGETED_OUT)
        pending = [pid for pid in queue_ids if pid not in done]
        if already["cost_usd"] >= CORRECTION_SOFT_STOP:
            budget_stop_worked = True
            pending = []

    if avg_cost is None or avg_cost <= 0:
        avg_cost = 0.008

    remaining_budget = max(0.0, CORRECTION_SOFT_STOP - already["cost_usd"])
    est_more = int(max(0, math.floor(remaining_budget / avg_cost)))
    if len(pending) > est_more:
        print(f"[queue] budget trim pending {len(pending)} -> {est_more} (avg=${avg_cost:.5f})")
        pending = pending[:est_more]
        budget_stop_worked = True

    queue_meta["avg_cost_per_row_usd"] = round(avg_cost, 6)
    queue_meta["estimated_additional_under_budget"] = est_more
    queue_meta["taxonomy_path"] = str(TAXONOMY_PATH)

    phase_plan = [
        ("phase_start_50", START_WORKERS, 2000),
        ("phase_ramp_65", RAMP_WORKERS, 3000),
        ("phase_max_80", MAX_WORKERS, None),
    ]
    for label, workers, chunk_n in phase_plan:
        if not pending:
            break
        live = summarize_targeted_output(TARGETED_OUT)
        if live["cost_usd"] >= CORRECTION_SOFT_STOP:
            print(f"[cost-stop] before {label}: ${live['cost_usd']:.2f}")
            budget_stop_worked = True
            break
        chunk = pending if chunk_n is None else pending[: min(chunk_n, len(pending))]
        pstats = run_correction_chunk(
            client=client,
            limiter=limiter,
            model=correction_model,
            taxonomy=taxonomy,
            system_primary=system_primary,
            system_full=system_full,
            chunk_ids=chunk,
            v21_by_id=v21_by_id,
            papers=papers,
            queue_why=queue_why,
            workers=workers,
            chunk_label=label,
            cost_stop_usd=CORRECTION_SOFT_STOP,
        )
        correction_phases.append(pstats)
        workers_used.append(workers)
        if pstats.get("cost_stop_triggered"):
            budget_stop_worked = True
        pending = pending[len(chunk) :]
        live = summarize_targeted_output(TARGETED_OUT)
        if live["cost_usd"] >= CORRECTION_SOFT_STOP:
            budget_stop_worked = True
            print(f"[cost-stop] after {label}: ${live['cost_usd']:.2f}")
            break
        calls = max(1, int(pstats.get("api_calls", 0)))
        rl = pstats.get("rate_limit", 0) / calls
        sx = pstats.get("server_5xx", 0) / calls
        if rl > PHASE_429_OK or sx > PHASE_5XX_OK:
            print(f"[ramp] elevated errors 429={rl:.2%} 5xx={sx:.2%}; holding workers={workers}")
            if pending and live["cost_usd"] < CORRECTION_SOFT_STOP:
                extra = run_correction_chunk(
                    client=client,
                    limiter=limiter,
                    model=correction_model,
                    taxonomy=taxonomy,
                    system_primary=system_primary,
                    system_full=system_full,
                    chunk_ids=pending[:],
                    v21_by_id=v21_by_id,
                    papers=papers,
                    queue_why=queue_why,
                    workers=workers,
                    chunk_label=f"{label}_hold",
                    cost_stop_usd=CORRECTION_SOFT_STOP,
                )
                correction_phases.append(extra)
                workers_used.append(workers)
                if extra.get("cost_stop_triggered"):
                    budget_stop_worked = True
                pending = []
            break

    targeted_summary = summarize_targeted_output(TARGETED_OUT)
    if targeted_summary["cost_usd"] >= CORRECTION_SOFT_STOP:
        budget_stop_worked = True

    # latest targeted map
    targeted_latest = {}
    for r in load_jsonl(TARGETED_OUT):
        targeted_latest[r["id"]] = r

    merged_rows, acceptance_stats = merge_candidate(v21_rows, targeted_latest)
    write_jsonl(CANDIDATE_OUT, merged_rows)
    v22_by_id = {r["id"]: r for r in merged_rows}

    # Stage 4 validation
    frame = []
    for old in v21_rows:
        pid = old["id"]
        if pid not in papers:
            continue
        new = v22_by_id[pid]
        od = DOMAIN_RENAME.get(old.get("domain"), old.get("domain"))
        changed = (
            old.get("thematic_area") != new.get("thematic_area")
            or od != new.get("domain")
            or bool(old.get("unclassifiable")) != bool(new.get("unclassifiable"))
        )
        frame.append(
            {
                "id": pid,
                "changed": changed,
                "band": band_of(old.get("confidence")),
                "theme_bucket": old.get("thematic_area") or "UNCLASSIFIABLE",
            }
        )
    changed_rows = [r for r in frame if r["changed"]]
    unchanged_rows = [r for r in frame if not r["changed"]]
    rng = random.Random(VALIDATION_SEED)
    changed_target = min(len(changed_rows), max(70, int(VALIDATION_SAMPLE_N * 0.55)))
    unchanged_target = max(0, VALIDATION_SAMPLE_N - changed_target)
    sampled = stratified_sample(changed_rows, changed_target, rng, lambda x: (x["band"], x["theme_bucket"])) + stratified_sample(
        unchanged_rows, unchanged_target, rng, lambda x: (x["band"], x["theme_bucket"])
    )
    sampled = stratified_sample(sampled, min(VALIDATION_SAMPLE_N, len(sampled)), rng, lambda x: (x["changed"], x["band"], x["theme_bucket"]))

    # trim validation if budget tight
    corr_spend_now = targeted_summary["cost_usd"]
    val_room = max(0.0, TOTAL_BUDGET_USD - corr_spend_now - verify_spend)
    if val_room < 3.0 and len(sampled) > 80:
        sampled = sampled[:80]
        print(f"[validation] trimmed sample to {len(sampled)} due to budget room ${val_room:.2f}")

    judge_system = build_judge_system_prompt(taxonomy)
    judged_rows, judge_stats = run_validation_judging(
        client=client,
        limiter=limiter,
        judge_model=judge_model,
        judge_system_prompt=judge_system,
        sample_rows=sampled,
        v21_by_id=v21_by_id,
        v22_by_id=v22_by_id,
        papers=papers,
    )
    chosen = {r["id"] for r in sampled}
    judged_rows = [r for r in judged_rows if r["id"] in chosen]
    validation_summary = compute_validation_summary(judged_rows)
    patterns = top_changed_patterns(judged_rows, v21_by_id, v22_by_id)

    non_tie = validation_summary["n_non_tie"]
    margin = validation_summary["net_margin_v2_2_minus_v2_1"]
    changed_margin = validation_summary["changed_subset"]["net_margin"]
    required_margin = max(5, int(0.05 * max(non_tie, 1)))
    if judge_model == correction_model:
        required_margin = max(required_margin, int(0.08 * max(non_tie, 1)))

    improved = (
        non_tie >= 40
        and margin >= required_margin
        and validation_summary["theme_non_regression"]
        and (validation_summary["domain_improvement_signal"] or changed_margin >= 5)
    )
    # honesty: if changed subset clearly loses, reject
    if validation_summary["changed_subset"]["n_non_tie"] >= 20 and changed_margin < 0:
        improved = False

    decision = {
        "accepted": bool(improved),
        "status": "ACCEPT_v2_2" if improved else "REJECT_keep_v2_1",
        "recommended_file": str(CANDIDATE_OUT if improved else FROZEN),
        "reason": (
            f"net_margin={margin} (required>={required_margin}), "
            f"changed_margin={changed_margin}, "
            f"theme_non_regression={validation_summary['theme_non_regression']}, "
            f"domain_signal={validation_summary['domain_improvement_signal']}"
        ),
        "papers_updated": acceptance_stats.get("accepted_total", 0),
    }
    DECISION_JSON.write_text(json.dumps(decision, indent=2), encoding="utf-8")

    write_validation_md(
        judged_rows,
        sampled,
        validation_summary,
        judge_model,
        judge_model != correction_model,
        patterns,
        v21_by_id,
        v22_by_id,
    )
    write_audit50_md(sampled, {r["id"]: r for r in judged_rows}, papers, v21_by_id, v22_by_id)

    val_spend = round(cost_from_usage(judge_model, judge_stats.get("usage", {})), 4)
    spent = {
        "correction": targeted_summary["cost_usd"],
        "validation": val_spend,
        "verify": round(verify_spend, 4),
        "total": round(targeted_summary["cost_usd"] + val_spend + verify_spend, 4),
    }

    if spent["total"] > TOTAL_BUDGET_USD:
        print(f"[WARN] total spend ${spent['total']:.2f} exceeded hard cap ${TOTAL_BUDGET_USD:.2f}")

    team_blurb = (
        f"Overnight we closed four taxonomy gaps (thermoelectrics, optical metrology, implant bioelectronics, "
        f"computer architecture) and re-scored a high-yield subset (~{targeted_summary['unique_ids']} papers) "
        f"with Sonnet under a ${TOTAL_BUDGET_USD:.0f} hard spend cap (actual ${spent['total']:.2f}; "
        f"peak parallelism {_PEAK_PARALLEL}). "
        + (
            f"Blind validation favored v2.2 (net +{margin} on non-ties; changed-subset net +{changed_margin}); "
            f"we accepted {acceptance_stats.get('accepted_total',0)} conservative updates. Recommend shipping v2.2."
            if improved
            else f"Blind validation did NOT clearly beat v2.1 (net {margin}; changed-subset {changed_margin}); "
            f"we are keeping v2.1 as the recommended labels and treating v2.2 as an experiment only."
        )
    )

    COST_OUT.write_text(
        json.dumps(
            {
                "budget_cap_usd": TOTAL_BUDGET_USD,
                "correction_soft_stop_usd": CORRECTION_SOFT_STOP,
                "validation_budget_reserve_usd": VALIDATION_BUDGET_RESERVE,
                "correction_model": correction_model,
                "judge_model": judge_model,
                "workers_config": {"start": START_WORKERS, "ramp": RAMP_WORKERS, "max": MAX_WORKERS},
                "workers_used": workers_used,
                "peak_parallel_observed": _PEAK_PARALLEL,
                "budget_stop_worked": budget_stop_worked,
                "correction_rows_written": targeted_summary["rows"],
                "correction_unique_ids": targeted_summary["unique_ids"],
                "queue_meta": queue_meta,
                "correction_usage": targeted_summary["usage"],
                "validation_usage": judge_stats.get("usage", {}),
                "spend_usd": spent,
                "decision": decision,
                "validation_summary": validation_summary,
                "acceptance_stats": acceptance_stats,
                "correction_phases": [
                    {k: v for k, v in p.items() if k != "phase_usage"} for p in correction_phases
                ],
                "updated": now_ts(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    write_run_report(
        decision=decision,
        acceptance_stats=acceptance_stats,
        spent=spent,
        peak_parallel=_PEAK_PARALLEL,
        workers_used=workers_used,
        budget_stop_worked=budget_stop_worked,
        queue_meta=queue_meta,
        correction_model=correction_model,
        targeted_summary=targeted_summary,
        judge_model=judge_model,
        validation_summary=validation_summary,
        patterns=patterns,
        team_blurb=team_blurb,
    )

    print("==== v2.2 RUN COMPLETE ====")
    print(
        json.dumps(
            {
                "decision": decision,
                "validation_summary": validation_summary,
                "spend_usd": spent,
                "peak_parallel": _PEAK_PARALLEL,
                "workers_used": workers_used,
                "budget_stop_worked": budget_stop_worked,
                "candidate_rows": len(merged_rows),
                "targeted_rows": targeted_summary["rows"],
            },
            indent=2,
        )
    )
    print("Artifacts:")
    print(" ", RUN_REPORT_MD)
    print(" ", CANDIDATE_OUT)
    print(" ", TARGETED_OUT)
    print(" ", COST_OUT)
    print(" ", VALIDATION_MD)
    print(" ", AUDIT50_MD)


if __name__ == "__main__":
    main()
