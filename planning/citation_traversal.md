# Citation Traversal Loop — Planning

## Motivation

The current literature search pipeline discovers papers through keyword matching against
titles and abstracts. This misses critical evidence that is:

- Buried in methods/results sections (not surfaced by abstract screening)
- Cited in passing in a review or atlas paper without prominent abstract presence
- Part of a conceptual lineage (a classical cell biology paper cited by a modern
  transcriptomics paper to justify a cluster annotation)

The scholarly workflow this aims to replicate: a researcher reads a recent review,
finds a sentence asserting something relevant, follows the citation to the primary
evidence, assesses it, and repeats.

---

## Core Idea: Citation-Annotated Passage Retrieval

### Primary mechanism: ASTA snippet search (validated 2026-03-05)

ASTA `snippet_search` returns ~500-word body-text passages with pre-computed
`refMentions` annotations that link inline citations to Semantic Scholar corpus IDs:

```json
{
  "text": "...serous demilunes due to chemical fixation in the SLG... [55]",
  "annotations": {
    "refMentions": [
      {"start": 646, "end": 650, "matchedPaperCorpusId": "12552345"},
      {"start": 863, "end": 867, "matchedPaperCorpusId": null}
    ]
  }
}
```

This provides exactly what a JATS parser would produce — sentence-level
citation associations — but across ~45M papers (including non-OA), with no
parsing infrastructure required.

**Limitations:**
- Returns top-N passages by relevance to the query, not exhaustive extraction
- Some `matchedPaperCorpusId` values are null (unresolved)
- No forward citations (only backward refs embedded in text)

### Fallback mechanism: JATS XML parsing

JATS XML (returned by EuropePMC full text) preserves inline citation structure:

```xml
Demilune cells secrete serous proteins <xref rid="R14" ref-type="bibr">14</xref>
and express aquaporin-5 <xref rid="R22" ref-type="bibr">22</xref>.
```

Cross-referencing with the paper's `<ref-list>` resolves ref_id → DOI/PMID.

JATS parsing remains useful for **exhaustive** citation extraction from a specific
seed paper (every reference, not just passages matching a query). But it is no
longer the primary mechanism — ASTA snippet search covers the common case.

---

## Proposed Architecture

### Primary path: ASTA-based (validated)

```
[0] EuropePMC: "topic AND PUB_TYPE:review" → seed PMIDs (reviews-first)
    — or — ASTA search_papers_by_relevance → seed corpus IDs
  │
  ▼
[1] ASTA snippet_search(query, paper_ids=seeds) → passages + refMentions
  │
  ▼
[2] LLM (Haiku): score passage relevance to query
    → extract matchedPaperCorpusId from high-scoring passages
  │
  ▼
[3] ASTA get_paper(corpusId) → metadata for cited papers
  │
  ▼
[4] ASTA snippet_search(query, paper_ids=cited_papers)
    → relevance check + further refMentions
  │
  ▼
[5] Fetch full texts of confirmed relevant papers (EuropePMC or PDF)
    → add to corpus
  │
  ▼
[6] Recurse to step [1] for newly added papers (depth-limited)
  │
  ▼
[7] Embed corpus → chunk retrieval → Haiku re-rank → synthesise
```

Key advantage: Step [0] uses EuropePMC's `PUB_TYPE:review` filter (which ASTA
lacks), then hands off to ASTA for citation-annotated body-text retrieval.
Each tool does what it's best at.

### Fallback path: JATS-based (for exhaustive extraction)

```
SEED PAPER (specific PMCID, must be OA)
  │
  ▼
[1] Fetch JATS XML → parse all <xref ref-type="bibr"> tags
  │
  ▼
[2] Resolve ref_ids → paper IDs (via <ref-list> or title search)
  │
  ▼
[3] OA check → fetch full texts of resolved papers
  │
  ▼
[4] Add to corpus → standard paperqa pipeline
```

Use this when you need every citation from a specific paper, not just passages
matching a query.

### Termination conditions
- Maximum recursion depth (e.g. N=2 for most queries, N=3 for deep reviews)
- Relevance threshold: don't recurse into a paper scoring below threshold
- Corpus size cap: stop adding papers beyond a set limit
- Deduplication: track visited paper IDs across all recursion levels

---

## Components to Build

### 1. Citation traversal orchestrator (new skill)
New skill: `citation-traverse`
Arguments: `[question] [--seed-strategy reviews|specific] [--depth 2] [--max-papers 50]`

Primary path (ASTA-based):
1. Seed discovery: EuropePMC `PUB_TYPE:review` → PMIDs, or user-specified seeds
2. ASTA `snippet_search(query, paper_ids=seeds)` → citation-annotated passages
3. Extract `matchedPaperCorpusId` from high-scoring passages
4. ASTA `get_paper(corpusId)` → metadata for cited papers
5. Recurse: `snippet_search(query, paper_ids=cited_papers)`
6. Fetch full texts of confirmed relevant papers → add to `papers_fetched/`
7. Hand off to existing `paperqa` skill

Outputs augmented `papers_fetched/` corpus for the paperqa pipeline.

### 2. Passage relevance scorer (reuse existing Haiku pattern)
Haiku task per ASTA snippet (or per batch of snippets from one paper):
- Score relevance to query
- Flag which refMentions corpus IDs are worth following
- Handle null matchedPaperCorpusId (skip or attempt title-based resolution)

### 3. JATS citation-sentence parser (fallback, lower priority)
**Input**: PMCID
**Output**: list of `{sentence, citations: [{ref_id, resolved_id, title}]}`

For exhaustive extraction from a specific seed paper when ASTA snippets don't
cover the needed passages. Implementation: Python script `parse_jats_citations.py`.

Only needed when:
- The seed paper is OA (JATS available) AND
- You want every citation, not just those in query-relevant passages AND
- ASTA snippet search misses important refs (e.g. cited in a section that
  doesn't match the query terms)

---

## Validation Experiment

### Goal
Demonstrate that citation traversal recovers primary evidence that keyword search misses.

### Topic: Salivary gland demilune cells
Modern scRNA-seq atlas papers annotate clusters by mapping to classical
histological descriptions, citing 1960s-1980s cell biology papers. These
classical papers are invisible to keyword search but are exactly the primary
evidence a researcher needs.

### Preliminary validation (2026-03-05)

ASTA snippet search was tested on this topic with promising results:

**Unscoped search** (`snippet_search("serous demilune cell markers salivary gland")`):
- 20 snippets returned, top scores 0.50–0.57
- Key finding: Maruyama et al. (CorpusId:5322044) — **Dcpp1** identified as a
  specific demilune marker, **Sox2** co-expressed in serous demilune cells
- BPIFB1 localised to serous demilunes (Musa et al.)
- refMentions returned resolved corpus IDs for cited papers

**Reviews-first hybrid** (EuropePMC `PUB_TYPE:review` → ASTA `paper_ids` scoped):
- 5 reviews found via EuropePMC; ASTA snippet_search scoped to those PMIDs worked
- Top snippet (Ungureanu et al., score 0.329): demilune text with refMention
  `matchedPaperCorpusId: "12552345"` (Amano et al., the anatomy review)
- Confirms the EuropePMC → ASTA hybrid pattern is viable

### Remaining protocol

**Step 1 — Keyword baseline**
Run current `literature-search` skill on the topic. Record papers found,
claims, and citations.

**Step 2 — ASTA citation traversal**
From the preliminary results:
1. Take top refMentions corpus IDs from the snippet search
2. `get_paper` for metadata
3. `snippet_search(query, paper_ids=[cited_papers])` — depth=1 traversal
4. Fetch full texts of confirmed relevant papers

**Step 3 — Compare**
Run `paperqa` over the augmented corpus. Compare new papers discovered,
evidence quality, and answer specificity vs. keyword baseline.

### Success criteria
- At least 1 primary evidence paper recovered that was not in the keyword search results
- That paper contains experimental data (not just another review)
- The synthesised answer is more specific or better evidenced

### Scale
Deliberately small: 1-2 seed papers, depth=1, ~10-20 additional papers.

---

## Dependencies and Risks

| Dependency | Status | Risk |
|---|---|---|
| ASTA MCP operational | **Working** (validated 2026-03-05) | Low — snippet_search, get_paper, search all tested |
| ASTA snippet_search refMentions coverage | Validated — returns corpus IDs for many refs | Low-Medium — some refs return null, need fallback |
| ASTA rate limit | 10 calls/second | Low — sufficient for depth-limited traversal |
| EuropePMC PUB_TYPE:review filter | Working | Low — reliable metadata |
| EuropePMC JATS full text available | Works for OA papers | PMC-only; only needed for JATS fallback path |
| ASTA `get_paper` resolves all ref IDs | Good coverage for established literature | Low — tested on biomedical corpus IDs |

---

## Relationship to Existing Pipeline

Citation traversal is additive — it populates `papers_fetched/` with more (and better
targeted) papers. The existing `paperqa` skill then runs unchanged over the augmented
corpus. The embedding cache invalidation issue (per-set keying) is a mild cost here:
each traversal level adds papers and busts the cache. Acceptable at validation scale;
worth addressing with per-paper caching before production use.
