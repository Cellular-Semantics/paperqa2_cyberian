# Query Decomposition and Search — PaperQA2 vs. Our Pipeline

## Our current approach

The literature-search skill pre-generates all queries upfront, before any
searching begins:

1. Main agent (Claude Sonnet) reads the research question
2. Generates **3 keyword queries** covering different angles
3. All 3 run **in parallel** against EuropePMC
4. Results are deduplicated, capped at 15 papers
5. All 15 papers are fetched, embedded, chunks retrieved
6. Fixed pipeline terminates — no iteration

The queries are generated from the question alone, with no knowledge of what
the search will return. Once generated, they cannot be revised.

---

## PaperQA2's approach

PaperQA2 treats search as a tool that an agent calls iteratively. The agent
receives the question plus a single orchestration prompt:

> *"Answer question: {question}. Search for papers, gather evidence, collect
> papers cited in evidence then re-gather evidence, and answer.*
> *If you do not have enough evidence to generate a good answer, you can:*
> *- Search for more papers (preferred)*
> *- Collect papers cited by previous evidence (preferred)*
> *- Gather more evidence using a different phrase*
> *Once you have five or more pieces of evidence from multiple sources, or you
> have tried a few times, call {generate_answer_tool}. The current status of
> evidence/papers/cost is {status}."*

The Paper Search tool is prompted to generate:

> *"A search query in this format: [query], [start year]-[end year]."*

The agent then:
1. Generates **one search query** (with optional date range)
2. Gets 12 candidate papers from Semantic Scholar
3. Papers are parsed, chunked, embedded — added to the agent's running context
4. Agent calls Gather Evidence (RCS), inspects results
5. Observes `{status}` — papers in context, evidence gathered, cost so far
6. **Decides autonomously** whether to:
   - Search again with different terms
   - Traverse citations from high-scoring papers
   - Generate an answer
7. Stopping condition is agent-driven: enough evidence from multiple sources,
   or several attempts made

---

## Key differences

| Aspect | PaperQA2 | Our pipeline |
|---|---|---|
| Queries generated | One at a time, iteratively | 3 upfront, in parallel |
| Query revision | Yes — based on evidence found | No |
| Stopping condition | Agent decides | Fixed pipeline always completes |
| Agent sees own state | Yes — `{status}` injected each step | No |
| Search backend | Semantic Scholar | EuropePMC |
| Papers per search | 12 | 15 total (all 3 queries combined) |
| Date range support | Yes | No |

---

## The ablation result

PaperQA2 explicitly tested a **"No Agent"** baseline — a hardcoded sequence of
`paper_search → gather_evidence → generate_answer` with no iteration. It had
**significantly lower accuracy** than the full agentic version (p = 0.015).

Their explanation:

> *"We attribute the performance difference to the agent's better recall
> because it can return to and change keyword searches after observing the
> amount of relevant papers it finds."*

**Our current pipeline is equivalent to their No Agent baseline.**

---

## Why this matters per scenario

**Scenario 1 (compact literature):** Difference is minimal. 3 fixed queries
are likely sufficient when all relevant papers surface easily.

**Scenario 2 (large literature):** Significant impact. A fixed pipeline
accepts the first 15 papers and stops. An agentic system notices poor coverage,
tries different terminology, and iterates until it has sufficient evidence.

**Scenario 3 (entities only in full text):** Critical failure mode. If the
first search returns poor results because the entity isn't in titles/abstracts,
a fixed pipeline moves on with thin evidence. An agentic system detects this —
via low RCS scores — and can switch strategy: different search terms, citation
traversal, or a broader/narrower query.

---

## What switching to the agentic interface unlocks

Moving from `retrieve_chunks.py` direct call to the library's full agentic
interface would give us:

1. **Iterative search with query revision** — the core improvement
2. **Citation traversal tool** — already implemented, currently bypassed
3. **Agent-observable state** — evidence quality feeds back into search strategy
4. **Autonomous stopping** — no arbitrary paper/chunk caps needed
5. **Date-range queries** — useful for seeding with recent reviews first

These are not separate features to build — they are all part of the agentic
interface that our current skill deliberately sidesteps by calling
`retrieve_chunks.py` directly.

---

## The EuropePMC vs. Semantic Scholar question

PaperQA2 uses Semantic Scholar as its search backend. We use EuropePMC.
This is not just an implementation detail — it affects what gets found:

| | EuropePMC | Semantic Scholar |
|---|---|---|
| Biomedical coverage | Excellent (PubMed, PMC, preprints) | Good but broader/less curated |
| Full text access | Strong (JATS XML for OA) | Limited |
| Field filters | `PUB_TYPE:review`, `HAS_FT:y`, date ranges | Venue, year |
| Body-text search | No (titles/abstracts only) | Yes (via snippet search) |
| Citation resolution | Via PMCID/DOI lookup | Native (Semantic Scholar IDs) |

The right answer is probably **both**: EuropePMC for biomedical discovery and
full-text access (JATS), Semantic Scholar (via ASTA MCP) for body-text snippet
search and citation resolution. These are complementary, not competing.

An agentic interface could use EuropePMC for initial paper discovery (leveraging
`PUB_TYPE:review`, `HAS_FT:y` filters) and then Semantic Scholar for citation
traversal and snippet search — matching each backend to what it does best.

---

## Reference

Skarlinski MD et al. (2024) *Language agents achieve superhuman synthesis of
scientific knowledge.* arXiv:2409.13740.
[PDF: Skarlinski_et_al_2024_PaperQA2.pdf]
