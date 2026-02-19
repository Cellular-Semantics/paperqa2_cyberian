# EuropePMC Literature Search Pipeline

> Plan file also exists at: `~/.claude/plans/woolly-sprouting-hinton.md`

## Context

The current pipeline requires PDFs to be manually placed in `papers/`. The goal is to approximate
the PaperQA2 paper's approach (arxiv 2409.13740): an LLM decomposes the user query into targeted
search strings, EuropePMC is searched for each, full texts are downloaded, and the existing RAG
pipeline runs on the result corpus.

Key insight from the paper: **no abstract-level pre-filter is needed**. The sentence-transformer
vector search built into `docs.aquery()` handles chunk-level pre-filtering efficiently across the
full corpus. With `evidence_k=10` (paperqa default), only 10 chunks go to codex regardless of
how many papers are indexed. The expensive part (codex) is already bounded.

EuropePMC `HAS_FT:y` filter searches full text (not just abstracts), so search ranking already
goes beyond title/abstract matching.

---

## Pipeline

```
User question
    │
    ▼  _sync_send_and_wait() [one codex call, sync, before asyncio.run]
LLM query decomposition → ["subquery 1", "subquery 2", ...]
    │
    ▼  EuropePMC REST search per subquery (httpx, sync)
Candidate papers (pmcid, doi, title, abstract)
    │
    ▼  Deduplicate by pmcid — cap at 50
Unique papers
    │
    ▼  EuropePMC full-text XML per pmcid → jats_to_text() → .txt files
papers_fetched/{pmcid}.txt
    │
    ▼  asyncio.run(run_experiment())  [existing main.py, unchanged]
    │   ├─ sentence-transformer embed all chunks
    │   ├─ vector search → top evidence_k chunks
    │   └─ codex chunk scoring + answer synthesis
    ▼
Answer + references
```

---

## New files

### `europepmc.py`

No new dependencies — uses httpx (already in pyproject.toml) and stdlib `xml.etree.ElementTree`.

```
EPMC_SEARCH_URL   = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
EPMC_FULLTEXT_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML"
REQUEST_DELAY_SECS = 0.5   # polite rate limiting
```

**`epmc_search(query: str, max_results: int = 10) -> list[dict]`**
- GET search URL with params: `query="{query} HAS_FT:y"`, `resultType=core`,
  `pageSize={max_results}`, `format=json`
- Returns list of `{pmcid, doi, title, year}` dicts (skip entries with no pmcid)
- Sleep `REQUEST_DELAY_SECS` after each call

**`fetch_full_text_xml(pmcid: str) -> str | None`**
- GET `EPMC_FULLTEXT_URL.format(pmcid=pmcid)`
- Return XML string on 200, None otherwise
- Sleep `REQUEST_DELAY_SECS` after call

**`jats_to_text(xml_str: str) -> str`**
- Parse with `xml.etree.ElementTree.fromstring()`
- Extract in order:
  1. `<article-title>` text (from `<front>`)
  2. All `<p>` text inside `<abstract>`
  3. All text from `<body>` via `root.find("body").itertext()`, but first remove all
     `<ref>` subtrees (references are noise) with `ref_parent.remove(ref_elem)`
- Join sections with `\n\n---\n\n`
- Strip leading/trailing whitespace, collapse runs of 3+ newlines to 2

**`fetch_papers(queries: list[str], papers_dir: Path, max_per_query: int = 10,
               max_total: int = 50) -> list[Path]`**
- Create `papers_dir` if it doesn't exist
- For each query: call `epmc_search(query, max_per_query)`, collect results
- Deduplicate by pmcid (preserve first-seen order); stop when `max_total` reached
- For each unique pmcid:
  - Skip if `papers_dir/{pmcid}.txt` already exists (simple file-level cache)
  - Call `fetch_full_text_xml(pmcid)` → `jats_to_text()` → write to `papers_dir/{pmcid}.txt`
  - Log title and pmcid on success, warning on failure
- Return sorted list of all `.txt` paths in `papers_dir`

---

### `search_and_ask.py`

New entry point. Everything before `asyncio.run()` is synchronous.

**Configuration** (env vars — all AGENTAPI_*, EMBEDDING_MODEL, CACHE_DIR still read from main.py):
```
EPMC_MAX_PER_QUERY   default 10    papers to fetch per subquery
EPMC_MAX_PAPERS      default 50    total paper cap
EPMC_MAX_QUERIES     default 3     max subqueries LLM may generate
PAPERS_FETCH_DIR     default "papers_fetched"   where to save .txt files
```

**`decompose_query(question: str, host: str, port: int, timeout: int) -> list[str]`**

Calls `_sync_send_and_wait(host, port, prompt, timeout, poll_interval=2.0)` where prompt is:

```
You are a biomedical literature search expert.
Break down the following research question into {EPMC_MAX_QUERIES} specific EuropePMC/PubMed
search query strings. Each query should be 2-6 words using precise scientific terminology.
Together the queries should cover different aspects of the question.

Return ONLY a JSON array of strings, e.g.: ["query one", "query two", "query three"]
Do not include any other text.

Research question: {question}
```

Parse response:
1. Try `json.loads(response_text.strip())`
2. Fallback: regex `re.search(r'\[.*?\]', response_text, re.DOTALL)` → `json.loads(match.group())`
3. Fallback: `[question]` (use raw question as single query)

Log the generated subqueries at INFO level.

**`main()`**
```
1. argparse: positional `question`
2. Import from main.py: _is_server_running, _start_agentapi_server,
   run_experiment, AGENTAPI_HOST, AGENTAPI_PORTS, AGENTAPI_TIMEOUT
3. Start/check agentapi (same logic as main.py: auto-start single port)
4. decompose_query(question, host=AGENTAPI_HOST, port=AGENTAPI_PORTS[0], ...)
5. papers_dir = Path(PAPERS_FETCH_DIR)
6. paper_paths = fetch_papers(subqueries, papers_dir, EPMC_MAX_PER_QUERY, EPMC_MAX_PAPERS)
7. if not paper_paths: print error, sys.exit(1)
8. asyncio.run(run_experiment(question, paper_paths))
9. finally: terminate managed agentapi proc if started
```

---

## Files to create / change

| File | Action |
|------|--------|
| `europepmc.py` | **NEW** |
| `search_and_ask.py` | **NEW** |
| `planning/ROADMAP.md` | Update: move item 1 (literature search) from Pending → Done |
| `README.md` | Add `search_and_ask.py` usage section |
| `main.py` | No changes |
| `cyberian_llm.py` | No changes |
| `pyproject.toml` | No changes (httpx already a dep) |

Note: artl-mcp (`download_pdf_from_doi` via Unpaywall) is a natural future enhancement for
fetching actual PDFs when `EPMC_EMAIL` is set. Deferred — JATS XML full text is sufficient
for v1.

---

## Verification

```bash
# 1. Start agentapi
agentapi server codex --port 3284 -- --dangerously-bypass-approvals-and-sandbox

# 2. Run ILRUN test query
uv run python search_and_ask.py "Summarise what is known about the function and expression of the ILRUN gene"

# Expected log output:
# INFO  Generated subqueries: ["ILRUN gene function", "C6orf106 expression", "ILRUN innate immunity"]
# INFO  epmc_search: 10 results for "ILRUN gene function HAS_FT:y"
# INFO  Fetched PMC12345678.txt (ILRUN regulates interferon...)
# ... (up to 50 papers)
# INFO  Indexed N document(s). Running query ...
# === ANSWER ===

# 3. Inspect fetched papers
ls papers_fetched/ | wc -l
head -80 papers_fetched/PMC*.txt | head -80
```
