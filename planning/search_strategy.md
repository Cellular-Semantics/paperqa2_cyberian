# Search Strategy — Query Decomposition, Citation Traversal, and Scenarios

## 1. Query generation: fixed pipeline vs. agentic iteration

### Our current approach
The skill pre-generates all queries upfront, before any searching begins:

1. Main agent generates **3 keyword queries** covering different angles
2. All 3 run **in parallel** against EuropePMC
3. Results deduplicated, capped at 15 papers
4. Fixed pipeline terminates — no iteration, no feedback

Queries are generated from the question alone, with no knowledge of what
search will return. Once generated, they cannot be revised.

### PaperQA2's approach
Search is a tool that an agent calls iteratively. The agent is given the
question plus a prompt that includes its current state:

> *"Search for papers, gather evidence, collect papers cited in evidence then
> re-gather evidence, and answer. If you do not have enough evidence:*
> *Search for more papers (preferred) / Collect cited papers (preferred) /
> Gather more evidence using a different phrase.*
> *Current status of evidence/papers/cost: {status}"*

Each Paper Search call generates **one query** (with optional date range),
fetches 12 candidates from Semantic Scholar, parses and embeds them. The agent
then inspects evidence quality and decides whether to search again, traverse
citations, or generate an answer.

### The ablation result
PaperQA2 explicitly tested a **"No Agent"** baseline — hardcoded sequence of
`paper_search → gather_evidence → generate_answer` with no iteration — and
found significantly lower accuracy (p = 0.015):

> *"We attribute the performance difference to the agent's better recall
> because it can return to and change keyword searches after observing the
> amount of relevant papers it finds."*

**Our current pipeline is equivalent to their No Agent baseline.**

### Comparison

| Aspect | PaperQA2 | Our pipeline |
|---|---|---|
| Queries | One at a time, iteratively | 3 upfront, in parallel |
| Query revision | Yes — based on evidence found | No |
| Stopping condition | Agent decides from evidence quality | Fixed pipeline always completes |
| Agent sees own state | Yes — `{status}` at every step | No |
| Search backend | Semantic Scholar | EuropePMC |
| Papers per search | 12 | 15 total (3 queries combined) |
| Date range support | Yes | No |

---

## 2. Citation traversal: two distinct strategies

Both PaperQA2 and our prototyped approach use citation graphs to discover
additional papers, but they solve different problems.

### Strategy A — Library `citations_traversal`: corpus expansion by co-citation

**Trigger:** Papers whose RCS score ≥ 8 become traversal seeds (D_prev).

**Mechanism:**
1. Semantic Scholar + Crossref APIs called for each seed paper
2. Returns full reference lists (backward) and future citers (forward)
3. **Overlap filtering:** papers cited by multiple seeds are prioritised
   - Threshold θo = ⌈α × |D_prev|⌉, default α = 1/3
   - With 3 seeds: any paper cited by ≥1 seed passes; with 6 seeds: ≥2
4. Within a bin, ties broken by Semantic Scholar citation count
5. Hard limit of 12 traversed papers
6. Traversed papers go through the full pipeline: parse → chunk → embed → RCS

**What it knows:** Which papers are in the citation neighbourhood of
high-scoring papers. It does NOT know which sentence cited which paper or why.

**Goal:** Find more papers likely to be relevant. A statistical co-citation
signal — papers cited by multiple independently relevant sources are
probably also relevant.

**Limitation:** Follows ALL citations from high-scoring papers indiscriminately.
A background reference cited in passing is treated the same as a primary
evidential citation.

### Strategy B — ASTA snippet-based claim tracing (validated 2026-03-05)

**Trigger:** User-specified seed paper(s), or high-scoring papers from initial search,
or reviews found via EuropePMC `PUB_TYPE:review`.

**Mechanism:**
1. Identify seed papers (EuropePMC review search, or user-specified, or top search results)
2. ASTA `snippet_search(query, paper_ids=seeds)` → body-text passages with
   `refMentions` annotations containing resolved `matchedPaperCorpusId`
3. LLM scores passage relevance; extracts corpus IDs from high-scoring passages
4. ASTA `get_paper(corpusId)` → metadata for cited papers
5. Recurse: `snippet_search(query, paper_ids=cited_papers)` at depth N

**What it knows:** Which specific passage made which specific claim, and
which paper was cited as evidence — with corpus IDs pre-resolved by
Semantic Scholar.

**Goal:** Trace evidential chains behind assertions. Semantic evidence signal.

**Key advantage over JATS approach:** Works on ~45M papers (not just OA),
no parsing infrastructure required, citation IDs are pre-resolved.

**Limitation:** Returns only query-relevant passages (not exhaustive extraction).
Some `matchedPaperCorpusId` values are null. Depth-limited to avoid
combinatorial explosion. Rate limit: 10 calls/second.

### Strategy C — JATS exhaustive extraction (fallback)

**Trigger:** Need every citation from a specific OA seed paper, regardless of
query relevance.

**Mechanism:** Fetch JATS XML → parse all `<xref ref-type="bibr">` → resolve
via `<ref-list>` or title search → OA check → fetch.

**Goal:** Complete reference graph extraction when ASTA's query-scoped
snippets miss important refs in sections that don't match search terms.

**Limitation:** OA-only (requires JATS XML or Grobid). Prototyped but lower
priority now that ASTA covers the common case.

### Comparison

| Aspect | Library traversal (A) | ASTA snippet tracing (B) | JATS exhaustive (C) |
|---|---|---|---|
| Starting point | High-scoring RCS chunks | Seed papers (reviews, user-specified) | Specific OA PMCID |
| What it follows | All citations from high-scoring papers | Cited refs in query-relevant passages | Every citation in paper |
| Relevance signal | Statistical (co-citation overlap) | Semantic (passage context + query) | None (exhaustive) |
| Direction | Both backward and forward | Backward (refs in text) | Backward (references) |
| Citation resolution | Semantic Scholar + Crossref | Pre-resolved corpus IDs (ASTA) | JATS ref-list + title search |
| OA constraint | None (uses DOIs) | **None** (~45M papers) | JATS required (OA only) |
| Paper type filtering | No | Yes (via EuropePMC → paper_ids) | N/A (single paper) |
| Implementation status | In library, bypassed | **Validated** (2026-03-05) | Prototyped |

### These are complementary, not competing

- **Library traversal (A)** expands the corpus broadly — improves **recall**
- **ASTA snippet tracing (B)** follows specific cited claims — improves **evidence quality**
  and enables a **reviews-first workflow** (EuropePMC PUB_TYPE → ASTA paper_ids)
- **JATS exhaustive (C)** extracts every reference from one paper — for **completeness**
  when ASTA's query-scoped snippets miss important refs

For a serious literature review:
- Library traversal on any high-scoring paper to ensure coverage
- ASTA snippet tracing on seed reviews to follow citation chains
- JATS exhaustive only when a specific seed needs complete reference extraction

---

## 3. Discovery channels — complementary, not competing

Four independent discovery mechanisms, each finding what the others miss:

| Channel | Finds | Misses | Status |
|---|---|---|---|
| EuropePMC keyword search | Papers with matching titles/abstracts | Body-text evidence; older cited papers | Working |
| EuropePMC `BODY:`/section search | OA papers where entity appears in full text | Non-OA papers; relevance ranking is BM25 only | Working |
| ASTA snippet search | Body-text evidence in any indexed paper (~45M) **+ inline citation refs** | Non-indexed papers; very recent papers | **Working** (validated 2026-03-05) |
| ASTA snippet search (paper_ids scoped) | Citation-annotated passages from specific papers (e.g. reviews) | Only returns query-relevant passages, not exhaustive | **Working** (validated 2026-03-05) |
| Library citation traversal | Papers in co-citation neighbourhood of relevant papers | Papers disconnected from any high-scoring seed | In library, currently bypassed |
| JATS claim tracing | Exhaustive citation extraction from a specific OA paper | Non-OA papers without Grobid; uncited evidence | Prototyped (see experiment doc) |

### EuropePMC full-text field search

EuropePMC indexes ~6.5M open-access full texts and exposes section-level
field codes usable in any query via the same REST API artl-mcp already calls:

| Field | Searches |
|---|---|
| `BODY:` | Full article body text |
| `METHODS:` | Materials & Methods |
| `RESULTS:` | Results section |
| `DISCUSS:` | Discussion |
| `INTRO:` | Introduction |
| `FIG:` | Figure captions |
| `TABLE:` | Tables |

Example query in artl-mcp `search_europepmc_papers`:
```
BODY:"demilune" AND BODY:"serous acini" AND PUB_TYPE:research-article
```

**Coverage:** OA papers only (`IN_EPMC:y`). This is the same constraint as
JATS XML retrieval — non-OA papers are invisible to `BODY:` search.

**Ranking:** BM25 keyword relevance, not semantic. Unlike ASTA's cross-encoder
reranker, there is no passage-level relevance score — results are ranked by
term frequency in the full text. A paper that mentions a term once in passing
may rank above one where it is central.

**Available now:** No API key required. Can be used immediately by adding
field-prefixed terms to the keywords string in artl-mcp calls.

**vs. ASTA snippet search:**
- EuropePMC `BODY:` returns paper-level records; ASTA returns 500-word passage snippets
- ASTA covers ~45M papers (including non-OA); EuropePMC full-text is ~6.5M OA only
- ASTA relevance scoring is semantic (cross-encoder); EuropePMC is lexical (BM25)
- For a rare biomedical term, both will find the same OA papers; ASTA additionally
  finds non-OA papers and ranks by passage relevance rather than document frequency

---

## 4. Scenario mapping

Three scenarios from compact to body-text-only relevance:

- **S1:** Compact literature, entities in titles/abstracts, easy to find
- **S2:** Large literature, entities in titles/abstracts, but too many to cap arbitrarily
- **S3:** Key papers missed because relevant entities only appear in full text

| Capability | S1 | S2 | S3 |
|---|---|---|---|
| **Query generation** | | | |
| Fixed 3-query pipeline (current) | ✅ sufficient | ⚠️ no iteration | ❌ can't adapt to thin results |
| Agentic iterative search | optional | ✅ essential | ✅ essential |
| `PUB_TYPE:review` seed filter | optional | ✅ good seed strategy | ✅ good seed strategy |
| Date range in queries | optional | ✅ useful | ✅ useful |
| **Paper discovery** | | | |
| EuropePMC keyword search | ✅ sufficient | ⚠️ too many to cap | ❌ misses key papers |
| EuropePMC `BODY:` field search | optional | ⚠️ complementary | ✅ available now (OA only) |
| Haiku abstract screening | not needed | ✅ essential | ⚠️ helps, but abstracts still miss |
| ASTA snippet search | optional | ⚠️ complementary | ✅ **essential** (working) |
| **Citation traversal** | | | |
| Library traversal (co-citation) | optional | ✅ expands coverage | ⚠️ only if seed found |
| ASTA snippet tracing (reviews-first) | ✅ evidence quality | ✅ evidence quality | ✅ secondary discovery |
| JATS exhaustive extraction (fallback) | optional | optional | ⚠️ OA only, lower priority |
| **Parsing and indexing** | | | |
| PyMuPDF (current default) | ✅ sufficient | ✅ sufficient | ⚠️ no citation extraction |
| Grobid PDF parsing | not needed | ⚠️ for non-OA | ✅ essential for non-OA |
| Per-set pickle cache (current) | ✅ sufficient | ⚠️ re-indexes on any change | ⚠️ re-indexes on any change |
| Per-paper FAISS cache | not needed | ✅ essential | ✅ essential |
| **Interface** | | | |
| `retrieve_chunks.py` direct call | ✅ sufficient | ❌ bypasses all agentic tools | ❌ bypasses all agentic tools |
| Library agentic interface | optional | ✅ essential | ✅ essential |

### Key observations

**S1 → S2 transition:** The bottleneck shifts from discovery to selection.
The main need is iterative agentic search + abstract screening to filter
hundreds of candidates. Library citation traversal adds incremental value.

**S2 → S3 transition:** A qualitative change. Statistical and keyword-based
discovery methods fail fundamentally. ASTA snippet search is the only
mechanism that can find papers where the entity appears only in body text.
JATS claim tracing becomes a secondary discovery mechanism (following
citations from the few papers that DO mention the entity in text).

---

## 5. Query planning — a missing layer

### The problem

Both PaperQA2 and our pipeline assume the input is already a clean, focused
research question. Real usage is messier: a biologist pastes a paragraph
describing their project, a question embedded in context, or multiple tasks at
once. Neither system has any principled mechanism to decompose this into
effective search queries.

PaperQA2 hopes the LLM infers good keywords from whatever is in context.
Our skill applies the 3-query decomposition instruction to `$ARGUMENTS`
verbatim. If the argument is free text, query quality is unpredictable.

What's missing is an explicit **query planning step** before any searching
begins.

### AI2 Paper Finder — a worked example

The Allen Institute's Paper Finder uses a structured **query analyser** that
breaks natural language queries into components before searching
([blog post](https://allenai.org/blog/paper-finder)):

- **Intent classification** — specific paper lookup vs. set of papers on a topic
- **Metadata criteria** — author names, venues, time ranges, structured attributes
- **Semantic requirements** — core conceptual content, broken into independent
  sub-criteria evaluated separately before combination
- **Quality modifiers** — terms like "recent", "classic", "central", "popular"
  that guide result prioritisation

A **query planner** then routes to specialised sub-flows: specific paper search,
semantic search with metadata constraints, pure-metadata queries, or
author-focused search.

The key insight is the "mini breakthrough" they describe: breaking semantic
requirements into **separate sub-criteria evaluated independently** before
combination. This allows nuanced matching of multi-part information needs —
exactly the case when a biologist asks about "demilune cell markers in mouse
submandibular gland in the context of Sjögren's syndrome".

### What a query planner for our use case would look like

```
raw input (arbitrary text)
  │
  ▼
Query analyser (LLM step, structured output)
  ├── entities: [cell types, genes, species, diseases, techniques, ...]
  ├── sub-questions: [Q1, Q2, Q3, ...]
  ├── quality modifiers: [recent?, review?, primary evidence?]
  ├── temporal scope: [year range or open]
  └── intent: [discovery | specific paper | evidence for claim]
  │
  ▼
Query planner (routes per sub-question)
  ├── Q1 → EuropePMC keyword + PUB_TYPE:review (broad discovery)
  ├── Q2 → ASTA snippet search (entity in body text only)
  └── Q3 → citation traversal from known seed paper
```

### Biomedical-specific considerations

Biomedical literature has particular terminological challenges that generic
query analysers don't handle:

- **Synonym expansion**: demilune = serous demilune = "crescentic cell";
  AQP5 = aquaporin-5 = aquaporin 5; the same gene may have multiple symbols
- **Classical vs. modern terminology**: a classical histology term may not
  appear in recent single-cell papers which use cluster IDs or marker genes
- **Species specificity**: mouse and human literature may use different terms
  for the same structure
- **Ontology grounding**: cell type names can be resolved to Cell Ontology
  terms, which provide canonical synonyms and related terms automatically

This suggests the query analyser for our use case should include a
**biomedical entity normalisation step** — potentially using a resource like
the Cell Ontology, Gene Ontology, or MeSH — before generating search queries.

### Status

Not implemented. Both systems currently leave query formulation entirely to
LLM intuition. Treating query planning as an explicit structured step,
inspired by AI2 Paper Finder's architecture, is a meaningful improvement
opportunity — particularly for Scenario 3, where the right search strategy
(snippet search, citation traversal) depends on correctly identifying what
kind of entities and evidence are being sought.

---

## 6. OpenScholar — architecture and relation to ASTA MCP

### What OpenScholar is

OpenScholar (Asai et al., Nature 2026; DOI:10.1038/s41586-025-10072-4) is
an Allen AI + UW system for scientific literature synthesis. It outperforms
GPT-4o (+6.1%), PaperQA2 (+5.5%) and in expert evaluation beats human
annotators (51–70% win rate) on ScholarQABench.

The system likely underlies the ASTA MCP endpoint
(`https://asta-tools.allen.ai/mcp/v1`). Both are Allen AI products and the
OpenScholar datastore (OSDS) is the corpus being queried by
`snippet_search`.

### Architecture

Three components:

**Datastore (OSDS)**
- 45 million scientific papers with precomputed dense embeddings
- 236 million passage embeddings (~500-word passages)
- Built on the peS2o corpus (open-access full texts from Semantic Scholar)
- Includes biomedicine, computer science, physics, neuroscience

**Retriever**
- Bi-encoder trained specifically on peS2o (domain-specialized)
- Cross-encoder reranker fine-tuned on synthetic data generated by
  Llama-3-70B-Instruct scoring passage relevance 1–5 against peS2o queries
- Meta-filtering at reranking: (1) max 3 passages per paper (source
  diversity); (2) normalized citation counts incorporated into relevance score
  (promotes well-cited papers over obscure ones)

**Generator LM**
- OpenScholar-8B: Llama 3.1 8B fine-tuned with training data from the
  inference pipeline
- OpenScholar-GPT-4o: GPT-4o as generator (higher performance, higher cost)

### Self-feedback inference loop

This is OpenScholar's key architectural innovation over standard RAG:

```
input x
  │
  ▼
Retriever → top-N passages P (bi-encoder + cross-encoder + meta-filter)
  │
  ▼
Generator LM
  ├── produces initial response y₀ (with inline citation markers)
  └── generates feedback sentences F = {f₁, f₂, f₃} (max 3)
       e.g. "The answer only includes empirical results on QA tasks.
             Add results from other task types."
  │
  For each fₖ that identifies missing content:
    fₖ → LM generates retrieval query qₖ
    qₖ → retrieve extra passages → append to P
    P updated → LM generates revised response yₖ
  │
  ▼
Citation verification (each citation checked against source passage)
  │
  ▼
Final response with verified inline citations
```

The feedback sentences are **free natural language** — not a predefined
checklist. The LM decides what to say about coverage, organization, or
missing evidence. If a feedback sentence implies retrieval is needed, it also
generates the query. Up to 3 refinement iterations.

### Comparison with PaperQA2's agentic approach

Both are iterative, but the mechanism differs:

| Aspect | OpenScholar | PaperQA2 |
|---|---|---|
| Iteration driver | LM generates explicit feedback sentences | Agent observes evidence quality (`{status}`) |
| Retrieval trigger | Natural language feedback → LM generates query | Agent decision: search more / traverse citations |
| Max iterations | Fixed (max 3 feedback sentences) | Agent-determined (until enough evidence) |
| Citation verification | Explicit post-generation step | Not described |
| Source diversity | Meta-filter: max 3 passages per paper | MMR (`docs_index_mmr_lambda`) |
| Datastore | 45M papers, 236M embeddings (OSDS) | Semantic Scholar (live API) |
| Cost | Orders of magnitude cheaper than PaperQA2 | High (many LLM calls) |

### PaperQA2 weakness identified by OpenScholar

> *"responses often rely on only one or a few papers, summarizing each
> retrieved snippet individually. This leads to limited coverage"*

The max-3-passages-per-paper meta-filter directly addresses this — it
forces source diversity at the retrieval stage rather than relying on the
LM to synthesize across papers.

### Implications for our pipeline

**ASTA `snippet_search` is probably querying OSDS.** This means:

1. **Coverage is good for peS2o-indexed papers** — open-access full texts
   across all major scientific domains, including biomedicine. Not every
   paper is indexed (non-OA, very recent papers will be missing), but
   coverage of established literature is likely strong.

2. **Body-text search works** — passages come from full text (methods,
   results, discussion), not just abstracts. This is the key advantage over
   EuropePMC keyword search for Scenario 3.

3. **The cross-encoder reranker is domain-specialized** — snippet_search
   relevance scores are not generic semantic similarity; they reflect
   scientific domain-specific relevance as scored by the trained reranker.

4. **Citation counts are in the relevance signal** — well-cited, established
   papers are boosted. This is useful for finding seminal references but may
   underweight very recent papers.

5. **Self-feedback loop is not exposed via the MCP** — we get retrieval
   results, not the full inference loop. To benefit from iterative refinement,
   we would need to implement our own feedback-driven re-retrieval, or
   use the agentic interface to call snippet_search multiple times with
   refined queries (which is exactly what PaperQA2's agent does).

### What a self-feedback loop for our pipeline would look like

The OpenScholar pattern can be approximated in our agentic interface:

```
1. Search (EuropePMC + ASTA snippet_search) → initial corpus
2. Gather evidence (RCS) → initial synthesis draft
3. Synthesis LM generates feedback sentences:
   "Coverage of X is missing. Search for Y."
4. For each feedback → generate retrieval query → EuropePMC / snippet_search
5. Add new papers to corpus → re-gather evidence → revise synthesis
6. Repeat (2–3 cycles)
7. Citation verification (each claim traced to source chunk)
```

This is not currently implemented but is a natural next step after
switching to the agentic interface (Section 7, Priority 2).

---

## 8. Prioritised path

Updated 2026-03-05 after validating ASTA MCP (snippet_search, get_paper,
search_papers_by_relevance all operational; refMentions confirmed working).

1. **ASTA snippet search as discovery + citation traversal** — **working now**;
   dual-purpose tool: body-text discovery (S3) AND citation-annotated passage
   retrieval for reviews-first traversal. Replaces JATS parsing for the common case.
2. **EuropePMC `BODY:` field search** — available now via artl-mcp, no key
   needed; add `BODY:"term"` to queries for immediate S3 improvement (OA only);
   complementary to ASTA (lexical vs. semantic, different coverage)
3. **ASTA-based citation-traverse skill** — implement the validated
   EuropePMC PUB_TYPE:review → ASTA snippet_search(paper_ids) → refMentions
   → get_paper → recurse pattern as a new skill
4. **Switch to agentic interface** — single change that unlocks iterative
   search, library citation traversal, and agent-observable state simultaneously;
   directly addresses the No Agent accuracy gap
5. **Per-paper FAISS cache** — needed before corpus grows beyond ~50 papers
6. **Grobid setup** — removes OA constraint from JATS exhaustive extraction;
   also improves chunking quality (section-based) and reduces token use (~30%);
   lower priority now that ASTA covers non-OA papers for snippet-based traversal
7. **JATS exhaustive extraction** — fallback for when ASTA query-scoped
   snippets miss important refs; only for specific OA seed papers
8. **Raise paper caps** — once discovery and caching are robust, remove
   arbitrary 15-paper limits in SKILL.md

---

## 9. References

Skarlinski MD et al. (2024) *Language agents achieve superhuman synthesis of
scientific knowledge.* arXiv:2409.13740.
[PDF: Skarlinski_et_al_2024_PaperQA2.pdf]

Asai A et al. (2026) *OpenScholar: synthesizing scientific literature with
retrieval-augmented LMs.* Nature 650:856–868.
DOI:10.1038/s41586-025-10072-4
[PDF: s41586-025-10072-4.pdf]

Related planning docs:
- [`citation_traversal.md`](citation_traversal.md) — JATS claim tracing architecture
- [`citation_traversal_experiment.md`](citation_traversal_experiment.md) — proof-of-concept experiment
- [`scaling.md`](scaling.md) — caching and corpus scaling
