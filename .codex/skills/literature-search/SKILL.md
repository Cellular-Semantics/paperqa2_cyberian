---
name: literature-search
description: Search Europe PMC for a research question, fetch full-text papers, run local retrieval, and synthesize a cited answer. Use when the user asks to find literature evidence on a topic.
metadata:
  short-description: Europe PMC search + local RAG
---

# Literature Search

Use this skill when the user wants literature-backed answers from Europe PMC plus local papers.

## Input

The user question is the research question.

## Workflow

1. Query decomposition
- Create 3 focused Europe PMC queries (2 to 6 words each) that cover different angles.

2. Europe PMC search
- For each query, call Europe PMC search API with `HAS_FT:y` and extract `{pmcid, title}` pairs.
- URL template:
  `https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={query}+HAS_FT:y&resultType=core&pageSize=10&format=json`
- Deduplicate and cap to 15 PMCID results.

3. Fetch full text
- Skip papers already present at `papers_fetched/{pmcid}.txt`.
- For missing papers, fetch:
  `https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML`
- Convert XML to plain text and save to `papers_fetched/{pmcid}.txt`.
- Run downloads in parallel batches when possible.

4. Vector retrieval
- Run:
  `uv run python retrieve_chunks.py "<question>" --k 15 --papers-dir papers papers_fetched`
- Parse the JSON chunk list from stdout.
- If empty, report insufficient evidence and stop.

5. Re-rank + summarize
- For each chunk, score relevance (0-10) and write a 2-3 sentence evidence summary.
- Keep only chunks with score >= 5, then keep top 10 by score.
- Do this in parallel batches to reduce latency.

6. Synthesize final answer
- Use only the chunk summaries as evidence.
- Provide:
  - `ANSWER`
  - `REFERENCES` with inline citation mapping like `[1]`
  - `SEARCH METADATA` with queries used, paper counts, retrieval count, and kept evidence count.

## Output rules

- Never fabricate claims.
- Cite only supported claims.
- If evidence is weak or conflicting, state that explicitly.
- Prefer specific findings over broad statements.
