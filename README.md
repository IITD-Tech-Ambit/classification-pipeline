# Classification Pipeline

Architecture and planning docs for the **Research Ambit** paper classification system at IIT Delhi.

The published document describes a quality-first, self-hosted pipeline for classifying ~70k Scopus papers into a fixed 9-theme taxonomy, with domains, subdomains, and topics induced bottom-up from the corpus. It covers data hygiene, embedding foundations, theme assignment, taxonomy induction, a multi-stage classification funnel, evaluation, and rollout on a two-laptop GPU cluster (no external LLM APIs).

## Live document

**https://iitd-tech-ambit.github.io/classification-pipeline/**

## Repository layout

| Path | Purpose |
|---|---|
| `docs/index.html` | Architecture document served by GitHub Pages |
| `.github/workflows/pages.yml` | Deploys `docs/` to GitHub Pages on push to `main` |

## Corpus & outcome

- **Corpus:** 69,677 Scopus papers (`researchmetadatascopus` in `research_ambit`)
- **Fixed layer:** 9 human-approved thematic areas
- **Generated layers:** Domains, subdomains, and topics rebuilt from the corpus
- **Target output:** `classification_v2` — primary path, secondary themes, topics, confidence, and provenance
