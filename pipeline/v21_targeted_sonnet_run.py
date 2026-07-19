"""Targeted Sonnet improvement run for classification v2 -> v2_1 candidate.

Implements the mission-critical staged flow:
  A) freeze baseline + build targeted queue + domain-optimized prompts
  B) parallel Sonnet correction with bounded concurrency, retries, checkpoints
  C) conservative acceptance gate for merge to full-corpus v2_1 candidate
  D) honest random-subset validation via blind A/B judging
  E) decision gate and deployment recommendation

Constraints:
  - file-based only (no production DB writes)
  - rollback-safe baseline snapshot
  - honest, conservative acceptance and recommendation
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import random
import re
import shutil
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
BASELINE = OUTPUTS / "classification_v2_final.jsonl"
BASELINE_METRICS = WORK / "goldset_metrics.json"
BASELINE_AUDIT = OUTPUTS / "audit_50_random.md"
PAPERS = WORK / "papers_source.jsonl"
DIAGNOSIS_MD = OUTPUTS / "domain_diagnosis.md"
TAXONOMY_PREF = [
    OUTPUTS / "taxonomy-draft-v2-prefix.json",
    OUTPUTS / "taxonomy-draft-v2.json",
]

SAFE_BASELINE_DIR = OUTPUTS / "safe_baseline"
TARGETED_OUT = WORK / "sonnet_targeted_v21.jsonl"
COST_OUT = WORK / "sonnet_v21_cost.json"
CANDIDATE_OUT = OUTPUTS / "classification_v2_1_candidate.jsonl"
VALIDATION_JSONL = WORK / "v21_random_subset_adjudication.jsonl"
RUN_REPORT_MD = OUTPUTS / "v21_run_report.md"
VALIDATION_MD = OUTPUTS / "v21_validation_random_subset.md"
AUDIT50_MD = OUTPUTS / "audit_50_random_v21.md"

# ------------------------------ run config --------------------------------- #
TOTAL_BUDGET_USD = 80.0
VALIDATION_BUDGET_RESERVE = 12.0
CORRECTION_BUDGET_USD = TOTAL_BUDGET_USD - VALIDATION_BUDGET_RESERVE

START_WORKERS = 35
RAMP_WORKERS = 60
MAX_WORKERS = 80
PILOT_ROWS = 120
PILOT_WORKERS = 12
CHECKPOINT_EVERY = 300

MAX_API_ATTEMPTS = 6
PHASE_429_OK = 0.05
PHASE_5XX_OK = 0.03

QUEUE_HARD_CAP = int(os.environ.get("V21_QUEUE_HARD_CAP", "45000"))
RPM_LIMIT = int(os.environ.get("V21_RPM_LIMIT", "1800"))
TPM_LIMIT = int(os.environ.get("V21_TPM_LIMIT", "900000"))

VALIDATION_SAMPLE_N = int(os.environ.get("V21_VALIDATION_SAMPLE_N", "220"))
VALIDATION_SEED = int(os.environ.get("V21_VALIDATION_SEED", "20260718"))
AUDIT50_SEED = int(os.environ.get("V21_AUDIT50_SEED", "20260719"))

CORRECTION_MODEL_CANDIDATES = [
    "claude-sonnet-4-5",
]
JUDGE_MODEL_CANDIDATES = [
    "claude-opus-4-5",
    "claude-opus-4-1",
    "claude-sonnet-4-5",
    "claude-haiku-4-5",
]

# Cost map (USD per million tokens). Opus values are explicit estimates.
PRICING = {
    "claude-haiku-4-5": {"in": 1.00, "out": 5.00, "cache_write": 1.25, "cache_read": 0.10},
    "claude-sonnet-4-5": {"in": 3.00, "out": 15.00, "cache_write": 3.75, "cache_read": 0.30},
    "claude-opus-4-1": {"in": 15.00, "out": 75.00, "cache_write": 18.75, "cache_read": 1.50},
    "claude-opus-4-5": {"in": 15.00, "out": 75.00, "cache_write": 18.75, "cache_read": 1.50},
}

CONFUSION_DOMAINS = {
    "Grid Integration & Smart Microgrids",
    "Power Systems & Grid Control",
    "Solar Thermal Energy & Heat Transfer Systems",
    "Algorithms & Computational Complexity",
    "Materials, Joining & Mechanical Behavior",
    "Composite & Laminate Structures",
    "Structural Dynamics & Seismic Engineering",
    "Organometallic & Chalcogenide Synthesis",
    "Drug Delivery & Molecular Therapeutics",
    "Wireless Network Access & Resource Allocation",
    "Semiconductor Photovoltaic & Photodetection Devices",
    "Next-Generation Photovoltaic Materials",
    "Carbon Utilization & Chemical Conversion",
    "Environmental Assessment & Land Use Management",
    "Fluid-Particle Flow & Multiphase Systems",
    "Digital Transformation & IT Applications",
}

TIEBREAK_BULLETS = [
    "Power-system operation (bulk-grid stability/load-flow/protection) belongs to Power Systems & Grid Control; renewable-source integration (PV/wind/battery inverters, DER microgrids) belongs to Grid Integration & Smart Microgrids.",
    "Thermodynamic-cycle, refrigeration, combustion, or engine-performance papers prefer Solar Thermal Energy & Heat Transfer Systems unless the core novelty is fuel chemistry.",
    "PV device-architecture/photodetector papers prefer Semiconductor Photovoltaic & Photodetection Devices; PV absorber/HTL/ETL material innovation prefers Next-Generation Photovoltaic Materials.",
    "Within materials-mechanics overlap: composite-laminate mechanics belongs to Composite & Laminate Structures; process-linked joining/machining/mechanical behavior belongs to Materials, Joining & Mechanical Behavior.",
    "If the work is protocol/network-resource design, choose Wireless Network Access & Resource Allocation rather than Algorithms & Computational Complexity.",
    "If contribution is primarily social-policy/business outcome and IT is incidental, avoid Digital Transformation & IT Applications.",
    "Use unclassifiable only with explicit out-of-scope/no-research/no-signal evidence from title/abstract; otherwise choose the closest supported domain.",
]


@dataclass
class Taxonomy:
    path: Path
    themes: list[dict[str, Any]]
    theme_to_domains: dict[str, list[dict[str, Any]]]
    theme_to_domain_names: dict[str, list[str]]
    domain_to_theme: dict[str, str]


class RateLimiter:
    """Simple rolling-window RPM/TPM limiter."""

    def __init__(self, rpm_limit: int, tpm_limit: int):
        self.rpm_limit = rpm_limit
        self.tpm_limit = tpm_limit
        self.req_events = deque()
        self.tok_events = deque()
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


def now_ts() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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


def parse_json_object(text: str) -> dict[str, Any]:
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if m:
        text = m.group(1)
    s = text.find("{")
    e = text.rfind("}")
    if s < 0 or e < 0:
        raise ValueError("no JSON object found")
    return json.loads(text[s:e + 1])


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


def tie_break_reason(reason: str | None) -> bool:
    r = normalize(reason)
    if not r:
        return False
    keys = ["tie-break", "rather than", "instead of", "primary contribution", "rule", "because"]
    return any(k in r for k in keys)


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
    ]
    return any(k in r for k in keys)


def read_taxonomy() -> Taxonomy:
    tax_path = None
    for p in TAXONOMY_PREF:
        if p.exists():
            tax_path = p
            break
    if tax_path is None:
        raise SystemExit("taxonomy file not found (expected v2 prefix/json)")
    tax = json.loads(tax_path.read_text(encoding="utf-8"))
    themes = tax["themes"]
    theme_to_domains: dict[str, list[dict[str, Any]]] = {}
    theme_to_domain_names: dict[str, list[str]] = {}
    domain_to_theme: dict[str, str] = {}
    for t in themes:
        tname = t["name"]
        domains = t["domains"]
        theme_to_domains[tname] = domains
        theme_to_domain_names[tname] = [d["name"] if isinstance(d, dict) else d for d in domains]
        for d in domains:
            dname = d["name"] if isinstance(d, dict) else d
            domain_to_theme[dname] = tname
    return Taxonomy(
        path=tax_path,
        themes=themes,
        theme_to_domains=theme_to_domains,
        theme_to_domain_names=theme_to_domain_names,
        domain_to_theme=domain_to_theme,
    )


def freeze_baseline(tax_path: Path) -> dict[str, Any]:
    SAFE_BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    snaps = {
        "classification_v2_final": BASELINE,
        "goldset_metrics": BASELINE_METRICS,
        "taxonomy_v2": tax_path,
    }
    manifest = {"created_at": now_ts(), "files": {}}
    for k, src in snaps.items():
        if not src.exists():
            continue
        dst = SAFE_BASELINE_DIR / f"{k}.snapshot"
        if src.suffix:
            dst = dst.with_suffix(src.suffix)
        shutil.copy2(src, dst)
        manifest["files"][k] = {
            "src": str(src),
            "snapshot": str(dst),
            "sha256": sha256_of(dst),
            "bytes": dst.stat().st_size,
        }
    man_path = SAFE_BASELINE_DIR / "manifest_v21.json"
    man_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def load_baseline_rows() -> list[dict[str, Any]]:
    rows = load_jsonl(BASELINE)
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


def build_target_queue(v2_rows: list[dict[str, Any]], papers: dict[str, dict[str, Any]]) -> tuple[list[str], dict[str, str], dict[str, Any]]:
    low: list[tuple[float, str]] = []
    confusion_hi: list[tuple[float, str]] = []
    why: dict[str, str] = {}
    for r in v2_rows:
        if r.get("unclassifiable"):
            continue
        pid = r["id"]
        if pid not in papers:
            continue
        conf = r.get("confidence")
        dom = r.get("domain")
        if conf is None:
            continue
        if conf < 0.8:
            low.append((float(conf), pid))
            why[pid] = "low_confidence"
        elif dom in CONFUSION_DOMAINS:
            confusion_hi.append((float(conf), pid))
            why[pid] = "confusion_domain_high_conf"
    low.sort(key=lambda x: (x[0], x[1]))
    confusion_hi.sort(key=lambda x: (x[0], x[1]))
    ordered = [pid for _, pid in low]
    for _, pid in confusion_hi:
        if pid not in why or why[pid] == "confusion_domain_high_conf":
            ordered.append(pid)

    meta = {
        "low_confidence_count": len(low),
        "confusion_high_conf_count": len(confusion_hi),
        "pre_cap_total": len(ordered),
        "queue_hard_cap": QUEUE_HARD_CAP,
    }
    if len(ordered) > QUEUE_HARD_CAP:
        ordered = ordered[:QUEUE_HARD_CAP]
        dropped = meta["pre_cap_total"] - len(ordered)
        kept = set(ordered)
        why = {k: v for k, v in why.items() if k in kept}
        meta["capped"] = True
        meta["dropped_due_hard_cap"] = dropped
    else:
        meta["capped"] = False
        meta["dropped_due_hard_cap"] = 0
    return ordered, why, meta


def choose_domains_for_theme(theme: str, taxonomy: Taxonomy) -> list[dict[str, Any]]:
    return taxonomy.theme_to_domains.get(theme, [])


def estimate_tokens(text: str) -> int:
    return max(16, int(len(text) / 4))


def build_correction_system_prompt() -> str:
    L: list[str] = []
    A = L.append
    A("You are a strict taxonomy classifier for IIT Delhi research papers.")
    A("PRIMARY MODE: theme-locked domain correction.")
    A("You will receive one existing theme and MUST choose exactly one domain from that theme's allowed domain list.")
    A("Judge by PRIMARY scientific contribution, not incidental keywords.")
    A("")
    A("Known confusion tie-breaks (apply strictly):")
    for i, b in enumerate(TIEBREAK_BULLETS, 1):
        A(f"{i}. {b}")
    A("")
    A("Output STRICT JSON only with schema:")
    A('{"thematic_area": str, "domain": str, "confidence": float, "unclassifiable": bool, "reason": str}')
    A("reason must be <=18 words, concrete, and mention a distinguishing signal.")
    A("Use unclassifiable=true ONLY with explicit out-of-scope/no-signal evidence.")
    return "\n".join(L)


def build_full_reassess_system_prompt(taxonomy: Taxonomy) -> str:
    L: list[str] = []
    A = L.append
    A("You are an expert taxonomy adjudicator for research-paper classification.")
    A("SECONDARY MODE: full reassessment for hard ambiguous cases.")
    A("Choose the best thematic_area and one allowed domain from that thematic area.")
    A("Use unclassifiable only with strict evidence.")
    A("")
    A("Taxonomy (theme -> allowed domains):")
    for t in taxonomy.themes:
        A(f"- {t['name']}:")
        for d in t["domains"]:
            dn = d["name"] if isinstance(d, dict) else d
            dd = d.get("definition", "") if isinstance(d, dict) else ""
            A(f"  - {dn}: {dd[:180]}")
    A("")
    A("Output STRICT JSON only:")
    A('{"thematic_area": str, "domain": str, "confidence": float, "unclassifiable": bool, "reason": str}')
    A("reason <=18 words.")
    return "\n".join(L)


def build_theme_locked_user_prompt(
    paper: dict[str, Any],
    old: dict[str, Any],
    theme_domains: list[dict[str, Any]],
) -> str:
    tname = old.get("thematic_area") or ""
    L: list[str] = []
    A = L.append
    A("Classify this paper in theme-locked mode.")
    A(f"LOCKED_THEMATIC_AREA: {tname}")
    A("Allowed domains under this locked theme:")
    for d in theme_domains:
        dn = d["name"] if isinstance(d, dict) else str(d)
        dd = d.get("definition", "") if isinstance(d, dict) else ""
        A(f"- {dn}: {dd[:180]}")
    A("")
    A(f"Current label: theme={old.get('thematic_area')} | domain={old.get('domain')} | confidence={old.get('confidence')}")
    A("Paper:")
    A(f"Title: {paper.get('title') or ''}")
    ab = (paper.get("abstract") or "")[:1500]
    A(f"Abstract: {ab if ab else '(no abstract)'}")
    A("")
    A("Return the JSON object only.")
    return "\n".join(L)


def build_full_reassess_user_prompt(paper: dict[str, Any], old: dict[str, Any]) -> str:
    L: list[str] = []
    A = L.append
    A("Hard-case full reassessment requested.")
    A(f"Previous v2 label: theme={old.get('thematic_area')} | domain={old.get('domain')} | confidence={old.get('confidence')}")
    A("Paper:")
    A(f"Title: {paper.get('title') or ''}")
    ab = (paper.get("abstract") or "")[:1700]
    A(f"Abstract: {ab if ab else '(no abstract)'}")
    A("Return STRICT JSON only.")
    return "\n".join(L)


def parse_and_validate(
    obj: dict[str, Any] | None,
    taxonomy: Taxonomy,
    locked_theme: str | None,
) -> tuple[dict[str, Any] | None, str]:
    if obj is None:
        return None, "no_object"
    theme = obj.get("thematic_area")
    domain = obj.get("domain")
    reason = obj.get("reason")
    unclass = bool(obj.get("unclassifiable", False))
    conf = obj.get("confidence")
    try:
        conf = float(conf)
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

    row = {
        "thematic_area": theme,
        "domain": domain,
        "confidence": conf,
        "unclassifiable": unclass,
        "reason": reason,
    }
    return row, "ok"


def api_json_call(
    client: anthropic.Anthropic,
    limiter: RateLimiter,
    model: str,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 260,
    max_attempts: int = MAX_API_ATTEMPTS,
) -> tuple[dict[str, Any] | None, str, dict[str, int], str | None, dict[str, int]]:
    usage_total = {"input_tokens": 0, "output_tokens": 0, "cache_write": 0, "cache_read": 0}
    err: str | None = None
    raw = ""
    stats = {"calls": 0, "rate_limit": 0, "server_5xx": 0, "timeout_conn": 0, "parse_error": 0}
    for attempt in range(max_attempts):
        est = estimate_tokens(system_prompt) + estimate_tokens(user_prompt) + max_tokens
        limiter.acquire(est)
        try:
            stats["calls"] += 1
            resp = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user_prompt}],
            )
            u = usage_dict(resp.usage)
            add_usage(usage_total, u)
            raw = (resp.content[0].text if resp.content else "").strip()
            obj = parse_json_object(raw)
            return obj, raw, usage_total, None, stats
        except ValueError as e:
            stats["parse_error"] += 1
            err = f"parse_error:{e}"
            time.sleep(0.3 * (attempt + 1))
            continue
        except anthropic.RateLimitError as e:
            stats["rate_limit"] += 1
            err = f"rate_limit:{e}"
            backoff = min(30.0, (2 ** attempt) + random.uniform(0, 0.7))
            time.sleep(backoff)
            continue
        except anthropic.APIStatusError as e:
            code = getattr(e, "status_code", None)
            err = f"api_status_{code}:{e}"
            if code == 429:
                stats["rate_limit"] += 1
            elif code and code >= 500:
                stats["server_5xx"] += 1
            backoff = min(30.0, (2 ** attempt) + random.uniform(0, 0.7))
            time.sleep(backoff)
            continue
        except (anthropic.APITimeoutError, anthropic.APIConnectionError) as e:
            stats["timeout_conn"] += 1
            err = f"timeout_or_connection:{e}"
            backoff = min(20.0, (2 ** attempt) + random.uniform(0, 0.5))
            time.sleep(backoff)
            continue
        except Exception as e:  # noqa: BLE001
            err = f"unexpected:{repr(e)}"
            time.sleep(0.5 * (attempt + 1))
            continue
    return None, raw, usage_total, err, stats


def probe_model(client: anthropic.Anthropic, model: str) -> dict[str, Any]:
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=1,
            messages=[{"role": "user", "content": "Reply with token ok"}],
        )
        u = usage_dict(resp.usage)
        c = cost_from_usage(model, u)
        return {"model": model, "resolved": True, "usage": u, "cost_usd": round(c, 6)}
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
    return {
        "rows": rows,
        "unique_ids": len(ids),
        "usage": usage,
        "cost_usd": round(cost, 4),
    }


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
    client: anthropic.Anthropic,
    limiter: RateLimiter,
    model: str,
    taxonomy: Taxonomy,
    system_primary: str,
    system_full: str,
    chunk_ids: list[str],
    v2_by_id: dict[str, dict[str, Any]],
    papers: dict[str, dict[str, Any]],
    queue_why: dict[str, str],
    workers: int,
    chunk_label: str,
) -> dict[str, Any]:
    lock = threading.Lock()
    fh = open(TARGETED_OUT, "a", encoding="utf-8")
    stats = Counter()
    phase_usage = {"input_tokens": 0, "output_tokens": 0, "cache_write": 0, "cache_read": 0}
    t0 = time.time()
    written = 0

    def classify_one(pid: str) -> dict[str, Any]:
        old = v2_by_id[pid]
        paper = papers[pid]
        allowed = choose_domains_for_theme(old.get("thematic_area"), taxonomy)

        usage_total = {"input_tokens": 0, "output_tokens": 0, "cache_write": 0, "cache_read": 0}
        api_stats_total = Counter()

        obj1, raw1, usage1, err1, st1 = api_json_call(
            client=client,
            limiter=limiter,
            model=model,
            system_prompt=system_primary,
            user_prompt=build_theme_locked_user_prompt(paper, old, allowed),
            max_tokens=260,
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
        )
        if need_secondary:
            obj2, raw2, usage2, err2, st2 = api_json_call(
                client=client,
                limiter=limiter,
                model=model,
                system_prompt=system_full,
                user_prompt=build_full_reassess_user_prompt(paper, old),
                max_tokens=320,
            )
            add_usage(usage_total, usage2)
            api_stats_total.update(st2)
            p2, p2_note = parse_and_validate(obj2, taxonomy, None)
            if p2 is not None:
                p1c = p1.get("confidence") if p1 else None
                p2c = p2.get("confidence")
                if p1 is None or (p2c is not None and (p1c is None or p2c >= p1c + 0.05)):
                    chosen = p2
                    pass_mode = "full_reassess"
                    schema_note = p2_note
            elif chosen is None:
                schema_note = p2_note

        if chosen is None:
            chosen = {
                "thematic_area": old.get("thematic_area"),
                "domain": old.get("domain"),
                "confidence": old.get("confidence"),
                "unclassifiable": bool(old.get("unclassifiable")),
                "reason": f"api_failure_keep_old:{err1}"[:300],
            }
            pass_mode = "fallback_keep_old"

        rec = {
            "id": pid,
            "old_theme": old.get("thematic_area"),
            "old_domain": old.get("domain"),
            "old_confidence": old.get("confidence"),
            "new_theme": chosen.get("thematic_area"),
            "new_domain": chosen.get("domain"),
            "new_confidence": chosen.get("confidence"),
            "changed_theme": chosen.get("thematic_area") != old.get("thematic_area"),
            "changed_domain": chosen.get("domain") != old.get("domain"),
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
        return rec

    ex = ThreadPoolExecutor(max_workers=workers)
    futs = {ex.submit(classify_one, pid): pid for pid in chunk_ids}
    since = 0
    try:
        for fut in as_completed(futs):
            pid = futs[fut]
            try:
                rec = fut.result()
            except Exception as e:  # noqa: BLE001
                old = v2_by_id[pid]
                rec = {
                    "id": pid,
                    "old_theme": old.get("thematic_area"),
                    "old_domain": old.get("domain"),
                    "old_confidence": old.get("confidence"),
                    "new_theme": old.get("thematic_area"),
                    "new_domain": old.get("domain"),
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

            with lock:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            written += 1
            since += 1
            stats["rows_written"] += 1
            if rec.get("changed_domain"):
                stats["changed_domain_raw"] += 1
            if rec.get("changed_theme"):
                stats["changed_theme_raw"] += 1
            if rec.get("unclassifiable"):
                stats["unclassifiable_raw"] += 1
            if rec.get("pass_mode") == "full_reassess":
                stats["full_reassess_calls"] += 1
            api_stats = rec.get("api_stats") or {}
            stats["api_calls"] += int(api_stats.get("calls", 0))
            stats["rate_limit"] += int(api_stats.get("rate_limit", 0))
            stats["server_5xx"] += int(api_stats.get("server_5xx", 0))
            stats["timeout_conn"] += int(api_stats.get("timeout_conn", 0))
            stats["parse_error"] += int(api_stats.get("parse_error", 0))
            add_usage(phase_usage, rec.get("usage", {}))

            if since >= CHECKPOINT_EVERY:
                since = 0
                fh.flush()
                os.fsync(fh.fileno())
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
    return dict(stats)


def choose_correction_and_judge_models(client: anthropic.Anthropic) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    probes: list[dict[str, Any]] = []
    for m in dict.fromkeys(CORRECTION_MODEL_CANDIDATES + JUDGE_MODEL_CANDIDATES):
        probes.append(probe_model(client, m))

    corr = next((p for p in probes if p["model"] in CORRECTION_MODEL_CANDIDATES and p["resolved"]), None)
    if corr is None:
        raise SystemExit("No Sonnet model id resolved.")

    judge = None
    for m in JUDGE_MODEL_CANDIDATES:
        hit = next((p for p in probes if p["model"] == m and p["resolved"]), None)
        if hit is None:
            continue
        if m != corr["model"]:
            judge = hit
            break
    if judge is None:
        judge = corr
    return corr, judge, probes


def accept_candidate(old: dict[str, Any], new: dict[str, Any]) -> tuple[bool, str]:
    old_theme = old.get("thematic_area")
    old_domain = old.get("domain")
    old_conf = old.get("confidence")
    try:
        old_conf_f = float(old_conf) if old_conf is not None else None
    except Exception:
        old_conf_f = None

    new_theme = new.get("new_theme")
    new_domain = new.get("new_domain")
    new_conf = new.get("new_confidence")
    try:
        new_conf_f = float(new_conf) if new_conf is not None else None
    except Exception:
        new_conf_f = None
    new_unclass = bool(new.get("unclassifiable"))
    reason = new.get("reason")

    if new_unclass:
        if out_of_scope_evidence(reason) and (old_conf_f is None or old_conf_f < 0.6) and (
            new_conf_f is None or new_conf_f >= 0.7
        ):
            return True, "accept_unclass_oos_evidence"
        return False, "reject_unclass_weak_evidence"

    if new_theme != old_theme:
        if (old_conf_f is not None and old_conf_f < 0.5) and (new_conf_f is not None and new_conf_f >= 0.8):
            return True, "accept_theme_change_low_old_high_new"
        return False, "reject_theme_change_threshold"

    if new_domain != old_domain:
        if new_conf_f is not None and old_conf_f is not None and new_conf_f >= old_conf_f:
            return True, "accept_domain_conf_nonregression"
        if tie_break_reason(reason) and (new_conf_f is not None) and (
            old_conf_f is None or new_conf_f >= max(0.55, old_conf_f - 0.1)
        ):
            return True, "accept_domain_tiebreak_reason"
        return False, "reject_domain_change_weak"

    return False, "reject_no_label_change"


def merge_candidate(
    v2_rows: list[dict[str, Any]],
    targeted_rows_by_id: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, str]]:
    merged: list[dict[str, Any]] = []
    stats = Counter()
    decision_by_id: dict[str, str] = {}
    for old in v2_rows:
        pid = old["id"]
        new = targeted_rows_by_id.get(pid)
        if new is None:
            merged.append(old)
            stats["kept_no_targeted_row"] += 1
            decision_by_id[pid] = "kept_no_targeted_row"
            continue
        accept, rule = accept_candidate(old, new)
        if not accept:
            merged.append(old)
            stats[f"kept_{rule}"] += 1
            decision_by_id[pid] = rule
            continue
        rec = dict(old)
        rec["thematic_area"] = new.get("new_theme")
        rec["domain"] = new.get("new_domain")
        rec["confidence"] = new.get("new_confidence")
        rec["unclassifiable"] = bool(new.get("unclassifiable"))
        rec["reason"] = new.get("reason")
        rec["source_model"] = "sonnet_v2_1_targeted"
        rec["escalated"] = True
        merged.append(rec)
        stats["accepted_total"] += 1
        if rec["thematic_area"] != old.get("thematic_area"):
            stats["accepted_theme_change"] += 1
        if rec["domain"] != old.get("domain"):
            stats["accepted_domain_change"] += 1
        if rec["unclassifiable"] != bool(old.get("unclassifiable")):
            stats["accepted_unclass_change"] += 1
        stats[f"accepted_{rule}"] += 1
        decision_by_id[pid] = rule
    return merged, dict(stats), decision_by_id


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")


def stratified_sample(
    rows: list[dict[str, Any]],
    n: int,
    rng: random.Random,
    strata_key,
) -> list[dict[str, Any]]:
    if n >= len(rows):
        out = rows[:]
        rng.shuffle(out)
        return out
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
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
    out: list[dict[str, Any]] = []
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
    L: list[str] = []
    A = L.append
    A("You are an independent blind A/B judge for taxonomy labels.")
    A("Decide which label better matches the paper's primary scientific contribution.")
    A("Rules:")
    A("1) Focus on taxonomy fit, not writing style.")
    A("2) Prefer tie if both labels are similarly defensible.")
    A("3) Unclassifiable is valid only with explicit out-of-scope/no-signal evidence.")
    A("4) Output strict JSON only.")
    A("")
    A("Taxonomy (theme -> domains):")
    for t in taxonomy.themes:
        A(f"- {t['name']}:")
        for d in t["domains"]:
            dn = d["name"] if isinstance(d, dict) else d
            A(f"  - {dn}")
    A("")
    A('JSON schema: {"winner":"A|B|tie","theme_winner":"A|B|tie","domain_winner":"A|B|tie","confidence":"high|medium|low","rationale":"<=30 words"}')
    return "\n".join(L)


def run_validation_judging(
    *,
    client: anthropic.Anthropic,
    limiter: RateLimiter,
    judge_model: str,
    judge_system_prompt: str,
    sample_rows: list[dict[str, Any]],
    v2_by_id: dict[str, dict[str, Any]],
    v21_by_id: dict[str, dict[str, Any]],
    papers: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    lock = threading.Lock()
    existing = {}
    if VALIDATION_JSONL.exists():
        for r in load_jsonl(VALIDATION_JSONL):
            existing[r["id"]] = r
    todo = [r for r in sample_rows if r["id"] not in existing]

    fh = open(VALIDATION_JSONL, "a", encoding="utf-8")
    stats = Counter()
    usage_total = {"input_tokens": 0, "output_tokens": 0, "cache_write": 0, "cache_read": 0}

    def judge_one(s: dict[str, Any]) -> dict[str, Any]:
        pid = s["id"]
        old = v2_by_id[pid]
        new = v21_by_id[pid]
        p = papers[pid]
        order_flip = random.Random(f"{VALIDATION_SEED}-{pid}").random() < 0.5
        if order_flip:
            A_lab, B_lab = new, old
            map_ab = {"A": "v2_1", "B": "v2"}
        else:
            A_lab, B_lab = old, new
            map_ab = {"A": "v2", "B": "v2_1"}

        def lab_txt(x: dict[str, Any]) -> str:
            return (
                f"theme={x.get('thematic_area')}; domain={x.get('domain')}; "
                f"confidence={x.get('confidence')}; unclassifiable={bool(x.get('unclassifiable'))}"
            )

        user_prompt = "\n".join(
            [
                "Paper:",
                f"Title: {p.get('title') or ''}",
                f"Abstract: {(p.get('abstract') or '')[:1500] if (p.get('abstract') or '') else '(no abstract)'}",
                "",
                f"Label A: {lab_txt(A_lab)}",
                f"Label B: {lab_txt(B_lab)}",
                "",
                "Return strict JSON only.",
            ]
        )

        obj, raw, usage, err, call_stats = api_json_call(
            client=client,
            limiter=limiter,
            model=judge_model,
            system_prompt=judge_system_prompt,
            user_prompt=user_prompt,
            max_tokens=200,
            max_attempts=5,
        )
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

        mapped_winner = map_ab.get(decision["winner"], "tie") if decision["winner"] != "tie" else "tie"
        mapped_theme_winner = map_ab.get(decision["theme_winner"], "tie") if decision["theme_winner"] != "tie" else "tie"
        mapped_domain_winner = map_ab.get(decision["domain_winner"], "tie") if decision["domain_winner"] != "tie" else "tie"

        rec = {
            "id": pid,
            "changed": s["changed"],
            "band": s["band"],
            "theme_bucket": s["theme_bucket"],
            "order_flip": order_flip,
            "label_A": lab_txt(A_lab),
            "label_B": lab_txt(B_lab),
            "winner_raw": decision["winner"],
            "theme_winner_raw": decision["theme_winner"],
            "domain_winner_raw": decision["domain_winner"],
            "winner": mapped_winner,
            "theme_winner": mapped_theme_winner,
            "domain_winner": mapped_domain_winner,
            "judge_confidence": decision["confidence"],
            "rationale": decision["rationale"],
            "judge_model": judge_model,
            "usage": usage,
            "judge_calls": call_stats,
            "updated": now_ts(),
        }
        return rec

    ex = ThreadPoolExecutor(max_workers=24)
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
            stats["server_5xx"] += int(jc.get("server_5xx", 0))
            stats["timeout_conn"] += int(jc.get("timeout_conn", 0))
    finally:
        ex.shutdown(wait=True, cancel_futures=True)
        fh.flush()
        os.fsync(fh.fileno())
        fh.close()

    all_rows = load_jsonl(VALIDATION_JSONL)
    chosen = {r["id"] for r in sample_rows}
    judged = [r for r in all_rows if r["id"] in chosen]
    sum_cost = round(cost_from_usage(judge_model, usage_total), 4)
    stats["usage"] = usage_total
    stats["cost_usd_new_rows"] = sum_cost
    return judged, dict(stats)


def compute_validation_summary(judged: list[dict[str, Any]]) -> dict[str, Any]:
    win = Counter(r.get("winner") for r in judged)
    theme = Counter(r.get("theme_winner") for r in judged)
    domain = Counter(r.get("domain_winner") for r in judged)
    n_comp = win.get("v2_1", 0) + win.get("v2", 0)
    net_margin = win.get("v2_1", 0) - win.get("v2", 0)
    net_rate = round((win.get("v2_1", 0) / n_comp) * 100, 2) if n_comp else None
    summary = {
        "n_judged": len(judged),
        "overall_wins": dict(win),
        "theme_wins": dict(theme),
        "domain_wins": dict(domain),
        "n_non_tie": n_comp,
        "net_margin_v2_1_minus_v2": net_margin,
        "v2_1_win_rate_non_tie_pct": net_rate,
        "theme_non_regression": theme.get("v2_1", 0) >= theme.get("v2", 0),
        "domain_improvement_signal": domain.get("v2_1", 0) > domain.get("v2", 0),
    }
    return summary


def top_changed_patterns(
    judged: list[dict[str, Any]],
    v2_by_id: dict[str, dict[str, Any]],
    v21_by_id: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    win = Counter()
    lose = Counter()
    for r in judged:
        if not r.get("changed"):
            continue
        pid = r["id"]
        old = v2_by_id[pid]
        new = v21_by_id[pid]
        key = f"{old.get('thematic_area')} / {old.get('domain')} -> {new.get('thematic_area')} / {new.get('domain')}"
        if r.get("winner") == "v2_1":
            win[key] += 1
        elif r.get("winner") == "v2":
            lose[key] += 1
    return {
        "improved_patterns": [{"pattern": k, "count": v} for k, v in win.most_common(10)],
        "regressed_patterns": [{"pattern": k, "count": v} for k, v in lose.most_common(10)],
    }


def write_validation_md(
    judged: list[dict[str, Any]],
    sample_rows: list[dict[str, Any]],
    summary: dict[str, Any],
    judge_model: str,
    judge_is_independent: bool,
    patterns: dict[str, list[dict[str, Any]]],
    v2_by_id: dict[str, dict[str, Any]],
    v21_by_id: dict[str, dict[str, Any]],
) -> None:
    sample_map = {r["id"]: r for r in sample_rows}
    judged.sort(key=lambda x: x["id"])
    L: list[str] = []
    A = L.append
    A("# v2_1 Random-Subset Validation (Blind A/B)\n")
    A(f"- Sample size judged: **{summary['n_judged']}** (seed `{VALIDATION_SEED}`, stratified by changed/unchanged, confidence band, theme).")
    A(f"- Judge model: **{judge_model}**.")
    A(f"- Independent stronger judge available: **{'yes' if judge_is_independent else 'no'}**.")
    if not judge_is_independent:
        A("- Caveat: judge is not independent from correction model; conclusions are conservative.")
    A(f"- Overall winner counts: **v2_1={summary['overall_wins'].get('v2_1',0)}**, **v2={summary['overall_wins'].get('v2',0)}**, tie={summary['overall_wins'].get('tie',0)}.")
    A(f"- Net margin (v2_1 - v2): **{summary['net_margin_v2_1_minus_v2']}** on {summary['n_non_tie']} non-tie cases.")
    A(f"- Theme non-regression check: **{'PASS' if summary['theme_non_regression'] else 'FAIL'}**.")
    A(f"- Domain improvement signal: **{'PASS' if summary['domain_improvement_signal'] else 'FAIL'}**.\n")

    A("## Error-pattern changes (changed rows only)\n")
    A("### Top v2_1 wins")
    for p in patterns["improved_patterns"][:8]:
        A(f"- {p['count']}x: {p['pattern']}")
    A("### Top v2_1 losses")
    for p in patterns["regressed_patterns"][:8]:
        A(f"- {p['count']}x: {p['pattern']}")
    A("")

    A("## Per-paper adjudication\n")
    A("| # | id | changed | band | v2 label | v2_1 label | winner | rationale |")
    A("|---:|---|---|---|---|---|---|---|")
    for i, r in enumerate(judged, 1):
        pid = r["id"]
        old = v2_by_id[pid]
        new = v21_by_id[pid]
        w = r.get("winner")
        rat = (r.get("rationale") or "").replace("|", "\\|").replace("\n", " ")
        v2_lbl = f"{old.get('thematic_area')} / {old.get('domain')} / {old.get('confidence')}"
        v21_lbl = f"{new.get('thematic_area')} / {new.get('domain')} / {new.get('confidence')}"
        A(f"| {i} | {pid} | {sample_map[pid]['changed']} | {sample_map[pid]['band']} | {v2_lbl} | {v21_lbl} | {w} | {rat} |")
    A("")
    VALIDATION_MD.write_text("\n".join(L), encoding="utf-8")


def write_audit50_md(
    sample_rows: list[dict[str, Any]],
    judged_by_id: dict[str, dict[str, Any]],
    papers: dict[str, dict[str, Any]],
    v2_by_id: dict[str, dict[str, Any]],
    v21_by_id: dict[str, dict[str, Any]],
) -> None:
    rng = random.Random(AUDIT50_SEED)
    rows = sample_rows[:]
    rng.shuffle(rows)
    picks = rows[:50]
    L: list[str] = []
    A = L.append
    A(f"# Random 50-Paper Audit — v2 vs v2_1 (Seed: {AUDIT50_SEED})\n")
    A("- Source: blind A/B adjudication on stratified validation sample.")
    A("| # | id | title | v2 domain | v2_1 domain | winner | rationale |")
    A("|---:|---|---|---|---|---|---|")
    for i, s in enumerate(picks, 1):
        pid = s["id"]
        j = judged_by_id.get(pid, {})
        p = papers.get(pid, {})
        title = (p.get("title") or "").replace("|", "\\|").replace("\n", " ")
        if len(title) > 90:
            title = title[:87] + "..."
        v2d = v2_by_id[pid].get("domain")
        v21d = v21_by_id[pid].get("domain")
        w = j.get("winner", "tie")
        rat = (j.get("rationale") or "").replace("|", "\\|").replace("\n", " ")
        A(f"| {i} | {pid} | {title} | {v2d} | {v21d} | {w} | {rat} |")
    AUDIT50_MD.write_text("\n".join(L), encoding="utf-8")


def write_cost_file(payload: dict[str, Any]) -> None:
    payload = dict(payload)
    payload["updated"] = now_ts()
    COST_OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_run_report(
    *,
    baseline_metrics: dict[str, Any],
    queue_meta: dict[str, Any],
    snapshot_manifest: dict[str, Any],
    probes: list[dict[str, Any]],
    correction_model: str,
    judge_model: str,
    correction_phases: list[dict[str, Any]],
    targeted_summary: dict[str, Any],
    acceptance_stats: dict[str, Any],
    validation_summary: dict[str, Any],
    patterns: dict[str, list[dict[str, Any]]],
    decision: dict[str, Any],
    spent: dict[str, float],
) -> None:
    L: list[str] = []
    A = L.append
    A("# v2.1 Targeted Sonnet Run Report\n")
    A("- Mission constraints: file-based only, no production DB writes, rollback baseline frozen.")
    A(f"- Baseline snapshot dir: `{SAFE_BASELINE_DIR}`.")
    A(f"- Baseline proxy metrics: theme **{baseline_metrics.get('theme_agreement',{}).get('pct')}%**, domain **{baseline_metrics.get('domain_agreement',{}).get('pct')}%**.")
    A("")
    A("## Stage A — Freeze + Queue")
    A(f"- Taxonomy used: `{queue_meta['taxonomy_path']}`.")
    A(f"- Queue pre-cap: **{queue_meta['pre_cap_total']}** (low<0.8={queue_meta['low_confidence_count']}, high-conf confusion={queue_meta['confusion_high_conf_count']}).")
    A(f"- Queue after budget cap: **{queue_meta['budget_capped_total']}**.")
    A(f"- Pilot rows for cost estimation: **{queue_meta['pilot_rows']}**.")
    A(f"- Estimated correction rows affordable under budget: **{queue_meta['estimated_rows_under_budget']}**.")
    A("")
    A("## Stage B — Parallel Sonnet correction")
    A(f"- Correction model: **{correction_model}**.")
    A(f"- Concurrency ramp: start {START_WORKERS}, then {RAMP_WORKERS}, then up to {MAX_WORKERS} when 429/5xx low.")
    A("- Phase stats:")
    for p in correction_phases:
        A(
            f"  - {p.get('chunk_label')}: workers={p.get('workers')}, "
            f"rows={p.get('rows_written')}, rate429={p.get('rate_limit',0)}, "
            f"5xx={p.get('server_5xx',0)}, phase_cost=${p.get('phase_cost_usd')}"
        )
    A(f"- Targeted output rows written: **{targeted_summary['rows']}** (unique ids={targeted_summary['unique_ids']}).")
    A("")
    A("## Stage C — Conservative acceptance gate")
    A(f"- Accepted total: **{acceptance_stats.get('accepted_total',0)}**.")
    A(f"- Accepted domain changes: **{acceptance_stats.get('accepted_domain_change',0)}**.")
    A(f"- Accepted theme changes: **{acceptance_stats.get('accepted_theme_change',0)}**.")
    A(f"- Accepted unclassifiable conversions: **{acceptance_stats.get('accepted_unclass_change',0)}**.")
    A("- Weak/unjustified changes were rejected and kept at baseline label.")
    A("")
    A("## Stage D — Random subset validation")
    A(f"- Judge model: **{judge_model}**.")
    A(f"- Net wins: v2_1={validation_summary['overall_wins'].get('v2_1',0)} vs v2={validation_summary['overall_wins'].get('v2',0)} (ties={validation_summary['overall_wins'].get('tie',0)}).")
    A(f"- Theme non-regression: **{'PASS' if validation_summary['theme_non_regression'] else 'FAIL'}**.")
    A(f"- Domain improvement signal: **{'PASS' if validation_summary['domain_improvement_signal'] else 'FAIL'}**.")
    A("- Top improvement patterns:")
    for p in patterns["improved_patterns"][:6]:
        A(f"  - {p['count']}x {p['pattern']}")
    A("- Top regression patterns:")
    for p in patterns["regressed_patterns"][:6]:
        A(f"  - {p['count']}x {p['pattern']}")
    A("")
    A("## Stage E — Decision gate")
    A(f"- Decision: **{decision['status']}**.")
    A(f"- Recommendation tonight: **{decision['recommended_file']}**.")
    A(f"- Reason: {decision['reason']}")
    A("")
    A("## Cost")
    A(f"- Correction spend: **${spent['correction']:.2f}**")
    A(f"- Validation spend: **${spent['validation']:.2f}**")
    A(f"- Model verify/probe spend: **${spent['verify']:.2f}**")
    A(f"- Total spend this run: **${spent['total']:.2f}** (cap ${TOTAL_BUDGET_USD:.2f})")
    A("")
    A("## Artifacts")
    A(f"- `{CANDIDATE_OUT}`")
    A(f"- `{TARGETED_OUT}`")
    A(f"- `{COST_OUT}`")
    A(f"- `{VALIDATION_MD}`")
    A(f"- `{AUDIT50_MD}`")
    RUN_REPORT_MD.write_text("\n".join(L), encoding="utf-8")


def main() -> None:
    load_dotenv(ROOT / ".env")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY missing in .env")

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"], timeout=120.0, max_retries=0)
    limiter = RateLimiter(RPM_LIMIT, TPM_LIMIT)

    taxonomy = read_taxonomy()
    snapshot_manifest = freeze_baseline(taxonomy.path)

    v2_rows = load_baseline_rows()
    v2_by_id = {r["id"]: r for r in v2_rows}
    papers = load_papers_map()

    queue_ids, queue_why, queue_meta = build_target_queue(v2_rows, papers)
    queue_meta["taxonomy_path"] = str(taxonomy.path)

    correction_model_probe, judge_model_probe, probes = choose_correction_and_judge_models(client)
    correction_model = correction_model_probe["model"]
    judge_model = judge_model_probe["model"]
    verify_spend = sum(p.get("cost_usd", 0.0) for p in probes if p.get("resolved"))

    # Resume-aware done set
    done = load_done_ids(TARGETED_OUT)
    queue_ids = [pid for pid in queue_ids if pid not in done]

    # Pilot-driven budget cap estimation
    system_primary = build_correction_system_prompt()
    system_full = build_full_reassess_system_prompt(taxonomy)

    correction_phases: list[dict[str, Any]] = []

    already = summarize_targeted_output(TARGETED_OUT)
    avg_cost = (already["cost_usd"] / already["unique_ids"]) if already["unique_ids"] else None
    pilot_rows = 0
    if avg_cost is None and queue_ids:
        pilot_ids = queue_ids[: min(PILOT_ROWS, len(queue_ids))]
        pstats = run_correction_chunk(
            client=client,
            limiter=limiter,
            model=correction_model,
            taxonomy=taxonomy,
            system_primary=system_primary,
            system_full=system_full,
            chunk_ids=pilot_ids,
            v2_by_id=v2_by_id,
            papers=papers,
            queue_why=queue_why,
            workers=PILOT_WORKERS,
            chunk_label="pilot_cost_estimation",
        )
        correction_phases.append(pstats)
        pilot_rows = pstats.get("rows_written", 0)
        already = summarize_targeted_output(TARGETED_OUT)
        avg_cost = (already["cost_usd"] / already["unique_ids"]) if already["unique_ids"] else 0.0
        done = load_done_ids(TARGETED_OUT)
        queue_ids = [pid for pid in queue_ids if pid not in done]

    if avg_cost is None or avg_cost <= 0:
        avg_cost = 0.0034  # conservative fallback estimate
    est_affordable_rows = int(max(0, math.floor(CORRECTION_BUDGET_USD / avg_cost)))
    est_affordable_rows = max(est_affordable_rows, pilot_rows)

    # Rebuild full ordered queue and budget-cap it
    all_queue_ids, queue_why, _ = build_target_queue(v2_rows, papers)
    budget_capped_queue = all_queue_ids[: min(len(all_queue_ids), est_affordable_rows)]
    if len(budget_capped_queue) < len(all_queue_ids):
        print(
            f"[queue] budget cap active: {len(budget_capped_queue)} / {len(all_queue_ids)}"
            f" (avg_cost=${avg_cost:.6f})"
        )
    done = load_done_ids(TARGETED_OUT)
    pending_ids = [pid for pid in budget_capped_queue if pid not in done]

    queue_meta["pilot_rows"] = pilot_rows
    queue_meta["avg_cost_per_row_usd"] = round(avg_cost, 6)
    queue_meta["estimated_rows_under_budget"] = est_affordable_rows
    queue_meta["budget_capped_total"] = len(budget_capped_queue)

    # Stage B main run with ramped concurrency
    phase_plan = [
        ("phase_start", START_WORKERS, 1500),
        ("phase_ramp", RAMP_WORKERS, 6000),
        ("phase_max", MAX_WORKERS, None),
    ]
    for label, workers, chunk_n in phase_plan:
        if not pending_ids:
            break
        if chunk_n is None:
            chunk = pending_ids[:]
        else:
            chunk = pending_ids[: min(chunk_n, len(pending_ids))]
        if not chunk:
            break
        pstats = run_correction_chunk(
            client=client,
            limiter=limiter,
            model=correction_model,
            taxonomy=taxonomy,
            system_primary=system_primary,
            system_full=system_full,
            chunk_ids=chunk,
            v2_by_id=v2_by_id,
            papers=papers,
            queue_why=queue_why,
            workers=workers,
            chunk_label=label,
        )
        correction_phases.append(pstats)
        pending_ids = pending_ids[len(chunk) :]
        sum_corr = summarize_targeted_output(TARGETED_OUT)
        corr_spend = sum_corr["cost_usd"]
        if corr_spend >= CORRECTION_BUDGET_USD:
            print(f"[cost-stop] correction budget reached ${corr_spend:.2f}")
            break
        # If ramp phase had elevated errors, do not escalate further.
        if label != "phase_max":
            calls = max(1, int(pstats.get("api_calls", 0)))
            rl = pstats.get("rate_limit", 0) / calls
            sx = pstats.get("server_5xx", 0) / calls
            if rl > PHASE_429_OK or sx > PHASE_5XX_OK:
                print(f"[ramp] high transient errors (429={rl:.2%}, 5xx={sx:.2%}); staying conservative.")
                # keep remaining on current worker count by inserting one more conservative phase
                if pending_ids:
                    extra = run_correction_chunk(
                        client=client,
                        limiter=limiter,
                        model=correction_model,
                        taxonomy=taxonomy,
                        system_primary=system_primary,
                        system_full=system_full,
                        chunk_ids=pending_ids[:],
                        v2_by_id=v2_by_id,
                        papers=papers,
                        queue_why=queue_why,
                        workers=workers,
                        chunk_label=f"{label}_conservative_hold",
                    )
                    correction_phases.append(extra)
                    pending_ids = []
                break

    targeted_summary = summarize_targeted_output(TARGETED_OUT)

    # Build latest targeted-by-id map for capped queue
    targeted_latest = {}
    for r in load_jsonl(TARGETED_OUT):
        if r["id"] in set(budget_capped_queue):
            targeted_latest[r["id"]] = r

    # Stage C merge under conservative acceptance
    merged_rows, acceptance_stats, decision_by_id = merge_candidate(v2_rows, targeted_latest)
    write_jsonl(CANDIDATE_OUT, merged_rows)
    v21_by_id = {r["id"]: r for r in merged_rows}

    # Stage D validation sample
    frame = []
    for old in v2_rows:
        pid = old["id"]
        if pid not in papers:
            continue
        new = v21_by_id.get(pid)
        if not new:
            continue
        changed = (
            old.get("thematic_area") != new.get("thematic_area")
            or old.get("domain") != new.get("domain")
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
    changed_target = min(len(changed_rows), max(80, int(VALIDATION_SAMPLE_N * 0.45)))
    unchanged_target = max(0, VALIDATION_SAMPLE_N - changed_target)
    sampled = stratified_sample(
        changed_rows,
        changed_target,
        rng,
        strata_key=lambda x: (x["band"], x["theme_bucket"]),
    ) + stratified_sample(
        unchanged_rows,
        unchanged_target,
        rng,
        strata_key=lambda x: (x["band"], x["theme_bucket"]),
    )
    sampled = stratified_sample(
        sampled,
        min(VALIDATION_SAMPLE_N, len(sampled)),
        rng,
        strata_key=lambda x: (x["changed"], x["band"], x["theme_bucket"]),
    )

    judge_system_prompt = build_judge_system_prompt(taxonomy)
    judged_rows, judge_stats = run_validation_judging(
        client=client,
        limiter=limiter,
        judge_model=judge_model,
        judge_system_prompt=judge_system_prompt,
        sample_rows=sampled,
        v2_by_id=v2_by_id,
        v21_by_id=v21_by_id,
        papers=papers,
    )
    # keep sample order stable in reports
    chosen = {r["id"] for r in sampled}
    judged_rows = [r for r in judged_rows if r["id"] in chosen]

    validation_summary = compute_validation_summary(judged_rows)
    patterns = top_changed_patterns(judged_rows, v2_by_id, v21_by_id)

    # Decision gate (conservative)
    non_tie = validation_summary["n_non_tie"]
    margin = validation_summary["net_margin_v2_1_minus_v2"]
    required_margin = max(8, int(0.05 * max(non_tie, 1)))
    if judge_model == correction_model:
        required_margin = max(required_margin, int(0.08 * max(non_tie, 1)))
    improved = (
        non_tie >= 80
        and margin >= required_margin
        and validation_summary["theme_non_regression"]
        and validation_summary["domain_improvement_signal"]
    )
    decision = {
        "status": "recommended_v2_1" if improved else "reject_v2_1_keep_v2",
        "recommended_file": str(CANDIDATE_OUT if improved else BASELINE),
        "reason": (
            f"net_margin={margin} (required>={required_margin}), "
            f"theme_non_regression={validation_summary['theme_non_regression']}, "
            f"domain_signal={validation_summary['domain_improvement_signal']}"
        ),
    }

    judged_by_id = {r["id"]: r for r in judged_rows}
    write_validation_md(
        judged=judged_rows,
        sample_rows=sampled,
        summary=validation_summary,
        judge_model=judge_model,
        judge_is_independent=(judge_model != correction_model),
        patterns=patterns,
        v2_by_id=v2_by_id,
        v21_by_id=v21_by_id,
    )
    write_audit50_md(
        sample_rows=sampled,
        judged_by_id=judged_by_id,
        papers=papers,
        v2_by_id=v2_by_id,
        v21_by_id=v21_by_id,
    )

    baseline_metrics = json.loads(BASELINE_METRICS.read_text(encoding="utf-8")) if BASELINE_METRICS.exists() else {}
    corr_spend = targeted_summary["cost_usd"]
    val_spend = round(cost_from_usage(judge_model, judge_stats.get("usage", {})), 4)
    spent = {
        "correction": corr_spend,
        "validation": val_spend,
        "verify": round(verify_spend, 4),
        "total": round(corr_spend + val_spend + verify_spend, 4),
    }

    write_cost_file(
        {
            "budget_cap_usd": TOTAL_BUDGET_USD,
            "correction_budget_usd": CORRECTION_BUDGET_USD,
            "validation_budget_reserve_usd": VALIDATION_BUDGET_RESERVE,
            "correction_model": correction_model,
            "judge_model": judge_model,
            "correction_rows_written": targeted_summary["rows"],
            "correction_unique_ids": targeted_summary["unique_ids"],
            "queue_meta": queue_meta,
            "correction_usage": targeted_summary["usage"],
            "validation_usage": judge_stats.get("usage", {}),
            "spend_usd": spent,
            "decision": decision,
            "validation_summary": validation_summary,
        }
    )

    write_run_report(
        baseline_metrics=baseline_metrics,
        queue_meta=queue_meta,
        snapshot_manifest=snapshot_manifest,
        probes=probes,
        correction_model=correction_model,
        judge_model=judge_model,
        correction_phases=correction_phases,
        targeted_summary=targeted_summary,
        acceptance_stats=acceptance_stats,
        validation_summary=validation_summary,
        patterns=patterns,
        decision=decision,
        spent=spent,
    )

    print("==== v2_1 RUN COMPLETE ====")
    print(json.dumps({
        "decision": decision,
        "validation_summary": validation_summary,
        "spend_usd": spent,
        "candidate_rows": len(merged_rows),
        "targeted_rows": targeted_summary["rows"],
    }, indent=2))
    print("Artifacts:")
    print(" ", RUN_REPORT_MD)
    print(" ", CANDIDATE_OUT)
    print(" ", TARGETED_OUT)
    print(" ", COST_OUT)
    print(" ", VALIDATION_MD)
    print(" ", AUDIT50_MD)


if __name__ == "__main__":
    main()
