---
name: paperqa
description: Answer questions over local papers using embedding retrieval, chunk re-ranking, and cited synthesis. Use when the user asks questions about papers in this repository.
metadata:
  short-description: Local paper RAG QA
---

# PaperQA

Use this skill for paper-grounded Q&A over local document collections.

## Input

The user question is the retrieval query.

## Workflow

1. Vector retrieval
- Run:
  `uv run python retrieve_chunks.py "<question>" --k 15 --papers-dir papers papers_fetched`
- Parse JSON output chunks.
- If no chunks, report that no relevant evidence was found.

2. Re-rank + summarize
- Score each chunk for relevance (0-10).
- Produce a short evidence summary for each chunk.
- Drop chunks with score < 5.
- Keep top 10 chunks by relevance.
- Execute scoring in parallel batches when possible.

3. Synthesize answer
- Use only retained summaries as evidence.
- Provide:
  - `ANSWER` with inline citations like `[1]`
  - `REFERENCES` mapping each citation to paper/chunk evidence.

## Output rules

- Do not invent evidence.
- If evidence is insufficient, say so and report what is available.
- Note disagreements across papers.
- Prefer specific and testable claims.
