---
name: paperqa
description: RAG pipeline over local papers. Reads PDFs/text from papers/ directory, chunks them, uses parallel subagents to score relevance, and synthesizes a cited answer. Use when asked to answer questions about papers in the project.
argument-hint: [question]
allowed-tools: Read, Glob, Grep, Task, Bash
---

# PaperQA — RAG over local papers

You are a research assistant performing retrieval-augmented generation over local papers. Follow this pipeline exactly.

## Input

The user's research question is provided as the skill argument: `$ARGUMENTS`

## Step 1: Discover papers

Use Glob to find all papers:
- `papers/*.pdf`
- `papers/*.txt`
- `papers_fetched/*.txt`

List what you found. If no papers are found, tell the user and stop.

## Step 2: Read and chunk papers

For each paper found:
- **PDF files**: Use Read with the `pages` parameter. Read in batches of up to 10 pages at a time (e.g., pages "1-10", "11-20", etc.). First read pages "1-2" to gauge length, then read remaining page ranges.
- **Text files**: Use Read. For files over 200 lines, read in 200-line segments using `offset` and `limit`.

Track each chunk as: `(paper_filename, chunk_index, first_50_chars_preview)`

Read multiple papers in parallel where possible.

## Step 3: Parallel evidence gathering

For each chunk, spawn a **haiku** Task subagent with this prompt:

```
You are scoring a text chunk for relevance to a research question.

Research question: "{question}"

Paper: {paper_filename}, chunk {chunk_index}

Text chunk:
---
{chunk_text}
---

Instructions:
1. Rate relevance to the research question from 0-10.
2. If relevance >= 5, write a 2-3 sentence summary of the relevant evidence found in this chunk. Include specific data points, findings, or claims.
3. If relevance < 5, summary should be empty string.

Respond with ONLY valid JSON, no other text:
{"relevance": N, "summary": "..."}
```

Important:
- Use `model: haiku` for all chunk-scoring subagents to keep costs low and speed high.
- Use `subagent_type: general-purpose` for the Task calls.
- Launch subagents in **parallel batches** — put multiple Task tool calls in a single message. Batch size of 5-8 is ideal.
- Collect all results. Sort by relevance score descending. Keep the **top 10** chunks.

## Step 4: Synthesize answer

Now, as the main agent, you have the top 10 evidence chunks with their summaries and source papers. Re-read the full text of each top chunk if needed for accuracy.

Produce a final answer in this exact format:

```
ANSWER
======
[Your synthesized answer here. Use inline citations like [1], [2] etc.
Be thorough but concise. Ground every claim in evidence from the papers.]

REFERENCES
==========
[1] paper_filename (chunk N) — "brief relevant quote from the chunk"
[2] paper_filename (chunk N) — "brief relevant quote from the chunk"
...
```

## Guidelines

- Never fabricate evidence. Only cite what you actually read from the papers.
- If the papers don't contain enough information to answer the question, say so clearly and report what was found.
- Prefer specific data points and findings over vague summaries.
- When papers disagree, note the disagreement and cite both sides.
