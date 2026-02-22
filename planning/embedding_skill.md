# Plan: Embedding-based paperqa skill (with LLM re-ranking)

## Context

The current `/paperqa` skill reads every chunk with Claude and scores all of them with
Haiku subagents — O(N) LLM calls that don't scale. The `/literature-search` skill has the
same problem: after fetching papers from EuropePMC it brute-force reads and scores every chunk.

We want a shared retrieval layer that uses paperqa's vector embeddings to narrow to top-k
chunks, then Haiku subagents re-rank and summarize just those k chunks (mirroring paperqa
the library's two-stage architecture: `summary_llm` per-chunk scoring + distillation, then
final synthesis on the summaries only). No agentapi or API keys needed — local
sentence-transformers for embeddings, Claude/Haiku for LLM work.

### Why re-ranking matters

paperqa (the library) never feeds raw chunks to the final answer LLM. Each retrieved chunk
gets a per-chunk `summary_llm` call that:
1. Scores relevance 0-10
2. Writes a question-focused summary — stripping irrelevant parts

The final synthesis LLM sees only these distilled summaries. This means:
- Cleaner, denser input (noise removed per-chunk)
- The synthesis LLM's context window is spent on signal, not filler
- Low-relevance chunks (score 0) are dropped entirely

Embedding-only retrieval (the previous version of this plan) would pass raw chunks to
synthesis, wasting context on partially-relevant text. Adding Haiku re-ranking gives us
the best of both: cheap vector narrowing + LLM distillation.

---

## Architecture

```
retrieve_chunks.py (Python, local only)          Claude skill layer
─────────────────────────────────────────    ──────────────────────────────
                                             User question
                                                 │
papers/ + papers_fetched/                        │
    │                                            │
    ▼                                            │
sentence-transformer embed + cache               │
    │                                            │
    ▼                                            │
cosine similarity → top k chunks (JSON)  ──►  Read JSON
                                                 │
                                                 ▼
                                          Haiku subagents (parallel)
                                          score + summarize each chunk
                                                 │
                                                 ▼
                                          Filter: drop score < 5
                                          Sort by score desc, top 10
                                                 │
                                                 ▼
                                          Claude synthesizes answer
                                          from summaries (not raw chunks)
```

---

## 1. New file: `retrieve_chunks.py`

A CLI script that does embedding-based indexing and retrieval, outputting JSON chunks.

**Usage:**
```
uv run python retrieve_chunks.py "question" [--k 15] [--papers-dir papers papers_fetched] [--cache-dir .paperqa_cache]
```

Note: `--papers-dir` accepts multiple directories. PDFs are collected from all dirs,
text files from all dirs. This lets both `/paperqa` (just `papers/`) and
`/literature-search` (`papers/ papers_fetched/`) use the same script.

**What it does:**
1. Collects all PDFs and `.txt` files from the specified directories
2. Creates a `SentenceTransformerEmbeddingModel` with `st-all-MiniLM-L6-v2`
3. Computes a cache key (reuse `_papers_cache_key` logic from `main.py`)
4. If cached `Docs` pickle exists, load it; otherwise:
   - Create `Docs()`, call `aadd()` for each paper with `citation=` provided
     and `Settings(parsing=ParsingSettings(use_doc_details=False))` — **zero LLM calls**
   - Save cache
5. Call `docs.retrieve_texts(query=question, k=k, embedding_model=embedding_model)`
   — pure cosine similarity, only embedding call is on the query string
6. Print JSON to stdout:
   ```json
   [{"text": "...", "name": "chunk_name", "doc_citation": "...", "doc_name": "..."}]
   ```

**Key points:**
- `use_doc_details=False` — skips LLM citation-extraction calls
- No `llm_model=` needed — embeddings only
- Caching: pickle + gzip, keyed on file hashes + model name (same pattern as `main.py`)

---

## 2. New skill: `/paperqa` replacement

Replace the existing `.claude/skills/paperqa/SKILL.md` with the embedding + re-ranking
pipeline. Same skill name, better implementation.

### Pipeline

#### Step 1: Vector retrieval
Run `retrieve_chunks.py` via Bash to get top-k chunks as JSON:
```bash
uv run python retrieve_chunks.py "$QUESTION" --k 15 --papers-dir papers papers_fetched
```

If no chunks returned, tell the user and stop.

#### Step 2: Haiku re-ranking + summarization
For each retrieved chunk, spawn a **Haiku** Task subagent (parallel batches of 5-8):

```
You are scoring a text chunk for relevance to a research question.

Research question: "{question}"
Paper: {doc_name}
Chunk: {chunk_name}

Text:
---
{chunk_text}
---

Provide a summary of relevant information that could help answer the question.
Respond with ONLY valid JSON:
{"relevance_score": 0-10, "summary": "2-3 sentence summary of relevant evidence, or empty if irrelevant"}
```

- Collect results. Drop chunks with `relevance_score < 5`.
- Sort by score descending. Keep **top 10**.

#### Step 3: Synthesize from summaries
Claude (host agent) produces the final answer using **only the Haiku-generated summaries**,
not the raw chunk text. This mirrors paperqa's architecture where the final LLM never sees
raw chunks.

Output format:
```
ANSWER
======
[Synthesized answer with inline citations [1], [2], etc.]

REFERENCES
==========
[1] doc_name (chunk_name) — "brief relevant quote from summary"
...
```

---

## 3. Updated `/literature-search` skill

The literature-search skill currently has its own brute-force read + score pipeline
(steps 3-5 in the current SKILL.md). Replace those steps with the shared retrieval layer:

### Updated pipeline

1. **Steps 0-2 unchanged**: Query decomposition, EuropePMC search, fetch full texts
   → `papers_fetched/{pmcid}.txt`
2. **Step 3 (replaces old steps 3-5)**: Run `retrieve_chunks.py` with
   `--papers-dir papers papers_fetched` to get top-k chunks
3. **Step 4**: Haiku re-ranking + summarization (same as `/paperqa` step 2)
4. **Step 5**: Synthesize answer from summaries (same as `/paperqa` step 3,
   plus SEARCH METADATA section)

This eliminates the manual read-every-file + score-every-chunk approach. The literature
search skill becomes: fetch papers → call the same retrieval + re-ranking pipeline →
synthesize.

---

## Files to create/modify

| File | Action |
|---|---|
| `retrieve_chunks.py` | **Create** — embedding retrieval CLI |
| `.claude/skills/paperqa/SKILL.md` | **Replace** — embedding + re-ranking pipeline |
| `.claude/skills/literature-search/SKILL.md` | **Update** — replace steps 3-5 with shared retrieval |

No changes to `main.py`, `cyberian_llm.py`, or existing Python files.

---

## Comparison with alternatives

| | This plan | Current `/paperqa` | `main.py` (codex) |
|---|---|---|---|
| **Retrieval** | Vector cosine → top k | Read all chunks | Vector → top k |
| **Re-ranking** | Haiku on k chunks | Haiku on N chunks | codex on k chunks |
| **What synthesis sees** | Haiku summaries | Haiku summaries | codex summaries |
| **Synthesis LLM** | Claude (host) | Claude (host) | codex |
| **LLM calls** | O(k) Haiku + 1 Claude | O(N) Haiku + 1 Claude | O(k) codex + 1 codex |
| **External deps** | None (local embeddings) | None | agentapi server(s) |
| **Scales to 100+ papers** | Yes (vector narrows) | No (reads everything) | Yes |

---

## Verification

1. **retrieve_chunks.py standalone**:
   ```bash
   uv run python retrieve_chunks.py "What are the main findings?" --k 5 --papers-dir papers
   ```
   Should output JSON array of chunks, no LLM calls. Run again → cache hit (fast).

2. **`/paperqa` skill**:
   ```
   /paperqa What are the main findings?
   ```
   Should call `retrieve_chunks.py`, spawn Haiku re-rankers, synthesize from summaries.

3. **`/literature-search` skill**:
   ```
   /literature-search What is the function of the ILRUN gene?
   ```
   Should fetch papers from EuropePMC, then use the same retrieval + re-ranking pipeline.

4. **Shared corpus**: After a literature search populates `papers_fetched/`, running
   `/paperqa` should pick up those files too (via `--papers-dir papers papers_fetched`).
