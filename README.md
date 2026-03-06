# paperqa2-cyberian

RAG pipeline using [paperqa2](https://pypi.org/project/paper-qa/) to retrieve and summarise PDF papers, with all LLM calls routed through one or more local [codex](https://openai.com/index/openai-codex/) agents via [agentapi](https://github.com/coder/agentapi). No OpenAI API key required for LLM calls; embeddings are computed locally with sentence-transformers.

## Requirements

- Python ≥ 3.14
- [uv](https://docs.astral.sh/uv/)
- `agentapi` CLI with codex support

## Quick start

### Local papers (main.py)

**1. Start one or more agentapi/codex servers** (each in its own terminal):

```bash
agentapi server codex --port 3284 -- --dangerously-bypass-approvals-and-sandbox
# optional second instance for parallel processing:
agentapi server codex --port 3285 -- --dangerously-bypass-approvals-and-sandbox
```

**2. Add PDF papers:**

```bash
mkdir -p papers
cp my_paper.pdf papers/
```

**3. Run a query:**

```bash
uv run python main.py "What are the main findings?"
```

For parallel processing across multiple instances:

```bash
AGENTAPI_PORTS=3284,3285 uv run python main.py "What are the main findings?"
```

### Claude Code skills (no agentapi required)

Two [Claude Code](https://claude.ai/claude-code) skills are provided. These use local
sentence-transformer embeddings for retrieval and Claude Haiku for re-ranking — no agentapi
server needed.

**`/paperqa`** — RAG over papers already in `papers/` or `papers_fetched/`:

```text
/paperqa What are the main findings about ILRUN gene expression?
```

**`/literature-search`** — fetch papers from EuropePMC then run RAG:

```text
/literature-search Summarise what is known about the function and expression of the ILRUN gene
```

Both skills use `retrieve_chunks.py` to narrow to the top-k most relevant chunks via
cosine similarity before any LLM calls, then Haiku re-ranks and summarises those chunks in
parallel.

> **Note:** sentence-transformers requires network access to `huggingface.co` on first use
> (to download the model). See `planning/ROADMAP.md` item 1 for details and workarounds.

## Features

- **Local LLM** — all summarisation and answer-synthesis calls go to codex via agentapi; no OpenAI API calls
- **Local embeddings** — sentence-transformers (`all-MiniLM-L6-v2` by default); no embedding API calls
- **Embedding cache** — `Docs` objects (chunks + embeddings) are pickled to `.paperqa_cache/` on first run and reloaded on subsequent runs; cache is invalidated automatically when papers change or the embedding model changes
- **Parallel sessions** — set `AGENTAPI_PORTS=3284,3285,3286` to distribute chunk-summary calls across multiple codex instances; unreachable ports are skipped with a warning
- **Context isolation** — `/new` is sent to codex before every call so each LLM request starts with a clean context window regardless of what ran before

## Configuration

All configuration is via environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `AGENTAPI_HOST` | `localhost` | agentapi server hostname |
| `AGENTAPI_PORT` | `3284` | Port for a single agentapi instance |
| `AGENTAPI_PORTS` | *(unset)* | Comma-separated ports for parallel instances, e.g. `3284,3285,3286`. Overrides `AGENTAPI_PORT`. |
| `AGENTAPI_TIMEOUT` | `300` | Max seconds to wait for a single LLM call |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformer model (the `st-` prefix is added automatically). Set to `text-embedding-3-small` to use OpenAI embeddings instead (requires `OPENAI_API_KEY`). |
| `CACHE_DIR` | `.paperqa_cache` | Directory for the embedding cache. Set to `""` to disable caching. |

## How it works

```text
PDF files
   │
   ▼ docs.aadd()  [sentence-transformer embeddings, no LLM]
   │
   ▼ docs.aquery()
       │
       ├─ vector search  [cosine similarity, no LLM]
       │
       ├─ chunk summarisation  [one codex call per retrieved chunk, parallel across ports]
       │    └─ chunks scoring < 1 are discarded
       │
       └─ answer synthesis  [one codex call with all surviving summaries as context]
```

paperqa2 asks the LLM to return structured JSON for chunk summaries. Each call is preceded by `/new` to reset the codex context window, then the response is retrieved from the agentapi message history.

## Files

| File / Directory | Purpose |
| --- | --- |
| `main.py` | Shim — delegates to `paperqa2_cyberian.main`; run with `uv run python main.py` |
| `retrieve_chunks.py` | Shim — delegates to `paperqa2_cyberian.retrieve_chunks`; kept at root so skills can call it directly |
| `paperqa2_cyberian/main.py` | Agentapi lifecycle, embedding cache, paperqa2 wiring |
| `paperqa2_cyberian/cyberian_llm.py` | `CyberianLLMModel` — `LLMModel` subclass that routes calls to agentapi |
| `paperqa2_cyberian/retrieve_chunks.py` | Embedding retrieval CLI — indexes papers, returns top-k chunks as JSON (no LLM calls) |
| `paperqa2_cyberian/cache.py` | Shared embedding cache helpers (key generation, load, save) |
| `.claude/skills/paperqa/` | `/paperqa` skill — embedding retrieval + Haiku re-ranking over local papers |
| `.claude/skills/literature-search/` | `/literature-search` skill — EuropePMC fetch + same retrieval pipeline |
| `papers/` | Input PDFs (git-ignored) |
| `papers_fetched/` | Full texts fetched by `/literature-search` (git-ignored) |
| `test_papers/` | Sample paper for integration testing |
| `.paperqa_cache/` | Embedding cache (auto-created, git-ignored) |
| `planning/` | Design notes and roadmap |
