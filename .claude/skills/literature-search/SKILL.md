---
name: literature-search
description: Searches EuropePMC for papers related to the question, downloads full texts, then runs RAG to produce a cited answer. Use when the user wants to search the literature for a topic.
argument-hint: [research question]
allowed-tools: Read, Glob, Grep, Task, Bash, WebFetch
---

# Literature Search — EuropePMC fetch + RAG

You are a research assistant that searches EuropePMC for relevant papers, downloads full texts, and produces a cited answer. Follow this pipeline exactly.

## Input

The user's research question is provided as the skill argument: `$ARGUMENTS`

## Step 0: Query decomposition

Decompose the research question into **3 targeted EuropePMC search queries**. Each query should be:
- 2-6 words
- Use scientific terminology and gene/protein names where appropriate
- Cover different angles of the question

Example for "What is the function of the ILRUN gene?":
1. `ILRUN gene function`
2. `ILRUN interferon regulation`
3. `ILRUN cholesterol innate immunity`

## Step 1: Search EuropePMC

For each of the 3 subqueries, use WebFetch to search EuropePMC. Launch all 3 searches **in parallel**:

URL pattern:
```
https://www.ebi.ac.uk/europepmc/webservices/rest/search?query={subquery}+HAS_FT:y&resultType=core&pageSize=10&format=json
```

Use this prompt for WebFetch: `"Extract all pmcid values and titles from the resultList.result array in this JSON. Return as a list of {pmcid, title} objects. If no results, return empty list."`

Collect all pmcids from all searches, deduplicate, cap at **15** papers total (to keep processing manageable).

## Step 2: Fetch full texts

For each pmcid, check if `papers_fetched/{pmcid}.txt` already exists (use Glob). Skip papers that are already downloaded.

For new papers, fetch the JATS XML full text and convert to plain text. Use a **Bash** call with inline Python for each paper:

```bash
python3 -c "
import urllib.request, xml.etree.ElementTree as ET, sys, os
pmcid = sys.argv[1]
url = f'https://www.ebi.ac.uk/europepmc/webservices/rest/{pmcid}/fullTextXML'
try:
    data = urllib.request.urlopen(url, timeout=30).read()
    root = ET.fromstring(data)
    texts = []
    for elem in root.iter():
        if elem.text and elem.text.strip():
            texts.append(elem.text.strip())
        if elem.tail and elem.tail.strip():
            texts.append(elem.tail.strip())
    text = '\n'.join(texts)
    os.makedirs('papers_fetched', exist_ok=True)
    with open(f'papers_fetched/{pmcid}.txt', 'w') as f:
        f.write(text)
    print(f'OK: {pmcid} ({len(text)} chars)')
except Exception as e:
    print(f'FAIL: {pmcid}: {e}')
" "{pmcid}"
```

Launch downloads in **parallel batches** of 5. Report how many papers were successfully downloaded.

## Step 3: Discover all papers

Use Glob to find all papers available for RAG:
- `papers/*.pdf`
- `papers/*.txt`
- `papers_fetched/*.txt`

List what was found. Prioritize newly fetched papers but include existing ones too.

## Step 4: Read and chunk papers

For each paper:
- **PDF files**: Use Read with `pages` parameter. Read in batches of up to 10 pages (e.g., "1-10", "11-20"). First read pages "1-2" to gauge length.
- **Text files**: Use Read. For files over 200 lines, read in 200-line segments using `offset` and `limit`.

Track each chunk as: `(paper_filename, chunk_index, first_50_chars_preview)`

Read multiple papers in parallel where possible.

## Step 5: Parallel evidence gathering

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
- Use `model: haiku` for all chunk-scoring subagents.
- Use `subagent_type: general-purpose` for the Task calls.
- Launch subagents in **parallel batches** of 5-8.
- Collect all results. Sort by relevance descending. Keep the **top 10**.

## Step 6: Synthesize answer

Re-read the full text of each top-10 chunk if needed. Produce a final answer:

```
ANSWER
======
[Your synthesized answer with inline citations [1], [2], etc.
Ground every claim in evidence from the papers. Be thorough but concise.]

REFERENCES
==========
[1] paper_filename (chunk N) — "brief relevant quote"
[2] paper_filename (chunk N) — "brief relevant quote"
...

SEARCH METADATA
===============
Queries used: [list the 3 EuropePMC queries]
Papers found: N total, M with full text downloaded
Papers analyzed: K
Top evidence chunks scored: J out of total L chunks
```

## Guidelines

- Never fabricate evidence. Only cite what you actually read from the papers.
- If the search returns insufficient results, say so clearly and suggest alternative search terms.
- Prefer specific data points and findings over vague summaries.
- When papers disagree, note the disagreement and cite both sides.
- If a paper download fails, skip it and note it in the metadata.
