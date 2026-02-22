# Roadmap

## Done

1. ✅ Parallel codex instances — `AGENTAPI_PORTS=3284,3285,...` distributes chunk-summary calls across multiple agentapi/codex servers via an asyncio port pool. Unreachable ports are skipped with a warning.
2. ✅ Embedding cache — `Docs` objects (chunks + embeddings) are pickled to `.paperqa_cache/<hash>.pkl.gz` after first indexing and reloaded on subsequent runs. Cache is keyed on paper filenames/sizes/mtimes + embedding model; auto-invalidates on any change. Disable with `CACHE_DIR=""`.
3. ✅ OpenAI embeddings option — set `EMBEDDING_MODEL=text-embedding-3-small` (requires `OPENAI_API_KEY`). See planning/embedding_cache.md for cache design notes.

## Pending

1. Support running the full paperqa pipeline with literature search

   **Known blocker: sentence-transformer network access in agent sandbox.**
   `retrieve_chunks.py` requires `all-MiniLM-L6-v2` to be reachable at query time (even
   when docs are cached). Outbound DNS/HTTPS to `huggingface.co` is blocked in the codex
   agent sandbox. **Requires systems/admin action** — see
   `planning/embedding_agent_permissions_findings_2026-02-20.md` for full details.
   Minimum: allow egress to `huggingface.co` + `cdn-lfs.huggingface.co` and write access
   to model cache dirs. Short-term workaround: switch to OpenAI embeddings
   (`EMBEDDING_MODEL=text-embedding-3-small`, needs `OPENAI_API_KEY` + `api.openai.com`).

2. Auto-launch agentapi from code with control over session options (e.g. skip update prompts). Currently a single instance is auto-started when none is running; multi-instance requires manual startup.

3. Fix JSON parse failures for PDF chunks containing LaTeX backslash sequences (e.g. `\0.0001` in statistical tables). In `cyberian_llm.py`, post-process codex's JSON responses to escape lone backslashes before returning to paperqa2. Currently these chunks are silently dropped; fixing this would improve recall on papers with numeric tables.

4. Improve output format. Currently the answer and processed chunk summaries are concatenated in stdout. Consider structured output (e.g. JSON with question, answer, and chunks as separate fields) which could drive downstream report generation — HTML report or linked Markdown docs.
