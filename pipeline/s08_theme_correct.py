"""Step 1b: theme-correct the Step-1 sample.

The v1 theme labels used to sample papers are only ~2/3 accurate, so the Step-1
domains were derived from contaminated pools. Here we re-assign each sampled paper
(title + abstract) to the single best-fit of the 9 FIXED themes (or "unclassifiable"
for editorials / front-matter / no-abstract errata) using claude-haiku-4-5.

- Theme-ONLY (no domains).
- The big scope-note block is sent as a cached system prompt (prompt caching).
- Concurrency kept well under the 10K RPM / 10M input TPM limits; 429s are retried.
- Resumable: results are flushed to theme_corrected.json as they complete.
"""
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic
from dotenv import load_dotenv

from common import WORK, ROOT

load_dotenv(ROOT / ".env")

MODEL = "claude-haiku-4-5"
PRICE_IN = 1.00
PRICE_OUT = 5.00
PRICE_CACHE_WRITE = 1.25
PRICE_CACHE_READ = 0.10

MAX_WORKERS = 8
FLUSH_EVERY = 100

_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# Theme numbering is FIXED by this list (index+1 == the number the model returns).
# Names/ids must match the thematicareas collection (verified in db_facts.json).
THEME_ORDER = [
    ("6a46ea5ece9a42a451a4714c", "Energy, Sustainability & Climate Change"),
    ("6a46ea5ece9a42a451a4714b", "Advanced Materials & Devices"),
    ("6a46ea5ece9a42a451a4714f", "Manufacturing & Industry 4.0"),
    ("6a46ea5ece9a42a451a47152", "Smart & Sustainable Infrastructure"),
    ("6a46ea5ece9a42a451a4714d", "Healthcare & MedTech"),
    ("6a46ea5ece9a42a451a47150", "Next-Gen Communication"),
    ("6a46ea5ece9a42a451a4714a", "AI/ML, Supercomputing & Quantum Computing"),
    ("6a46ea5ece9a42a451a47151", "Quantum Technologies & Semiconductor Technology"),
    ("6a46ea5ece9a42a451a47153", "Social Sciences, Humanities & Management"),
]

SCOPE_BLOCK = """You are a precise research-paper classifier for IIT Delhi's research portal.
Your job: read a paper's title and abstract and assign it to exactly ONE of the 9 fixed
thematic areas below (or mark it as not-a-research-paper). Decide by the paper's PRIMARY
scientific contribution, not by an incidental keyword. If a paper could plausibly fit two
themes, apply the tie-break rules at the end. Reply with ONLY the single digit of the
best-fit theme (1-9), or 0 if the item is not a research paper.

1. Energy, Sustainability & Climate Change
   Scope: renewable energy systems (solar PV and wind grid integration, microgrids, power
   quality, inverters for renewables), batteries and electrochemical energy storage
   (Li-ion, flow, K-ion) with performance/thermal modelling, thermal and exergy systems,
   heat exchangers and waste-heat recovery, concentrating solar power, catalysis for clean
   fuels and for CO2 / biomass conversion, atmospheric science, aerosols, air quality and
   greenhouse-gas monitoring, environmental / land-use / watershed / ecosystem assessment,
   and techno-economic or policy analysis tied to a specific energy technology.
   Representative titles: "Techno-economic analysis of floating solar PV plant in a
   reservoir-based hydropower station"; "Modeling of lithium nucleation and plating kinetics
   under fast charge"; "Influence of monsoons on atmospheric CO2 variability over India".
   NOT: energy-efficient buildings or smart-grid DISTRIBUTION as urban infrastructure (=>4);
   pure material synthesis with no energy application (=>2).

2. Advanced Materials & Devices
   Scope: discovery, synthesis, characterization and structure-property relationships of
   novel materials studied AS materials: nanomaterials, plasmonic and optical materials,
   polymers and polymer nanocomposites, functional coatings, ceramics, ferroelectric and
   multiferroic compounds, metamaterials and wave-engineering metastructures, organic
   optoelectronic molecules, porphyrins and coordination complexes, and biomaterials WITHOUT
   a specific clinical/therapeutic endpoint.
   Representative titles: "Photocurrent enhancement by surface plasmon resonance of gold
   nanoparticles in dye sensitized solar cells"; "Dielectric and magnetic properties of a
   multiferroic perovskite compound"; "Emergence of metadamping in a thin-walled metabeam".
   NOT: processing/joining/machining for production (=>3); materials designed for a clinical
   therapy or device (=>5); semiconductor or quantum devices (=>8).

3. Manufacturing & Industry 4.0
   Scope: manufacturing processes and production systems: metal forming, deep drawing,
   hydroforming, welding, additive manufacturing, machining and surface finishing
   (magnetorheological / magnetic-abrasive / ultrasonic-assisted), mechanical
   characterization under processing conditions, control systems and machinery dynamics,
   rotordynamics and machinery fault diagnostics, power electronics and motor drives for
   industrial machinery, textile and fiber engineering (spinning, weaving, yarn), industrial
   bioprocess / fermentation / downstream scale-up, and supply-chain and operations
   management for manufacturing and logistics.
   Representative titles: "Simulation of hydroforming of a two-wheeler fuel tank"; "Mechanism
   of surface finishing in ultrasonic-assisted magnetic abrasive finishing"; "Torque ripple
   minimization in DTC-based induction motor drive".
   Key idea: the PROCESSING of materials, not their discovery.

4. Smart & Sustainable Infrastructure
   Scope: built and civil-engineered systems at the system level: structural analysis and
   seismic / earthquake engineering, foundation and soil dynamics, geotechnics, construction
   materials durability, concrete, corrosion, solid-waste valorization and thermal
   performance of buildings, water distribution and transport networks, urban air-quality
   monitoring and forecasting, smart grids and energy distribution treated as infrastructure,
   and circular-economy practices in the built environment.
   Representative titles: "Seismic performance of self-centering BRB frames under near-field
   ground motions"; "Factors influencing ambient particulate matter in Delhi via machine
   learning"; "State-space modelling of a series-compensated long-distance transmission line".

5. Healthcare & MedTech
   Scope: disease diagnosis, treatment and monitoring, and biomedical innovation: medical
   devices and wearable / implantable sensors, prosthetics and rehabilitation, drug delivery
   and clinically-intended biomaterials and hydrogels, cancer biology and molecular oncology,
   infectious disease and virology (incl. COVID-19, tuberculosis), protein engineering and
   molecular biophysics, medical imaging and diagnostics, electrochemical biosensors and
   lab-on-chip, clinical AI and decision support, computational biomechanics and physiology,
   neuroscience and neurophysiology, and biopharmaceutical manufacturing and analytics.
   Representative titles: "Repurposing FDA-approved drugs against SARS-CoV-2 papain-like
   protease"; "Tunable macroporous hydrogels for controlled drug release"; "Wearable sensors
   for motion capture and tissue imaging".

6. Next-Gen Communication
   Scope: the physical layer and system level of communication: antenna and RF component
   design at microwave and millimeter-wave frequencies, MIMO / beamforming / relay theory and
   optimization, wireless network access, MAC protocols, traffic modelling and resource
   allocation (IoT, cellular, ad hoc), signal processing / wavelets / filtering FOR
   transmission and reception, and electromagnetic-wave, laser-plasma and plasma-wave
   interaction, wakefield generation, self-focusing and microwave-plasma phenomena.
   Representative titles: "Optimality of beamforming for a correlated MISO relay channel";
   "Analysis of GPRS radio channel access delay"; "Nonlinear interaction of an intense laser
   beam with an electron plasma wave". THIS is the single home for plasma-wave and
   electromagnetic-plasma physics.

7. AI/ML, Supercomputing & Quantum Computing
   Scope: papers whose PRIMARY contribution is the algorithm or computational method: neural
   networks and deep learning, natural language processing and information retrieval, machine
   learning methodology and generative models, classical / parallel / distributed algorithms,
   computational geometry and graph algorithms, high-performance and scientific computing,
   and quantum ALGORITHMS, quantum information and quantum computing theory. This is also the
   closest home for applied mathematics, optimization theory and dynamical-systems / nonlinear
   -dynamics methods that do not belong to another applied theme.
   Representative titles: "Scalable generative modelling for temporal interaction graphs";
   "Optimal output-sensitive parallel algorithms for upper envelopes of line segments";
   "Statistical language modeling with syntactic-semantic information".
   NOT: physical quantum or semiconductor DEVICES (=>8).

8. Quantum Technologies & Semiconductor Technology
   Scope: physical devices and their enabling materials: semiconductor thin films,
   nanostructures and heterostructures and their device physics, photodetectors, CMOS and
   nanoscale transistor engineering, memory and analog integrated circuits, quantum dots and
   colloidal nanocrystals, magnetic materials, spintronics and magnonics, photonic devices,
   quantum optics hardware, and photonic / plasmonic / fiber-optic sensing.
   Representative titles: "GaSe/Si vertical 2D/3D heterojunction for self-driven
   photodetectors"; "Anisotropic magnetic damping in beta-Ta / epitaxial-Py bilayers";
   "Spectral purity of telecom photon pairs from on-chip LNOI waveguides".
   Key idea: quantum and photonic DEVICES and MATERIALS, not algorithms (=>7).

9. Social Sciences, Humanities & Management
   Scope: economics, management and business, international business and strategy, development
   economics and social welfare, public policy, education, game theory and market/mechanism
   design, linguistics and computational linguistics for (esp. Indian) languages, design
   studies and pure humanities; ALSO library and information science and knowledge management;
   and organizational digital transformation, IT adoption and information systems. This is the
   catch-all disciplinary home for non-STEM scholarship.
   Representative titles: "Cash vs. in-kind transfers: Indian data meets theory"; "A
   characterization of Nash equilibrium for games with random payoffs"; "Dependency
   annotation scheme for Indian languages"; "Cloud computing and its application in libraries".

0. NOT A RESEARCH PAPER (unclassifiable)
   Editorials, prefaces, forewords, introductions to proceedings, front matter, tables of
   contents, author or subject indexes, book reviews, corrigenda / errata / retraction
   notices, and administrative notices that carry no research content or have no usable
   abstract. Titles like "Preface", "Editorial", "Foreword", "Erratum to ...", "Author index".

TIE-BREAK RULES (apply in order when two themes seem possible):
- Quantum "software" (algorithms, information, computation, error correction) => 7; quantum
  "hardware" (devices, dots, quantum-optics hardware, quantum materials) => 8.
- Machine learning / AI applied to another field: if the novelty is the ML method itself =>7;
  if the novelty is the application system, use that system's theme (clinical =>5,
  infrastructure/grid/air-quality =>4, manufacturing/diagnostics =>3, communication =>6,
  business/economics =>9).
- Plasma physics and electromagnetic / laser-plasma wave interaction => 6 (not 7, not 2).
- Applied mathematics, pure dynamical systems, nonlinear dynamics with no applied home => 7.
- Catalysis and chemistry FOR fuels / CO2 / energy => 1; catalysis or materials chemistry with
  no energy or clinical purpose => 2.
- A material or biomaterial made FOR a stated clinical/therapeutic use => 5; the same material
  studied only for its intrinsic properties => 2.
- Processing / joining / machining / production of a material => 3; discovery / synthesis /
  characterization of the material => 2.
- Energy generation / storage / conversion device => 1; the same treated as building or grid
  infrastructure for a city => 4.

Respond with a single character: one of 0 1 2 3 4 5 6 7 8 9. No words, no punctuation."""

_usage_lock = threading.Lock()
_usage = {"input_tokens": 0, "output_tokens": 0, "cache_write": 0, "cache_read": 0, "calls": 0}


def _add_usage(u):
    with _usage_lock:
        _usage["input_tokens"] += u.input_tokens
        _usage["output_tokens"] += u.output_tokens
        _usage["cache_write"] += getattr(u, "cache_creation_input_tokens", 0) or 0
        _usage["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0
        _usage["calls"] += 1


def paper_text(p):
    t = p["title"]
    if p.get("abstract"):
        t += "\n\nAbstract: " + p["abstract"][:1200]
    else:
        t += "\n\n(No abstract available.)"
    return t


def classify_one(p):
    prompt = "Paper:\n" + paper_text(p) + "\n\nBest-fit theme number:"
    for attempt in range(6):
        try:
            resp = _client.messages.create(
                model=MODEL,
                max_tokens=5,
                system=[{"type": "text", "text": SCOPE_BLOCK,
                         "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": prompt}],
            )
            _add_usage(resp.usage)
            txt = resp.content[0].text.strip()
            digit = next((c for c in txt if c in "0123456789"), None)
            return digit
        except (anthropic.RateLimitError, anthropic.APIStatusError, anthropic.APIConnectionError) as e:
            if attempt == 5:
                print(f"  give up on {p['id']}: {e}")
                return None
            time.sleep(min(2 ** attempt, 30))
    return None


def main():
    samples = json.loads((WORK / "samples.json").read_text(encoding="utf-8"))

    tasks = []
    for tid, papers in samples["by_theme"].items():
        for p in papers:
            tasks.append({"id": p["id"], "title": p["title"], "abstract": p["abstract"],
                          "v1_theme_id": tid})
    for p in samples["unclassified"]:
        tasks.append({"id": p["id"], "title": p["title"], "abstract": p["abstract"],
                      "v1_theme_id": None})
    print(f"papers to theme-correct: {len(tasks)}")

    out_path = WORK / "theme_corrected.json"
    results = {}
    if out_path.exists():
        results = json.loads(out_path.read_text(encoding="utf-8")).get("assignments", {})
        print(f"resuming: {len(results)} already done")

    todo = [t for t in tasks if t["id"] not in results]
    print(f"remaining: {len(todo)}")

    num_to_theme = {str(i + 1): tid for i, (tid, _) in enumerate(THEME_ORDER)}

    def flush():
        payload = {"theme_order": [tid for tid, _ in THEME_ORDER], "assignments": results,
                   "usage": _usage}
        out_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    done_since_flush = 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        fut_to_task = {ex.submit(classify_one, t): t for t in todo}
        completed = 0
        for fut in as_completed(fut_to_task):
            t = fut_to_task[fut]
            digit = fut.result()
            if digit == "0":
                v2 = "unclassifiable"
            elif digit in num_to_theme:
                v2 = num_to_theme[digit]
            else:
                v2 = "unclassifiable"  # unparseable -> treat as non-research/unknown
            results[t["id"]] = {"v1": t["v1_theme_id"], "v2": v2, "raw": digit}
            completed += 1
            done_since_flush += 1
            if done_since_flush >= FLUSH_EVERY:
                flush()
                done_since_flush = 0
                rate = completed / (time.time() - t0)
                print(f"  {completed}/{len(todo)} done ({rate:.1f}/s)", flush=True)
    flush()

    cost = round(
        _usage["input_tokens"] / 1e6 * PRICE_IN
        + _usage["output_tokens"] / 1e6 * PRICE_OUT
        + _usage["cache_write"] / 1e6 * PRICE_CACHE_WRITE
        + _usage["cache_read"] / 1e6 * PRICE_CACHE_READ,
        4,
    )
    print(f"done in {time.time()-t0:.0f}s; calls={_usage['calls']} "
          f"in={_usage['input_tokens']} out={_usage['output_tokens']} "
          f"cache_w={_usage['cache_write']} cache_r={_usage['cache_read']} "
          f"est_cost=${cost}")

    # merge cost into the shared usage tracker
    shared_path = WORK / "llm_usage.json"
    shared = {"input_tokens": 0, "output_tokens": 0, "calls": 0, "est_cost_usd": 0}
    if shared_path.exists():
        shared = json.loads(shared_path.read_text(encoding="utf-8"))
    shared["input_tokens"] += _usage["input_tokens"] + _usage["cache_write"] + _usage["cache_read"]
    shared["output_tokens"] += _usage["output_tokens"]
    shared["calls"] += _usage["calls"]
    shared["est_cost_usd"] = round(shared.get("est_cost_usd", 0) + cost, 4)
    shared["theme_correction_cost_usd"] = cost
    shared_path.write_text(json.dumps(shared, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
