# Query Decompose Skill — Planning

**Status:** Draft — needs experimentation before implementation
**Detailed plan:** `~/.claude/plans/fancy-cooking-steele.md`
**Related:** `query_decomposition.md` (analysis), `query_planning_implementation.md` (phased roadmap)

## Problem

The `literature-search` skill tells the LLM to "generate 3 keyword queries" from arbitrary input. No entity extraction, no synonym awareness, no intent classification. Queries target EuropePMC only — no ASTA snippet search support.

## Proposed solution

A standalone skill (`.codex/skills/query-decompose/SKILL.md`) that takes a research question and outputs structured JSON with queries for **both** EuropePMC and ASTA snippet search.

Pure LLM reasoning — no tools, no API calls. Could become a programmatic LLM API call later.

## Output shape (draft)

```json
{
  "original_question": "...",
  "entities": ["tanycyte", "hypothalamus"],
  "synonyms": {"tanycyte": ["tanycytes", "α-tanycyte", "β-tanycyte"]},
  "intent": "established | recent | mixed",
  "strategy": "reviews_first | primary_first | fulltext_first",
  "temporal_scope": {"from_year": 2022, "to_year": null} | null,

  "europepmc_queries": {
    "abstract_queries": ["tanycyte subtypes markers hypothalamus", ...],
    "fulltext_queries": ["BODY:\"tanycyte\" AND BODY:\"marker\"", ...],
    "review_query": "tanycyte hypothalamus markers PUB_TYPE:review",
    "filters": {"has_fulltext": true, "date_range": null}
  },

  "asta_queries": {
    "snippet_queries": ["tanycyte subtype markers hypothalamus", ...],
    "scoped_queries": []
  },

  "reasoning": "Brief rationale"
}
```

Key difference between backends:
- **EuropePMC**: short keyword queries (BM25), field operators (`BODY:`, `PUB_TYPE:review`)
- **ASTA**: natural-language semantic queries (cross-encoder), longer/more descriptive, no field operators

## What needs experimenting first

1. **Does the LLM reliably produce valid JSON in this format?** Try a few manual runs with different question styles before committing to the schema.

2. **Are ASTA snippet queries actually better when longer/more descriptive?** Or does short keyword style work equally well with the cross-encoder? Compare recall on known-good queries from the citation traversal experiment.

3. **Does synonym expansion help or hurt?** EuropePMC BM25 might benefit from explicit synonyms as separate queries. ASTA's cross-encoder might handle synonyms implicitly. Test both.

4. **Intent detection accuracy.** Does the LLM reliably distinguish "start with reviews" from a question that merely mentions reviews? Try adversarial examples.

5. **How does this interact with `literature-search` Step 1?** The downstream skill needs to consume this JSON and route queries. Sketch the integration before finalizing the schema.

## Experiment plan

Run the skill prompt manually (paste into Claude conversation) with these test cases:

| Question | Expected intent | Expected strategy | Key entities |
|---|---|---|---|
| "What markers distinguish tanycyte subtypes?" | established | primary_first | tanycyte, markers |
| "Start with reviews — ILRUN gene function" | established | reviews_first | ILRUN |
| "Recent findings on pinealocyte TFs since 2022" | recent | primary_first | pinealocyte, transcription factors |
| "What is the role of Fezf2 in corticospinal neuron specification?" | established | primary_first | Fezf2, corticospinal neuron |
| "Are there serous demilune cells in human sublingual glands?" | established | fulltext_first | serous demilune, sublingual gland |

Check: valid JSON, sensible entities/synonyms, correct intent/strategy, queries look useful.

Then run the generated queries against both EuropePMC and ASTA to see if they actually return relevant papers.
