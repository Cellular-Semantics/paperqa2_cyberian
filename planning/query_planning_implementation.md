# Query Planning — Phased Implementation

## Problem

The current literature-search skill generates 3 fixed keyword queries from the user's
input verbatim, with no entity extraction, intent classification, or strategy selection.
This is equivalent to PaperQA2's "No Agent" baseline.

Real user input is often a paragraph, a project description, or multiple questions.
The agent is left to infer good search terms from arbitrary free text, with unpredictable
results.

## Goal

Add a structured query analysis step before searching begins, without requiring users
to write in any special format. Plain English signals ("start with reviews", "recent
findings") should guide strategy selection automatically.

---

## Phase 1 — Better query analysis, same search infrastructure

**Change:** Expand Step 0 only. Step 1 (search) is unchanged.

**What it does:**

The main agent performs a structured reasoning step on `$ARGUMENTS` and produces:

```json
{
  "entities": ["key named entities: cell types, genes, species, diseases, techniques"],
  "synonyms": {"entity": ["alt term 1", "alt term 2"]},
  "intent": "established | recent | mixed",
  "strategy": "reviews_first | primary_first | fulltext_first",
  "abstract_queries": ["query 1 (2-6 words)", "query 2", "query 3"],
  "fulltext_queries": ["BODY:\"term\" AND BODY:\"term2\""],
  "review_query": "terms AND PUB_TYPE:review",
  "temporal_scope": {"from_year": YYYY, "to_year": YYYY} | null
}
```

In Phase 1, only `abstract_queries` are used (same 3-query flow as now). The other fields
are computed but reserved for Phase 2+.

**User strategy signals detected from free text (no special syntax):**
- "reviews first", "start with reviews", "citation chain", "established knowledge"
  → `strategy: reviews_first`
- "recent", "latest", "since 2023", "new papers"
  → `intent: recent`
- "only in methods", "specific marker", "rare entity"
  → `strategy: fulltext_first`

**Value:** Immediately better queries from arbitrary input. Entity extraction prevents
the agent from using irrelevant words as search terms. Synonym awareness improves recall.
The plan is produced and logged so the user can see what the agent understood.

**Paper cap:** unchanged at 15.

**Files changed:** `.codex/skills/literature-search/SKILL.md` (Step 0 only)

---

## Phase 2 — Add fulltext search alongside abstract search

**Change:** Step 1 runs both abstract and BODY: field searches and deduplicates.

Regardless of strategy, always run:
- `abstract_queries` in parallel (existing)
- `fulltext_queries` in parallel (new) — `BODY:"term" AND BODY:"term2"`

Deduplicate by PMCID. Keep the union, cap at 20.

**Why 20:** Running two parallel search types roughly doubles candidates before
deduplication. 20 accommodates this without arbitrary truncation of good results.

**Value:** Finds papers where the entity appears only in methods/results (Scenario 3),
not just title/abstract. Already validated — see search_strategy.md Section 3.
No new infrastructure needed; artl-mcp already supports BODY: field syntax.

**Files changed:** `.codex/skills/literature-search/SKILL.md` (Step 1)

---

## Phase 3 — Strategy-driven search branches

**Change:** Step 1 branches on `strategy` from the Phase 1 plan.

### Branch A: `reviews_first`

Designed for established knowledge where the user wants citation-chain coverage:

1. Run `review_query` → up to 5 review papers
2. Note publication years of reviews found → derive `review_cutoff` (year of most recent)
3. Run `abstract_queries` (non-review) in parallel → up to 10 primary papers
4. Run `fulltext_queries` in parallel → up to 5 additional papers
5. Always run `abstract_queries` filtered to `PUB_DATE:[{review_cutoff} TO 2026]`
   → up to 5 recent papers (reviews are never fully up to date)
6. Deduplicate. Cap at 20. Priority: reviews > primaries > recent.

Note: citation traversal from the reviews is a Phase 4+ concern (requires the library
agentic interface). Phase 3 just fetches the review papers; full citation graph traversal
comes later.

### Branch B: `primary_first` (default)

1. Run `abstract_queries` in parallel → up to 15 papers
2. Run `fulltext_queries` in parallel → up to 5 additional papers
3. Deduplicate. Cap at 20.

### Branch C: `fulltext_first`

For Scenario 3 (entity appears only in body text):

1. Run `fulltext_queries` first → up to 10 papers
2. Run `abstract_queries` in parallel → up to 10 papers
3. Deduplicate. Cap at 20.

**Files changed:** `.codex/skills/literature-search/SKILL.md` (Step 1)

---

## Phase 4 — Iterative agentic loop (future)

Requires switching from `retrieve_chunks.py` direct call to the paperqa library's
full agentic interface. This unlocks:

- Agent-observable search state (evidence quality feeds back into query revision)
- Library citation traversal tool (`citations_traversal` via Semantic Scholar + Crossref)
- Autonomous stopping condition (no arbitrary paper caps)
- Full reviews-first → citation traversal workflow

This is a larger architectural change, deferred until Phase 1–3 are stable.

See `search_strategy.md` Section 8 (Prioritised path) for full context.

---

## Implementation order

| Phase | Scope | Risk | Value |
|---|---|---|---|
| 1 | Step 0 only — better query analysis | Low — no search changes | Immediate for all queries |
| 2 | Add BODY: search | Low — additive, already tested | S3 improvement, no strategy needed |
| 3 | Strategy branches | Medium — more complex Step 1 | Reviews-first workflow, guided search |
| 4 | Agentic interface | High — architectural change | Full iterative loop, citation traversal |

Phases 1 and 2 can be implemented together in a single SKILL.md edit.
Phase 3 adds the strategy branching on top, once Phase 1 plan output is validated.

---

## Open questions for Phase 3

- **Review cap:** 5 reviews feels right for seeding — but should we screen them by
  relevance (Haiku abstract check) before deciding which to keep?
- **Recent cutoff:** Use the most recent review year, or the median, or ask the user?
  Most recent seems right — it's the tightest bound on what the reviews cover.
- **BODY: quota within Branch A:** Currently 5. Is this too few if the entity is rare?
  Could make it adaptive (if abstract search returns < 5 relevant papers, increase BODY: quota).
- **Synonym expansion:** Currently the plan generates synonyms but doesn't use them to
  expand abstract_queries automatically. Should it? (1-2 extra queries per entity synonym)

---

## References

- `search_strategy.md` — full scenario mapping and discovery channel analysis
- `scaling.md` — caching implications of paper count changes
- `citation_traversal.md` — JATS claim tracing (complementary to reviews-first citation chain)
