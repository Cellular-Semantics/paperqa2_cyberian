# Scaling the Literature Search Pipeline

## Current architecture ("training wheels")

The pipeline is a fixed single-pass linear flow:

```
3 queries → top 15 papers → embed all → top 15 chunks → rank → answer
```

### Hard limits (all set in SKILL.md)

| Stage | Current limit | Where |
|---|---|---|
| EuropePMC sub-queries | 3 | literature-search SKILL.md |
| Papers fetched | cap 15 | literature-search SKILL.md |
| Chunks retrieved (k) | 15 | both skills |
| Chunks kept after re-ranking | top 10 | both skills |
| Synthesis input | 10 × 2–3 sentence summaries | both skills |

These limits are appropriate for initial development and testing, not for
serious literature reviews.

---

## What scales well already

### Haiku re-ranking (RCS)
Each chunk is scored in an isolated Task subagent (5–8 in parallel). Each sees
only one ~500-word chunk plus the question. This scales arbitrarily — 15 chunks
or 500 chunks, the per-chunk cost is identical and fully parallelisable.

This pattern directly mirrors what PaperQA2 calls **Reranking and Contextual
Summarization (RCS)** — the step that most differentiates PaperQA2 from simpler
RAG systems (Skarlinski et al. 2024). One difference: the PaperQA2 paper found
that using the *best available* model (not a cheaper one) for RCS improved
performance. Our current Haiku choice optimises for cost; this is a quality
trade-off worth revisiting at scale.

### Synthesis
Synthesis operates on RCS summaries (2–3 sentences each), not raw text.
With a top-N cap (currently 10), context size at synthesis is bounded regardless
of corpus size. **This stage already scales.**

### Disk-based embedding cache
`retrieve_chunks.py` caches the fully-indexed `Docs` object as a gzip-pickled
file in `.paperqa_cache/`. The cache key is SHA-256 over sorted
`(filename, size, mtime_ns)` for all papers plus the embedding model name.
On cache hit, all papers are skipped and only the retrieval query runs.

---

## What breaks at scale

### 1. Per-set cache invalidation
The cache covers the entire paper set as a single key. Adding one paper
invalidates the whole cache — all papers are re-embedded from scratch.
At 15–30 papers this costs seconds. At 500+ papers this becomes the
dominant cost per session.

Note: PaperQA2's production infrastructure uses **MongoDB request caching +
Redis object caching** (Skarlinski et al. 2024, §8). The local pickle cache
in the open-source library mirrors the intent but not the granularity. A
per-paper embedding store (e.g. FAISS with sidecar metadata) would be the
open-source equivalent.

### 2. Single-stage retrieval degrades at scale
Embedding similarity over thousands of chunks produces noisy top-k results.
A paper tangentially related to the query but with many chunks can dominate.

PaperQA2 addresses this with **MMR (Maximum Marginal Relevance)** pre-filtering
(`docs_index_mmr_lambda`) to promote source diversity before the RCS step.

### 3. Paper cap is arbitrary
The 15-paper cap is a SKILL.md constant with no technical grounding. The
fetch, embed and cache steps handle arbitrary corpus sizes. The right limit
is determined by cost and coverage, not a fixed number.

### 4. Query decomposition is open-loop
3 sub-queries are generated once from the question. If they miss an angle,
nothing corrects for it. PaperQA2 addresses this by treating retrieval as a
**multi-step agent task**: the agent can revise search parameters, generate
new queries, and iterate — rather than executing a fixed plan.

### 5. No paper-level relevance screen
Papers are selected purely by EuropePMC keyword ranking, with no relevance
filtering until the chunk level. A highly relevant paper ranked 16th in
EuropePMC results is permanently excluded.

---

## Citation traversal — already in the library

The most significant finding from reading the PaperQA2 paper: **citation
traversal (`citations_traversal`) is already implemented as an agentic tool
in the paperqa library** (Skarlinski et al. 2024, §8.1.1).

Our current skill bypasses this entirely by calling `retrieve_chunks.py`
directly rather than using the library's agentic interface.

### How the library's citation traversal works

- Starts from papers whose RCS scores exceed a threshold (default ≥ 8/10)
- Calls **Semantic Scholar + Crossref APIs** for past references and future citers
- Uses an **overlap filter**: papers cited by multiple high-scoring source papers
  are prioritised over those cited by only one
- Default overlap fraction α = 1/3; traversal limit ℓ = 12 papers
- Both directions: backward (past references) and forward (future citers)

This is meaningfully different from our manually prototyped approach
(see [`citation_traversal_experiment.md`](citation_traversal_experiment.md)):

| Aspect | Our prototype | Library tool |
|---|---|---|
| Starting point | User-specified seed paper | High-scoring RCS chunks (emergent) |
| Citation resolution | JATS XML + EuropePMC title search | Semantic Scholar + Crossref APIs |
| OA constraint | Requires PMC JATS XML | Works on any paper with a DOI |
| Direction | Backward only (references) | Both backward and forward |
| Overlap filtering | Not implemented | Built in (α = 1/3) |
| Paper source | EuropePMC JATS | Semantic Scholar (broader coverage) |

### Implication for our roadmap

Before building a custom citation traversal skill, the priority should be to
**expose and use the library's native `citations_traversal` tool** within our
agentic pipeline. This requires moving from the current direct
`retrieve_chunks.py` call to using paperqa's full agentic interface.

The ASTA Semantic Scholar MCP (pending API key) is directly complementary:
Semantic Scholar is the same backend the library uses for citation resolution.

---

## PDF parsing — Grobid vs. PyMuPDF

Our current setup uses paperqa's default parser (PyMuPDF/pypdf), which
extracts plain text but does not reliably parse citations or section structure.

PaperQA2's production runs use **Grobid** (`parsing_configuration.ordered_parser_preferences=grobid`), which:
- Reliably parses sections, tables, and **inline citations** from any PDF
- Enables section-based chunking (one chunk per section) rather than
  sliding-window character chunks
- Removes reference sections from chunks (saving ~30% tokens per paper:
  mean 12,247 tokens PyMuPDF → 8,903 tokens Grobid)
- Works on any PDF, not just OA PMC papers — this directly addresses the
  OA wall we encountered in the citation traversal experiment

Grobid is not included in the core paperqa package; it requires a running
Grobid server (`https://github.com/kermitt2/grobid`). Setting this up would
give us citation-aware parsing for any paper, independent of JATS availability.

---

## ASTA Semantic Scholar snippet search (validated 2026-03-05)

The Semantic Scholar MCP (`snippet_search`) searches ~500-word body-text
passages across ~45M papers (the peS2o corpus — open-access full texts from
Semantic Scholar, **broader than PubMed OA alone**) without downloading papers.

Validated as operational with three capabilities:

### As a discovery layer
Snippet search finds papers where the relevant content is in the body —
methods, results, discussion — not in the abstract. Invisible to EuropePMC
keyword ranking, surfaced by semantic body-text search with a domain-specialized
cross-encoder reranker.

### As a fast relevance gate before download
```
EuropePMC search → candidate PMIDs
  → snippet_search scoped to candidates → passage-level relevance scores
  → download only high-scoring papers
  → embed + chunk retrieval as normal
```

### As a citation traversal mechanism (key finding)
Snippet search returns `refMentions` annotations with pre-resolved Semantic
Scholar corpus IDs for inline citations. Combined with EuropePMC's
`PUB_TYPE:review` filter, this enables a reviews-first citation traversal
workflow without any JATS parsing:

```
EuropePMC: "topic AND PUB_TYPE:review" → PMIDs
  → ASTA snippet_search(query, paper_ids=PMIDs) → passages + refMentions
  → extract matchedPaperCorpusId from high-scoring passages
  → ASTA get_paper(corpusId) → metadata
  → recurse snippet_search on cited papers
```

**Status:** Working. Rate limit: 10 calls/second (sufficient for depth-limited
traversal). Coverage confirmed for biomedical literature including salivary
gland cell biology.

---

## Proposed scaled architecture

```
query decomposition (iterative, agentic)
  │
  ├── EuropePMC search (PUB_TYPE:review + primary, multiple queries)
  ├── ASTA snippet search (body-text discovery)       ← requires ASTA API key
  │
  ▼
abstract/title screen (Haiku, cheap, parallelised)
  │
  ▼
fetch full texts (EuropePMC JATS for OA; Grobid PDF parse for non-OA)
  │
  ▼
embed + chunk (per-paper cache; FAISS index)           ← replace per-set pickle
  │
  ▼
gather evidence (top-k MMR retrieval → RCS)
  │
  ▼
citation traversal (library native tool via Semantic Scholar + Crossref)
  │
  ▼
re-gather evidence from traversed papers
  │
  ▼
synthesise answer
```

---

## Discovery channels — complementary, not competing

Keyword search, snippet search, and citation traversal address the same root
problem (relevant papers missed) via different mechanisms:

| Strategy | Finds | Misses | Status |
|---|---|---|---|
| EuropePMC keyword | Papers with matching titles/abstracts | Body-text evidence, older cited papers | Working |
| ASTA snippet search | Body-text evidence in ~45M papers **+ citation refs** | Non-indexed papers, very recent papers | **Working** |
| ASTA snippet tracing (reviews-first) | Primary evidence cited in review passages | Refs not in query-relevant passages | **Working** |
| Library citation traversal | Papers in co-citation neighbourhood | Papers not connected to any seed | In library, bypassed |
| JATS exhaustive extraction | All references from a specific OA paper | Non-OA papers | Prototyped |

A mature pipeline uses all of these as complementary discovery channels feeding
the same corpus and embedding cache. ASTA snippet search now serves dual duty:
discovery AND citation traversal.

---

## Prioritised next steps

Updated 2026-03-05 after ASTA validation.

1. **ASTA-based citation-traverse skill** — implement the validated
   EuropePMC → ASTA snippet_search(paper_ids) → refMentions → recurse
   pattern (see `citation_traversal.md` for architecture)
2. **Expose library citation traversal** — switch from `retrieve_chunks.py`
   direct call to using paperqa's full agentic interface with
   `citations_traversal` tool enabled
3. **Per-paper embedding cache** — replace per-set pickle with FAISS index to
   eliminate full re-index on corpus growth
4. **Grobid setup** — enables citation-aware parsing of non-OA PDFs; lower
   priority now that ASTA covers non-OA for snippet-based traversal, but still
   valuable for chunking quality and section-based parsing
5. **Raise paper caps** — once discovery and caching are more robust, remove
   the arbitrary 15-paper limits in SKILL.md

---

## References

Skarlinski MD et al. (2024) *Language agents achieve superhuman synthesis of
scientific knowledge.* arXiv:2409.13740.
[PDF: Skarlinski_et_al_2024_PaperQA2.pdf]
