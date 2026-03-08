---
name: find-seeds
description: Discover seed papers for literature review — reviews via EuropePMC, other paper types (scRNAseq, keyword, topic) via ASTA semantic search. Outputs structured JSON with corpus IDs ready for citation-traverse.
---

# Find Seed Papers

You discover starting papers for literature reviews. You use two search backends:
- **EuropePMC** for review articles (only backend with `PUB_TYPE:review` filter)
- **ASTA `search_papers_by_relevance`** for everything else (better semantic ranking, corpus IDs returned directly)

## Input

`$ARGUMENTS` contains a topic description and optional modifiers:

- **Strategy keywords** (detected from free text):
  - "reviews", "review articles" → EuropePMC with `PUB_TYPE:review`
  - "scRNAseq", "single-cell", "atlas" → ASTA search with scRNAseq terms added
  - "recent", "since YYYY", "last N years" → add date filter to both backends
  - If none specified, default to reviews
- **`--output-dir path`** (optional, default `traversal_output/`)
- **`--max N`** (optional, max results per strategy, default 10)

## Procedure

### 1. Parse strategy

Extract the research topic and strategy from the arguments. Examples:

| Input | Topic | Strategy |
|---|---|---|
| "tanycyte markers hypothalamus" | tanycyte markers hypothalamus | reviews (default) |
| "reviews on salivary gland cell types" | salivary gland cell types | reviews |
| "scRNAseq studies of hypothalamic tanycytes" | hypothalamic tanycytes | scrnaseq |
| "recent reviews and scRNAseq on pinealocytes since 2020" | pinealocytes | reviews + scrnaseq, from 2020 |

### 2. Search

Run searches in **parallel** when multiple strategies are requested.

#### Reviews → EuropePMC

```
search_europepmc_papers(
    keywords="{topic} PUB_TYPE:review HAS_FT:y",
    max_results=10,
    result_type="core"
)
```

For recency, prepend `FIRST_PDATE:[{year} TO 2026]` to the keywords.

#### scRNAseq / keyword / general → ASTA

```
search_papers_by_relevance(
    keyword="{topic} single-cell RNA-seq",
    fields="title,authors,year,venue,publicationDate,url,isOpenAccess,abstract",
    limit=10
)
```

For recency, use `publication_date_range="{year}:"` (e.g. `"2020:"`).

For general keyword search (no scRNAseq), just use the topic as the keyword:
```
search_papers_by_relevance(
    keyword="{topic}",
    fields="title,authors,year,venue,publicationDate,url,isOpenAccess,abstract",
    limit=10
)
```

### 3. Normalize results

**From EuropePMC results**, extract:
- `pmcid`, `pmid`, `doi`
- `title`, `year` (from pubYear)
- `abstract_excerpt` (first 300 chars of abstractText)
- `pub_type` (from pubTypeList)
- `is_open_access` (from isOpenAccess)
- `strategy`: "review"

**From ASTA results**, extract:
- `corpus_id` (from paperId or corpusId — already provided)
- `title`, `year`
- `abstract_excerpt` (first 300 chars of abstract)
- `venue`
- `is_open_access` (from isOpenAccess)
- `url`
- `strategy`: "scrnaseq" or "keyword"

Deduplicate across strategies by DOI or title. If a paper appears in both, merge and note all strategies.

### 4. Resolve corpus IDs for EuropePMC results

ASTA results already have corpus IDs. EuropePMC results need resolution:

```
get_paper_batch(
    ids=["PMID:{pmid}", ...] or ["DOI:{doi}", ...],
    fields="title,corpusId"
)
```

Add the `corpusId` to each EuropePMC seed record. Papers that don't resolve can still be used via EuropePMC full text but won't work with ASTA snippet search — flag them.

### 5. Output

Write results to `{output_dir}/seeds.json`:

```json
{
  "topic": "...",
  "strategies_used": ["review", "scrnaseq"],
  "recency_filter": "2020-2026",
  "seeds": [
    {
      "corpus_id": "...",
      "pmcid": "PMC...",
      "pmid": "...",
      "doi": "...",
      "title": "...",
      "year": 2024,
      "abstract_excerpt": "...",
      "venue": "...",
      "is_open_access": true,
      "strategy": ["review"],
      "source_backend": "europepmc"
    },
    {
      "corpus_id": "...",
      "pmcid": null,
      "pmid": null,
      "doi": "10.1038/...",
      "title": "...",
      "year": 2023,
      "abstract_excerpt": "...",
      "venue": "Nature",
      "is_open_access": true,
      "strategy": ["scrnaseq"],
      "source_backend": "asta"
    }
  ],
  "total": N,
  "unresolved_corpus_ids": M
}
```

Also print a human-readable summary:

```
SEED PAPERS FOUND
=================
Strategy: reviews (EuropePMC) + scRNAseq (ASTA) | Recency: since 2020 | Total: N

Reviews (EuropePMC):
  1. [2024] Title of review paper (PMC..., CorpusId:...)
  2. [2023] Another review (PMC..., CorpusId:...)

scRNAseq (ASTA):
  3. [2022] Single-cell atlas of ... (CorpusId:...)
  4. [2021] Transcriptomic profiling ... (CorpusId:...)

Saved to: {output_dir}/seeds.json
```

## Rules

- **Reviews → EuropePMC only.** It's the only backend with `PUB_TYPE:review`.
- **Everything else → ASTA.** Better semantic ranking, corpus IDs come free.
- **Always include `HAS_FT:y` for EuropePMC queries** — papers without full text are less useful.
- **Don't filter by relevance.** Return all results — let the user or orchestrator prune.
- **Flag papers without corpus IDs.** They can't be used for ASTA snippet search scoping.
