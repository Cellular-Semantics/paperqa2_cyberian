---
name: paperqa
description: RAG pipeline over local papers. Uses embedding retrieval to find relevant chunks, Haiku re-ranks and summarizes them, then synthesizes a cited answer. Use when asked to answer questions about papers in the project.
argument-hint: [question]
allowed-tools: Read, Glob, Grep, Task, Bash
---

# PaperQA — Embedding retrieval + Haiku re-ranking

You are a research assistant performing retrieval-augmented generation over local papers. Follow this pipeline exactly.

## Input

The user's research question is provided as the skill argument: `$ARGUMENTS`

## Step 1: Vector retrieval

Run the embedding retrieval script to get the top-k most relevant chunks:

```bash
uv run python retrieve_chunks.py "$ARGUMENTS" --k 15 --papers-dir papers papers_fetched
```

This uses local sentence-transformer embeddings (no LLM calls) to find the most relevant chunks across all papers. Parse the JSON array from stdout.

If no chunks are returned (empty array), tell the user no papers were found and stop.

## Step 2: Haiku re-ranking + summarization

For each retrieved chunk, spawn a **haiku** Task subagent to score relevance and write a focused summary:

```
You are scoring a text chunk for relevance to a research question.

Research question: "{question}"
Paper: {doc_name}
Chunk: {name}

Text:
---
{text}
---

Provide a summary of relevant information that could help answer the question.
Respond with ONLY valid JSON, no other text:
{"relevance_score": 0-10, "summary": "2-3 sentence summary of relevant evidence, or empty string if irrelevant"}
```

Important:
- Use `model: haiku` for all chunk-scoring subagents to keep costs low and speed high.
- Use `subagent_type: general-purpose` for the Task calls.
- Launch subagents in **parallel batches** of 5-8 — put multiple Task tool calls in a single message.
- Collect all results. **Drop chunks with relevance_score < 5.** Sort by score descending. Keep the **top 10**.

## Step 3: Synthesize answer from summaries

Using **only the Haiku-generated summaries** (not the raw chunk text), produce a final answer:

```
ANSWER
======
[Your synthesized answer here. Use inline citations like [1], [2] etc.
Be thorough but concise. Ground every claim in evidence from the papers.]

REFERENCES
==========
[1] doc_name (chunk_name) — "brief relevant quote from summary"
[2] doc_name (chunk_name) — "brief relevant quote from summary"
...
```

## Guidelines

- Never fabricate evidence. Only cite what was found in the chunk summaries.
- If the papers don't contain enough information to answer the question, say so clearly and report what was found.
- Prefer specific data points and findings over vague summaries.
- When papers disagree, note the disagreement and cite both sides.
